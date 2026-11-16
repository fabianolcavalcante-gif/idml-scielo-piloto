from __future__ import annotations

import hashlib
import re
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any, cast
from urllib.parse import urlparse

from lxml import etree
from pydantic import Field

from idml_foundation.domain.common import SHA256_PATTERN, StrictModel
from idml_foundation.mathml import MATHML_NS
from idml_foundation.pipeline.jats_builder import (
    JATS_DTD_NAME,
    JATS_PUBLIC_ID,
    XLINK_NS,
    XML_NS,
)

_XML_DECLARATION = re.compile(rb'^<\?xml version=["\']1\.0["\'] encoding=["\']UTF-8["\']\?>')
_LANGUAGE = re.compile(r"^[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")
_ISSN = re.compile(r"^\d{4}-\d{3}[\dXx]$")
_DOI = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)
_INVISIBLE_CHARACTERS = frozenset(
    {
        "\ufeff",
        "\u200b",
        "\u2060",
        *(chr(value) for value in range(0x202A, 0x202F)),
        *(chr(value) for value in range(0x2066, 0x206A)),
    }
)


class ValidationSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


class ValidationStage(StrEnum):
    XML = "xml"
    JATS_DTD = "jats-dtd"
    SPS_BASELINE = "sps-baseline"


class ValidationIssue(StrictModel):
    stage: ValidationStage
    severity: ValidationSeverity
    code: str
    message: str
    line: int | None = Field(default=None, ge=1)
    element_id: str | None = None


class ValidationReport(StrictModel):
    report_version: str = "1.1.0"
    validator_profile: str = "jats-1.3-mathml3+sps-baseline-1.2.0"
    xml_sha256: str = Field(pattern=SHA256_PATTERN)
    valid: bool
    issues: tuple[ValidationIssue, ...]


class OfflineJatsValidator:
    def __init__(self, vendor_directory: Path) -> None:
        vendor_root = vendor_directory.resolve(strict=True)
        dtd_path = (vendor_root / JATS_DTD_NAME).resolve(strict=True)
        if not dtd_path.is_relative_to(vendor_root):
            raise ValueError("JATS DTD must remain inside the allowlisted vendor directory")
        self._dtd = etree.DTD(str(dtd_path))

    def validate(self, xml: bytes, *, asset_names: set[str] | None = None) -> ValidationReport:
        digest = hashlib.sha256(xml).hexdigest()
        issues: list[ValidationIssue] = []
        parser = etree.XMLParser(
            resolve_entities=False,
            load_dtd=False,
            no_network=True,
            recover=False,
            huge_tree=False,
        )
        try:
            root = etree.fromstring(xml, parser=parser)
        except etree.XMLSyntaxError as exc:
            issues.append(
                ValidationIssue(
                    stage=ValidationStage.XML,
                    severity=ValidationSeverity.ERROR,
                    code="xml-not-well-formed",
                    message=str(exc),
                    line=max(exc.lineno or 1, 1),
                )
            )
            return ValidationReport(xml_sha256=digest, valid=False, issues=tuple(issues))

        document = cast(Any, root.getroottree().docinfo)
        if xml.startswith(b"\xef\xbb\xbf") or not _XML_DECLARATION.match(xml):
            issues.append(
                ValidationIssue(
                    stage=ValidationStage.XML,
                    severity=ValidationSeverity.ERROR,
                    code="invalid-xml-declaration",
                    message="XML must start with an unambiguous UTF-8 declaration and no BOM",
                )
            )
        if document.public_id != JATS_PUBLIC_ID or document.system_url != JATS_DTD_NAME:
            issues.append(
                ValidationIssue(
                    stage=ValidationStage.JATS_DTD,
                    severity=ValidationSeverity.ERROR,
                    code="unexpected-doctype",
                    message=(
                        "DOCTYPE PUBLIC and SYSTEM identifiers must both identify the pinned "
                        "JATS Publishing 1.3 with MathML3 DTD"
                    ),
                )
            )

        if not self._dtd.validate(root):
            error_log = cast(Any, self._dtd.error_log)
            for error in error_log:
                issues.append(
                    ValidationIssue(
                        stage=ValidationStage.JATS_DTD,
                        severity=ValidationSeverity.ERROR,
                        code=f"dtd-{error.type_name.casefold().replace('_', '-')}",
                        message=error.message,
                        line=max(error.line, 1),
                    )
                )
        issues.extend(self._sps_baseline(root, asset_names or set()))
        issues.sort(key=lambda item: (item.severity, item.stage, item.code, item.line or 0))
        return ValidationReport(
            xml_sha256=digest,
            valid=not any(item.severity == ValidationSeverity.ERROR for item in issues),
            issues=tuple(issues),
        )

    def _sps_baseline(
        self,
        root: etree._Element,
        asset_names: set[str],
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []

        def problem(
            code: str,
            message: str,
            *,
            severity: ValidationSeverity = ValidationSeverity.ERROR,
            element_id: str | None = None,
        ) -> None:
            issues.append(
                ValidationIssue(
                    stage=ValidationStage.SPS_BASELINE,
                    severity=severity,
                    code=code,
                    message=message,
                    element_id=element_id,
                )
            )

        def require(xpath: str, code: str, message: str) -> None:
            if not root.xpath(xpath):
                problem(code, message)

        if root.tag != "article" or root.get("dtd-version") != "1.3":
            problem("unsupported-jats-version", "article must declare JATS dtd-version 1.3")
        if root.get("specific-use") != "sps-1.10":
            problem("unsupported-sps-version", "article must declare specific-use sps-1.10")
        language = root.get(f"{{{XML_NS}}}lang", "")
        if not _LANGUAGE.fullmatch(language):
            problem("invalid-primary-language", "article xml:lang must be a valid language tag")
        if root.nsmap.get("xlink") != XLINK_NS or root.nsmap.get("mml") != MATHML_NS:
            problem(
                "missing-required-namespaces",
                "article must declare the pinned XLink and MathML namespaces",
            )
        if not (root.get("article-type") or "").strip():
            problem("missing-article-type", "article-type is required")
        require("front", "missing-front", "front matter is required")
        require("body", "missing-body", "article body is required")
        require(
            "front/journal-meta/journal-id[@journal-id-type='publisher-id'][normalize-space()]",
            "missing-journal-id",
            "publisher journal ID is required",
        )
        require(
            "front/journal-meta/journal-title-group/journal-title[normalize-space()]",
            "missing-journal-title",
            "journal title is required",
        )
        require(
            "front/journal-meta/issn[normalize-space()]",
            "missing-issn",
            "at least one ISSN is required",
        )
        require(
            "front/article-meta/article-categories/subj-group/subject[normalize-space()]",
            "missing-article-category",
            "article category is required",
        )
        require(
            "front/article-meta/article-id[(@pub-id-type='publisher-id' or "
            "@pub-id-type='other') and normalize-space()]",
            "missing-publisher-id",
            "publisher article ID is required",
        )
        require(
            "front/article-meta/title-group/article-title[normalize-space()]",
            "missing-article-title",
            "primary article title is required",
        )
        publisher_ids = cast(
            list[etree._Element],
            root.xpath(
                "front/article-meta/article-id[(@pub-id-type='publisher-id' or "
                "@pub-id-type='other') and normalize-space()]"
            ),
        )
        if len(publisher_ids) > 1:
            problem("duplicate-publisher-id", "exactly one publisher article ID is allowed")
        for issn in cast(list[etree._Element], root.xpath("front/journal-meta/issn")):
            if not _ISSN.fullmatch("".join(cast(Any, issn).itertext()).strip()):
                problem("invalid-issn", "ISSN must use the NNNN-NNNX syntax")
        for doi in cast(
            list[etree._Element],
            root.xpath("//article-id[@pub-id-type='doi'] | //pub-id[@pub-id-type='doi']"),
        ):
            if not _DOI.fullmatch("".join(cast(Any, doi).itertext()).strip()):
                problem("invalid-doi", "DOI does not follow the registered 10.xxxx/suffix syntax")

        id_values = [element.get("id", "") for element in root.iter() if element.get("id")]
        elements_by_id = {
            element.get("id", ""): element for element in root.iter() if element.get("id")
        }
        if len(id_values) != len(set(id_values)):
            problem("duplicate-xml-id", "XML IDs must be unique")
        bibliography_rids: set[str] = set()
        target_tags = {
            "aff": {"aff"},
            "bibr": {"ref"},
            "corresp": {"corresp"},
            "disp-formula": {"disp-formula"},
            "fig": {"fig"},
            "fn": {"fn"},
            "sec": {"sec"},
            "table": {"table-wrap"},
        }
        for xref in (element for element in root.iter() if element.get("rid")):
            rid_values = str(xref.get("rid")).split()
            ref_type = xref.get("ref-type", "")
            if xref.tag == "xref" and ref_type not in {*target_tags, "other"}:
                problem("invalid-xref-type", "xref ref-type is absent or unsupported")
            if ref_type == "bibr":
                bibliography_rids.update(rid_values)
            for rid in rid_values:
                target = elements_by_id.get(rid)
                if target is None:
                    problem(
                        "orphan-rid",
                        "cross-reference RID does not resolve",
                        element_id=xref.get("id"),
                    )
                elif ref_type in target_tags and target.tag not in target_tags[ref_type]:
                    code = (
                        "invalid-bibliography-rid-target"
                        if ref_type == "bibr"
                        else "invalid-xref-target"
                    )
                    problem(
                        code,
                        f"{ref_type} RID targets an incompatible element",
                        element_id=xref.get("id"),
                    )
        for reference in root.iter("ref"):
            reference_id = reference.get("id")
            if reference_id and reference_id not in bibliography_rids:
                problem(
                    "uncited-reference",
                    "reference is not targeted by a bibliographic cross-reference",
                    severity=ValidationSeverity.WARNING,
                    element_id=reference_id,
                )

        for graphic in (
            element for element in root.iter() if element.tag in {"graphic", "inline-graphic"}
        ):
            href = graphic.get(f"{{{XLINK_NS}}}href", "")
            if not href or PurePosixPath(href.replace("\\", "/")).name != href or "://" in href:
                problem(
                    "unsafe-asset-reference",
                    "asset references must be non-empty package-local basenames",
                )
            elif asset_names and href not in asset_names:
                problem(
                    "unknown-asset-reference",
                    "graphic reference is absent from the canonical asset set",
                )

        for link in root.iter("ext-link"):
            href = link.get(f"{{{XLINK_NS}}}href", "")
            parsed = urlparse(href)
            if parsed.scheme.casefold() not in {"http", "https", "mailto"}:
                problem(
                    "unsafe-external-link",
                    "external links must use http, https, or mailto",
                )
        for element in root.iter():
            values = (element.text or "", element.tail or "")
            if any(character in _INVISIBLE_CHARACTERS for value in values for character in value):
                problem(
                    "forbidden-invisible-character",
                    "XML text contains a zero-width or bidirectional control character",
                    element_id=element.get("id"),
                )
                break
        return issues
