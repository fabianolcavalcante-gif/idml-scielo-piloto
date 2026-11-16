"""Narrow ADR-019 legacy capability exceptions, never publication approval."""

import hashlib
import re
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Literal
from zipfile import ZipFile

from lxml import etree, html
from pydantic import Field

from idml_foundation.domain.common import SHA256_PATTERN, StrictModel
from idml_foundation.pipeline.jats_builder import JATS_DTD_NAME, JATS_PUBLIC_ID
from idml_foundation.pipeline.validation import OfflineJatsValidator
from idml_foundation.release.xpm_compatibility import XpmCompatibilityEvidence
from idml_foundation.release.xpm_sps_compatibility import (
    SpsCompatibilityAssessment,
    SpsRuntimeEvidence,
    _snippet,
    assess_xpm_sps_compatibility,
)

NATIVE_QUALIFICATION_SHA256 = "749ca09175041e1e8def1a32034f90e726aef44a3d935bc42bde4ff5be80a6aa"
FN_VALUES = (
    "abbr com con conflict corresp current-aff deceased edited-by equal financial-disclosure "
    "on-leave participating-researchers presented-at presented-by present-address previously-at "
    "study-group-members supplementary-material supported-by other "
)
ROOT_MESSAGE = 'Attribute "dtd-version" with value "1.3" must have a value of "1.1".'
FN_MESSAGE = (
    f'Attribute "fn-type" with value "coi-statement" must have a value from the list "{FN_VALUES}".'
)


class StructuralException(StrictModel):
    rule_id: Literal["xpm-jats13-legacy-dtd-1.0", "xpm-sps110-style-unavailable-1.0"]
    original_severity: Literal["fatal", "error"]
    occurrence_sha256: str = Field(pattern=SHA256_PATTERN)
    independent_report_sha256: str = Field(pattern=SHA256_PATTERN)
    native_qualification_sha256: str = NATIVE_QUALIFICATION_SHA256


class StructuralAssessment(StrictModel):
    policy_version: Literal["xpm-homologation-structural-compatibility-1.0"]
    base: SpsCompatibilityAssessment
    exceptions: tuple[StructuralException, ...]
    unresolved_counts: dict[str, int]
    technical_errors_resolved: bool
    reasons: tuple[str, ...]
    homologation_ready: Literal[False] = False
    release_approved: Literal[False] = False


def _normalized(text: str) -> str:
    return " ".join(text.split())


def structural_occurrences(report: bytes, root: etree._Element, filename: str) -> tuple[str, str]:
    """Recognize the complete native diagnostic prefix, not strings inside article text.

    Only called after attestation, scope and XML/package validation. The vendor
    embeds the article after its diagnostic prefix; that text is not evidence.
    """
    doc = html.fromstring(report.decode("utf-8"), parser=html.HTMLParser(no_network=True))
    blocks = doc.findall('.//div[@class="report-block-xmlrep"]')
    if len(blocks) != 1:
        raise ValueError("xpm_structural_block_ambiguous")
    block = blocks[0]
    parent = block.getparent()
    if (
        parent is None
        or {str(k): str(v) for k, v in block.attrib.items()}
        != {"class": "report-block-xmlrep", "id": "xmlrep" + filename[:-4]}
        or parent.tag != "td"
        or parent.get("class") != "reports-hidden-block"
        or any(a.tag in {"script", "style", "template", "code"} for a in block.iterancestors())
    ):
        raise ValueError("xpm_structural_block_context")
    # DTD diagnostics in this pinned vendor consist solely of direct text and br tails.
    prefix = block.text or ""
    for child in block:
        if child.tag != "br":
            break
        if child.attrib or len(child) or child.text:
            raise ValueError("xpm_structural_diagnostic_markup")
        prefix += child.tail or ""
        if "Parse/validation finished" in prefix:
            break
    if "Parse/validation finished" not in prefix:
        raise ValueError("xpm_structural_diagnostic_missing")
    prefix = _normalized(prefix.split("Parse/validation finished", 1)[0])
    header = (
        "Summary-------[FATAL ERROR] [F1] XML file has DTD errors.........DTD errors----------"
        f'Found: <!DOCTYPE article PUBLIC "{JATS_PUBLIC_ID}" "{JATS_DTD_NAME}">'
        f"Unknown PUBLIC ID: {JATS_PUBLIC_ID}"
    )
    pattern = re.escape(_normalized(header))
    nodes = [root, *root.findall('.//fn[@fn-type="coi-statement"]')]
    for node in nodes:
        message = ROOT_MESSAGE if node is root else FN_MESSAGE
        diagnostic = (
            "Error: Public ID: null "
            f"System ID: file:/work/SciELO_XPM/xml/./{filename} "
            "Line number: "
        )
        # The vendor pretty-prints its private working copy before DTD validation;
        # its coordinates do not refer to the unchanged submitted XML lines.
        pattern += (
            re.escape(diagnostic)
            + r"[1-9][0-9]* Column number: [1-9][0-9]*"
            + re.escape(" Message: " + message)
        )
    if re.fullmatch(pattern, prefix) is None:
        raise ValueError("xpm_structural_diagnostic_unqualified")
    headings = block.findall("./h1")
    errors = block.findall('./div[@class="error"]')
    codes = block.findall("./code")
    if (
        len(headings) != 1
        or headings[0].attrib
        or len(headings[0])
        or headings[0].text != "Packtools Style Checker (2.4.2)"
        or len(errors) != 1
        or {str(k): str(v) for k, v in errors[0].attrib.items()} != {"class": "error"}
        or len(errors[0])
        or errors[0].text != "Total of errors = 1"
        or len(codes) != 1
        or codes[0].attrib
        or any(n.tag not in {"code", "font", "br"} for n in codes[0].iter())
    ):
        raise ValueError("xpm_structural_style_ambiguous")
    style = _normalized(_snippet(codes[0]))
    if style != (
        f"Something went wrong while working on /work/input_xpm/scielo_package/{filename}: "
        'version "sps-1.10" is not currently supported.'
    ):
        raise ValueError("xpm_structural_style_unqualified")
    return hashlib.sha256(prefix.encode()).hexdigest(), hashlib.sha256(style.encode()).hexdigest()


def assess_xpm_structural_compatibility(
    *,
    xml: bytes,
    package: bytes,
    report: bytes,
    crossref: bytes,
    trusted: XpmCompatibilityEvidence,
    expected_scope: dict[str, str],
    now: datetime,
    sps_evidence: SpsRuntimeEvidence,
) -> StructuralAssessment:
    if not isinstance(sps_evidence, SpsRuntimeEvidence):
        raise ValueError("xpm_structural_current_evidence_required")
    base = assess_xpm_sps_compatibility(
        xml=xml,
        package=package,
        report=report,
        crossref=crossref,
        trusted=trusted,
        expected_scope=expected_scope,
        now=now,
        sps_evidence=sps_evidence,
    )
    # The base already checks ZIP safety, size, sole XML and exact byte bindings.
    with ZipFile(BytesIO(package)) as archive:
        names = set(archive.namelist())
    filename = next(n for n in names if n.lower().endswith(".xml"))
    validation = OfflineJatsValidator(
        Path(__file__).resolve().parents[3] / "vendor/jats/1.3"
    ).validate(xml, asset_names=names)
    if not validation.valid:
        raise ValueError("xpm_structural_offline_validation_failed")
    root = etree.fromstring(
        xml, etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True)
    )
    dtd, style = structural_occurrences(report, root, filename)
    exceptions = (
        StructuralException(
            rule_id="xpm-jats13-legacy-dtd-1.0",
            original_severity="fatal",
            occurrence_sha256=dtd,
            independent_report_sha256=sps_evidence.independent_report_sha256,
        ),
        StructuralException(
            rule_id="xpm-sps110-style-unavailable-1.0",
            original_severity="error",
            occurrence_sha256=style,
            independent_report_sha256=sps_evidence.independent_report_sha256,
        ),
    )
    counts = dict(base.unresolved_counts)
    counts["fatal_errors"] -= 1
    counts["errors"] -= 1
    if min(counts.values()) < 0:
        raise ValueError("xpm_structural_occurrence_count_invalid")
    resolved = all(counts[k] == 0 for k in ("blocking_errors", "fatal_errors", "errors"))
    reasons = tuple(r for r in base.reasons if r != "doctype-jats-decision-pending")
    return StructuralAssessment(
        policy_version="xpm-homologation-structural-compatibility-1.0",
        base=base,
        exceptions=exceptions,
        unresolved_counts=counts,
        technical_errors_resolved=resolved,
        reasons=(
            *reasons,
            "delivery-doctype-policy-pending",
            "warnings-and-queries-review-required",
        ),
    )
