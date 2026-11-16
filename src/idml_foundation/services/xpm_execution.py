"""Trusted server execution bridge; neither client attestations nor release authority."""

import hashlib
from collections.abc import Callable
from datetime import UTC, datetime
from io import BytesIO
from typing import Any
from zipfile import ZipFile

from pydantic import StrictBool

from idml_foundation.domain.common import StrictModel
from idml_foundation.release.validation_engine import ValidatorRun
from idml_foundation.release.xpm import XpmAttestation, XpmReportParser
from idml_foundation.release.xpm_compatibility import IMAGE, TOOL_SHA256
from idml_foundation.release.xpm_query_semantics import QueryEvidence, assess_queries
from idml_foundation.services.validation_scope import validate_scope
from idml_foundation.services.xpm_runtime_compatibility import (
    WaytaExecutionEvidence,
    assess_runtime_compatibility,
)


class XpmExecutionEvidence(StrictModel):
    scope: dict[str, str]
    report: bytes
    attestation: XpmAttestation
    image: str
    required_queries_complete: StrictBool
    query_evidence: QueryEvidence | None = None
    wayta_evidence: WaytaExecutionEvidence | None = None


XpmExecutor = Callable[[bytes, dict[str, str]], XpmExecutionEvidence]


def assess_xpm_execution(
    *,
    xml: bytes,
    package: bytes,
    expected_scope: dict[str, str] | None,
    executor: XpmExecutor | None,
    independent_runs: tuple[ValidatorRun, ...] = (),
) -> dict[str, Any]:
    unavailable = {
        "status": "unavailable",
        "attested": False,
        "failure_code": "xpm-executor-not-configured",
    }
    if executor is None:
        return unavailable
    try:
        scope = validate_scope(expected_scope or {})
        if (
            hashlib.sha256(xml).hexdigest() != scope["xml_sha256"]
            or hashlib.sha256(package).hexdigest() != scope["package_sha256"]
            or not 0 < len(xml) <= 8 * 1024**2
            or not 0 < len(package) <= 100 * 1024**2
        ):
            raise ValueError("candidate_mismatch")
        # Verify the XML sent to modern validators is the sole XML inside this ZIP.
        with ZipFile(BytesIO(package)) as archive:
            entries = archive.infolist()
            names = [item.filename for item in entries]
            xml_entries = [item for item in entries if item.filename.lower().endswith(".xml")]
            if (
                len(entries) > 500
                or len({name.casefold() for name in names}) != len(names)
                or any("/" in n or "\\" in n or ":" in n or n in {".", ".."} for n in names)
                or len(xml_entries) != 1
                or xml_entries[0].file_size != len(xml)
                or archive.read(xml_entries[0]) != xml
            ):
                raise ValueError("package_mismatch")
        # Revalidate even model_copy/model_construct results; never trust a passed flag.
        response = executor(package, dict(scope))
        evidence = XpmExecutionEvidence.model_validate(
            response.model_dump(mode="python", warnings=False)
        )
        attestation = evidence.attestation
        if (
            validate_scope(evidence.scope) != scope
            or evidence.image != IMAGE
            or attestation.contract_version != "1.0.0"
            or attestation.tool_sha256 != TOOL_SHA256
            or attestation.xpm_version != "4.0.096"
            or attestation.candidate_package_sha256 != scope["package_sha256"]
        ):
            raise ValueError("execution_mismatch")
        parsed = XpmReportParser().parse_attested(evidence.report, attestation)
        result: dict[str, Any] = {
            "status": parsed.status.value,
            "attested": parsed.attested,
            "candidate_package_sha256": parsed.candidate_package_sha256,
            "report_sha256": parsed.report_sha256,
            "tool_sha256": parsed.tool_sha256,
            "xpm_version": parsed.xpm_version,
            "counts": {
                k: getattr(parsed, k)
                for k in ("blocking_errors", "fatal_errors", "errors", "warnings")
            },
            "parser_recovered": parsed.parser_recovered,
            "parser_errors": parsed.parser_errors,
            "required_queries_complete": evidence.required_queries_complete,
            "raw_passed": parsed.passed,
            "failure_code": None,
        }
        if evidence.query_evidence is not None:
            now = datetime.now(UTC)
            try:
                result["selected_queries"] = assess_queries(
                    xml=xml,
                    evidence=evidence.query_evidence,
                    scope=scope,
                    report_sha256=parsed.report_sha256 or "",
                    now=now,
                )
                result["compatibility"] = assess_runtime_compatibility(
                    xml=xml,
                    package=package,
                    report=evidence.report,
                    scope=scope,
                    image=evidence.image,
                    attestation=attestation,
                    queries=evidence.query_evidence,
                    selected=result["selected_queries"],
                    now=now,
                    independent_runs=independent_runs,
                    wayta=evidence.wayta_evidence,
                )
            except Exception:
                result["selected_queries"] = {
                    "status": "unavailable",
                    "reason": "query-evidence-invalid-or-unqualified",
                }
            result["required_queries_complete"] = False
        return result
    except Exception:
        # Tool exceptions, paths, HTML, commands and environment can contain private data.
        return unavailable | {"failure_code": "xpm-execution-failed-or-evidence-mismatch"}
