from __future__ import annotations

import hashlib
import re
from enum import StrEnum
from typing import Self

from lxml import etree, html
from pydantic import Field, model_validator

from idml_foundation.domain.common import SHA256_PATTERN, StrictModel

_MAX_REPORT_BYTES = 8 * 1024 * 1024
_VERSION = re.compile(r"<!--\s*(\d+\.\d+\.\d+)\s+\d{2}/\d{2}/\d{4}\s*-->")
_TOTALS = {
    "blocking_errors": re.compile(r"Total of blocking errors\s*:\s*(\d+)", re.I),
    "fatal_errors": re.compile(r"Total of fatal errors\s*:\s*(\d+)", re.I),
    "errors": re.compile(r"Total of errors\s*:\s*(\d+)", re.I),
    "warnings": re.compile(r"Total of warnings\s*:\s*(\d+)", re.I),
}


class XpmStatus(StrEnum):
    COMPLETED = "completed"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


class XpmAttestation(StrictModel):
    contract_version: str = "1.0.0"
    candidate_package_sha256: str = Field(pattern=SHA256_PATTERN)
    report_sha256: str = Field(pattern=SHA256_PATTERN)
    tool_sha256: str = Field(pattern=SHA256_PATTERN)
    xpm_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    command_id: str = Field(min_length=1, max_length=100)
    environment: str = Field(min_length=1, max_length=200)


class XpmWarningAcceptance(StrictModel):
    acceptance_id: str = Field(min_length=1, max_length=100)
    xpm_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    warning_count: int = Field(ge=1)
    report_sha256: str = Field(pattern=SHA256_PATTERN)
    accepted_by: str = Field(min_length=1, max_length=200)
    justification: str = Field(min_length=20, max_length=1000)
    evidence_sha256: str = Field(pattern=SHA256_PATTERN)


class XpmResult(StrictModel):
    contract_version: str = "1.1.0"
    status: XpmStatus
    candidate_package_sha256: str = Field(pattern=SHA256_PATTERN)
    xpm_version: str | None = None
    tool_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    report_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    attested: bool = False
    parser_recovered: bool = False
    parser_errors: int = Field(default=0, ge=0)
    command_id: str | None = None
    environment: str | None = None
    blocking_errors: int = Field(default=0, ge=0)
    fatal_errors: int = Field(default=0, ge=0)
    errors: int = Field(default=0, ge=0)
    warnings: int = Field(default=0, ge=0)
    warning_acceptance: XpmWarningAcceptance | None = None
    failure_code: str | None = None

    @model_validator(mode="after")
    def evidence_is_coherent(self) -> Self:
        if self.attested and not all(
            (
                self.xpm_version,
                self.tool_sha256,
                self.report_sha256,
                self.command_id,
                self.environment,
            )
        ):
            raise ValueError("attested XPM result requires complete execution evidence")
        if self.warning_acceptance is not None:
            if not self.report_sha256 or not self.xpm_version:
                raise ValueError("warning acceptance requires a completed report")
            if (
                self.warning_acceptance.report_sha256 != self.report_sha256
                or self.warning_acceptance.xpm_version != self.xpm_version
                or self.warning_acceptance.warning_count != self.warnings
            ):
                raise ValueError("warning acceptance does not match the XPM result")
        return self

    @property
    def passed(self) -> bool:
        warnings_accepted = self.warnings == 0 or self.warning_acceptance is not None
        return (
            self.status == XpmStatus.COMPLETED
            and self.attested
            and warnings_accepted
            and not (self.blocking_errors or self.fatal_errors or self.errors)
        )


class XpmReportParser:
    def parse(
        self,
        report: bytes,
        *,
        candidate_package_sha256: str,
        tool_sha256: str | None,
    ) -> XpmResult:
        if not report or len(report) > _MAX_REPORT_BYTES:
            raise ValueError("XPM report must be between 1 byte and 8 MiB")
        decoded = report.decode("utf-8", errors="strict")
        parser = html.HTMLParser(encoding="utf-8", no_network=True, recover=True)
        try:
            document = html.document_fromstring(decoded, parser=parser)
        except (etree.ParserError, etree.XMLSyntaxError) as exc:
            raise ValueError("XPM report is malformed") from exc
        if etree.QName(document).localname.casefold() != "html":
            raise ValueError("XPM report root must be html")
        visible_nodes_raw = document.xpath(
            "//text()[not(ancestor::script) and not(ancestor::style) and not(ancestor::template)]"
        )
        if not isinstance(visible_nodes_raw, list):
            raise ValueError("XPM report text extraction failed")
        visible_nodes = visible_nodes_raw
        visible_text = " ".join(" ".join(str(value) for value in visible_nodes).split())
        versions = _VERSION.findall(decoded)
        if len(versions) != 1:
            raise ValueError("XPM report must contain exactly one version marker")
        totals: dict[str, int] = {}
        for name, pattern in _TOTALS.items():
            matches = pattern.findall(visible_text)
            if len(matches) != 1:
                raise ValueError(f"XPM report must contain exactly one {name}")
            totals[name] = int(matches[0])
        return XpmResult(
            status=XpmStatus.COMPLETED,
            candidate_package_sha256=candidate_package_sha256,
            xpm_version=versions[0],
            tool_sha256=tool_sha256,
            report_sha256=hashlib.sha256(report).hexdigest(),
            parser_recovered=bool(parser.error_log),
            parser_errors=len(parser.error_log),
            **totals,
        )

    def parse_attested(self, report: bytes, attestation: XpmAttestation) -> XpmResult:
        report_sha256 = hashlib.sha256(report).hexdigest()
        if report_sha256 != attestation.report_sha256:
            raise ValueError("XPM attestation report hash mismatch")
        result = self.parse(
            report,
            candidate_package_sha256=attestation.candidate_package_sha256,
            tool_sha256=attestation.tool_sha256,
        )
        if result.xpm_version != attestation.xpm_version:
            raise ValueError("XPM attestation version mismatch")
        return result.model_copy(
            update={
                "attested": True,
                "command_id": attestation.command_id,
                "environment": attestation.environment,
            }
        )

    def accept_warnings(self, result: XpmResult, acceptance: XpmWarningAcceptance) -> XpmResult:
        return XpmResult.model_validate(
            {
                **result.model_dump(mode="json"),
                "warning_acceptance": acceptance.model_dump(mode="json"),
            }
        )

    def unavailable(self, candidate_package_sha256: str, code: str) -> XpmResult:
        return XpmResult(
            status=XpmStatus.UNAVAILABLE,
            candidate_package_sha256=candidate_package_sha256,
            failure_code=code,
        )
