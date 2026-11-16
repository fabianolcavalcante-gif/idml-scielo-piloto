"""ADR-019 closed SPS/date rules layered over the unchanged DOI assessment.

Trusted evidence is produced by the supervised executor, never by an HTTP client
or AI. This contract cannot approve a release, DOCTYPE or incomplete web queries.
"""

import hashlib
import json
import re
from datetime import date, datetime, timedelta
from typing import Any, Literal

from lxml import etree, html
from pydantic import AwareDatetime, Field

from idml_foundation.domain.common import SHA256_PATTERN, StrictModel
from idml_foundation.release.validation_engine import ValidatorRun, ValidatorStatus
from idml_foundation.release.xpm_compatibility import (
    XpmCompatibilityAssessment,
    XpmCompatibilityEvidence,
    assess_xpm_compatibility,
)
from idml_foundation.services.validation_scope import scope_digest, validate_scope

VENDOR_FILES = {
    "xml/app_modules/app/data/article.py": (
        "2039be726993e759dfc2a322f6546d017e71b2658e740b4a61aa3f2d573e1b67"
    ),
    "xml/app_modules/app/data/attributes.py": (
        "0d6c8e27f64d6618b248a793c0689bdbd17a74e0d4f7a888bfe62d2620eb583d"
    ),
    "xml/app_modules/app/validations/article_content_validations.py": (
        "e0882113d47ee4fd64e2e4290e1e63d933c6324d6cf542f2f9323aedfc78c3b8"
    ),
}
VALIDATORS = {
    "packtools": (
        "4.17.2+ef0e6f874ea7",
        "4d5aadab7d75822c778890e1704e0533d9fc0578aed87034b128f20ec6da2eca",
        "xml_sha256",
    ),
    "spsvalidator": (
        "0.3.0+d1aa774d4e33",
        "61b90cc8ecca8de508c6cd19701551860de32f053a4899fd056835c8f05ab048",
        "package_sha256",
    ),
}
NORMATIVE_SOURCES = (
    "https://groups.google.com/g/scielo-xml/c/MJHQuqRwsgs",
    "https://groups.google.com/g/scielo-xml/c/KiC-TDlazJE",
)
DATE_MESSAGE = "@date-type is invalid for this version of SPS."
COMBINATION_MESSAGES = {
    "Invalid combination of date types: "
    + order
    + ". Expected values: 'epub-ppub', 'epub', 'collection', 'epub'."
    for order in ("pub | collection", "collection | pub")
}


class SpsCompatibilityEvidence(StrictModel):
    contract_version: Literal["xpm-sps-compatibility-evidence-1.0"]
    scope: dict[str, str]
    vendor_sha256: dict[str, str]
    independent_report_sha256: str = Field(pattern=SHA256_PATTERN)
    runs: tuple[ValidatorRun, ...] = Field(min_length=2, max_length=2)


class SpsRuntimeEvidence(StrictModel):
    """Current server invocation; individual validator report hashes stay intact."""

    contract_version: Literal["xpm-sps-runtime-evidence-2.0"]
    scope: dict[str, str]
    vendor_sha256: dict[str, str]
    xpm_report_sha256: str = Field(pattern=SHA256_PATTERN)
    assembled_at: AwareDatetime
    runs: tuple[ValidatorRun, ...] = Field(min_length=2, max_length=2)
    independent_report_sha256: str = Field(pattern=SHA256_PATTERN)


def runtime_digest(value: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()


def bind_runtime_runs(
    scope: dict[str, str], report_sha256: str, runs: tuple[ValidatorRun, ...], now: datetime
) -> SpsRuntimeEvidence:
    evidence = SpsRuntimeEvidence(
        contract_version="xpm-sps-runtime-evidence-2.0",
        scope=scope,
        vendor_sha256=VENDOR_FILES,
        xpm_report_sha256=report_sha256,
        assembled_at=now,
        runs=runs,
        independent_report_sha256="0" * 64,
    )
    return evidence.model_copy(
        update={
            "independent_report_sha256": runtime_digest(
                evidence.model_dump(mode="json", exclude={"independent_report_sha256"})
            )
        }
    )


class SpsCompatibilityException(StrictModel):
    rule_id: Literal[
        "xpm-sps110-version-table-1.0",
        "xpm-sps110-date-type-1.0",
        "xpm-sps110-date-combination-1.0",
    ]
    occurrence_sha256: str = Field(pattern=SHA256_PATTERN)
    original_severity: Literal["error", "blocking"]
    independent_report_sha256: str = Field(pattern=SHA256_PATTERN)
    normative_sources: tuple[str, ...] = NORMATIVE_SOURCES


class SpsCompatibilityAssessment(StrictModel):
    policy_version: Literal["xpm-homologation-sps-compatibility-1.0"]
    base: XpmCompatibilityAssessment
    exceptions: tuple[SpsCompatibilityException, ...]
    unresolved_counts: dict[str, int]
    reasons: tuple[str, ...]
    homologation_ready: Literal[False] = False
    release_approved: Literal[False] = False


def _text(node: etree._Element) -> str:
    return " ".join("".join(map(str, node.itertext())).split())


def _signature(node: etree._Element) -> tuple[object, ...]:
    return (
        node.tag,
        tuple(sorted(node.attrib.items())),
        (node.text or "").strip(),
        tuple((_signature(child), (child.tail or "").strip()) for child in node),
    )


def _snippet(node: etree._Element) -> str:
    # Original html_reports.format_xml inserts these exact markers for spaces.
    # Do not strip arbitrary middle dots or hidden/user-supplied text.
    if node.tag == "font":
        parent = node.getparent()
        if (
            {str(k): str(v) for k, v in node.attrib.items()} != {"color": "#F56991"}
            or node.text != "\u00b7"
            or len(node)
            or parent is None
            or parent.tag != "code"
        ):
            raise ValueError("unqualified_xpm_snippet_marker")
        return " "
    result = " " if node.tag == "br" else (node.text or "")
    return result + "".join(_snippet(child) + (child.tail or "") for child in node)


def qualified_publication_date(root: etree._Element, now: datetime) -> date | None:
    """Narrow full-date + annual collection profile; no inferred or corrected dates."""
    metas = root.findall("front/article-meta")
    if len(metas) != 1 or len(root.findall(".//pub-date")) != 2:
        return None
    nodes = metas[0].findall("pub-date")
    if len(nodes) != 2 or [n.get("date-type") for n in nodes] != ["pub", "collection"]:
        return None
    pub, collection = nodes
    # No AOP, legacy attributes, duplicate/extra children, markup, guessed precision.
    if (
        metas[0].findtext("issue") == "ahead"
        or not metas[0].findtext("volume")
        or set(pub.attrib) != {"date-type", "publication-format", "iso-8601-date"}
        or {str(k): str(v) for k, v in collection.attrib.items()}
        != {"date-type": "collection", "publication-format": "electronic"}
        or pub.get("publication-format") != "electronic"
        or [n.tag for n in pub] != ["day", "month", "year"]
        or [n.tag for n in collection] != ["year"]
        or any(
            n.attrib or len(n) or not re.fullmatch(r"[0-9]{1,4}", n.text or "")
            for parent in nodes
            for n in parent
        )
        or any(
            (parent.text or "").strip() or any((n.tail or "").strip() for n in parent)
            for parent in nodes
        )
    ):
        return None
    try:
        value = date(
            int(pub.findtext("year", "")),
            int(pub.findtext("month", "")),
            int(pub.findtext("day", "")),
        )
        if (
            pub.get("iso-8601-date") != value.isoformat()
            or collection.findtext("year") != str(value.year)
            or not date(2021, 4, 2) <= value <= now.date()
        ):
            return None
        return value
    except ValueError:
        return None


def _cells(row: etree._Element, severity: str, label: str) -> list[etree._Element] | None:
    cells = row.findall("td")
    if (
        [n.tag for n in row] != ["td"] * 4
        or [n.get("class") for n in cells] != ["td_label", "td_status", "td_message", "td_xml"]
        or any(n.tag not in {"tr", "td", "a", "code", "br", "font"} for n in row.iter())
        or any(n.tag in {"script", "style", "template"} for n in row.iterancestors())
        or _text(cells[0]) != label + " [?]"
        or not re.fullmatch(
            r"\[ERROR\] \[E[1-9]\d*\]"
            if severity == "error"
            else r"\[BLOCKING ERROR\] \[B[1-9]\d*\]",
            _text(cells[1]),
        )
    ):
        return None
    return cells


def assess_xpm_sps_compatibility(
    *,
    xml: bytes,
    package: bytes,
    report: bytes,
    crossref: bytes,
    trusted: XpmCompatibilityEvidence,
    expected_scope: dict[str, str],
    now: datetime,
    sps_evidence: SpsCompatibilityEvidence | SpsRuntimeEvidence,
) -> SpsCompatibilityAssessment:
    base = assess_xpm_compatibility(
        xml=xml,
        package=package,
        report=report,
        crossref=crossref,
        trusted=trusted,
        expected_scope=expected_scope,
        now=now,
    )
    scope = validate_scope(expected_scope)
    if len(sps_evidence.runs) != 2:
        raise ValueError("xpm_sps_independent_validation_missing")
    sps_evidence = type(sps_evidence).model_validate(
        sps_evidence.model_dump(mode="python", warnings=False)
    )
    runtime = isinstance(sps_evidence, SpsRuntimeEvidence)
    if isinstance(sps_evidence, SpsRuntimeEvidence) and (
        sps_evidence.xpm_report_sha256 != hashlib.sha256(report).hexdigest()
        or now.utcoffset() is None
        or not timedelta(0) <= now - sps_evidence.assembled_at <= timedelta(hours=24)
        or sps_evidence.independent_report_sha256
        != runtime_digest(
            sps_evidence.model_dump(mode="json", exclude={"independent_report_sha256"})
        )
        or len({r.sanitized_output_sha256 for r in sps_evidence.runs}) != 2
    ):
        raise ValueError("xpm_sps_runtime_binding_invalid")
    if (
        validate_scope(sps_evidence.scope) != scope
        or scope["journal_profile_id"] != "esa-aop-1.1.0"
        or sps_evidence.vendor_sha256 != VENDOR_FILES
    ):
        raise ValueError("xpm_sps_evidence_mismatch")
    if len({r.name for r in sps_evidence.runs}) != 2:
        raise ValueError("xpm_sps_independent_validation_missing")
    for run in sps_evidence.runs:
        expected = VALIDATORS.get(run.name)
        if (
            expected is None
            or run.version != expected[0]
            or run.tool_sha256 != expected[1]
            or run.candidate_sha256 != scope[expected[2]]
            or run.status != ValidatorStatus.COMPLETED
            or run.failure_code is not None
            or run.profile_id != "sps-1.10/jats-1.3"
            or run.adapter_contract != "1.1.0"
            or not run.sanitized_output_sha256
            or (
                not runtime
                and run.sanitized_output_sha256 != sps_evidence.independent_report_sha256
            )
            or not run.environment
            or any(issue.severity != "warning" for issue in run.issues)
        ):
            raise ValueError("xpm_sps_independent_validation_failed")
    if scope_digest(scope) != base.scope_sha256:
        raise ValueError("xpm_sps_scope_mismatch")
    root = etree.fromstring(
        xml, etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True)
    )
    publication_date = qualified_publication_date(root, now)
    exceptions: list[SpsCompatibilityException] = []

    def add(row: etree._Element, rule: str, severity: str) -> None:
        exceptions.append(
            SpsCompatibilityException.model_validate(
                {
                    "rule_id": rule,
                    "original_severity": severity,
                    "occurrence_sha256": hashlib.sha256(
                        etree.tostring(row, method="c14n")
                    ).hexdigest(),
                    "independent_report_sha256": sps_evidence.independent_report_sha256,
                }
            )
        )

    if publication_date is not None:
        doc = html.fromstring(report.decode("utf-8"), parser=html.HTMLParser(no_network=True))
        sps_rows, date_rows, combo_rows = [], [], []
        expected_message = (
            f"For articles published on {publication_date:%d/%m/%Y}, sps-1.10 is not valid. "
            "Expected SPS versions for this article: sps-1.8 or sps-1.9."
        )
        expected_dates = {_signature(n) for n in root.findall("front/article-meta/pub-date")}
        for row in doc.iter("tr"):
            kind = row.get("class")
            if kind == "error":
                cells = _cells(row, "error", "article/@specific-use")
                if (
                    cells is not None
                    and _text(cells[2]) == expected_message
                    and not _text(cells[3])
                ):
                    sps_rows.append(row)
            elif kind == "blockingerror":
                cells = _cells(row, "blocking", "pub-date")
                if cells is None:
                    continue
                if _text(cells[2]) == DATE_MESSAGE:
                    try:
                        snippet = " ".join(_snippet(cells[3]).split())
                        if "<!" in snippet or len(snippet) > 4096:
                            continue
                        node = etree.fromstring(
                            snippet.encode(),
                            etree.XMLParser(
                                resolve_entities=False, load_dtd=False, no_network=True
                            ),
                        )
                    except (etree.XMLSyntaxError, ValueError):
                        continue
                    date_rows.append((row, _signature(node)))
                elif _text(cells[2]) in COMBINATION_MESSAGES and not _text(cells[3]):
                    combo_rows.append(row)
        if len(sps_rows) == 1:
            add(sps_rows[0], "xpm-sps110-version-table-1.0", "error")
        # Treat the three related rows atomically; duplicates/missing/wrong snippets fail closed.
        if (
            len(date_rows) == 2
            and {s for _, s in date_rows} == expected_dates
            and len(combo_rows) == 1
        ):
            for row, _ in date_rows:
                add(row, "xpm-sps110-date-type-1.0", "blocking")
            add(combo_rows[0], "xpm-sps110-date-combination-1.0", "blocking")
    counts = dict(base.unresolved_counts)
    for exception in exceptions:
        counts["errors" if exception.original_severity == "error" else "blocking_errors"] -= 1
    if min(counts.values()) < 0 or len({e.occurrence_sha256 for e in exceptions}) != len(
        exceptions
    ):
        raise ValueError("xpm_sps_occurrence_ambiguous")
    reasons = list(base.reasons)
    reasons.append("doctype-jats-decision-pending")
    if publication_date is None:
        reasons.append("publication-date-profile-not-qualified")
    return SpsCompatibilityAssessment(
        policy_version="xpm-homologation-sps-compatibility-1.0",
        base=base,
        exceptions=tuple(exceptions),
        unresolved_counts=counts,
        reasons=tuple(reasons),
    )
