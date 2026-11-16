"""ADR-019 first rules: exact DOI title matches, with raw XPM and release untouched.

Inputs marked trusted must originate in the server-side executor/authority manifests,
not HTTP request bodies or model output. This module grants no publication or G-HOMOLOG.
"""

import hashlib
import re
from datetime import datetime
from io import BytesIO
from typing import Literal
from zipfile import ZipFile

from lxml import etree, html
from pydantic import AwareDatetime, Field

from idml_foundation.domain.common import SHA256_PATTERN, StrictModel
from idml_foundation.release.doi_snapshot import bind_doi_snapshot
from idml_foundation.release.xpm import XpmAttestation, XpmReportParser, XpmResult
from idml_foundation.services.validation_scope import scope_digest, validate_scope

TOOL_SHA256 = "1b22157b9e816255db8d8910acc46a13b78c0f286cbb68155a39a95ed0f0bdec"
IMAGE = "sha256:43ca49864959e4106d7cbb571f6f64a1222f9865068fee1ce61953aa19886d63"
VENDOR_COMPARISON_SHA256 = "e07eb281a1d4cd9b9eefae23e530c26b340bd4f78d57799596605f0ef0038d3a"


class XpmCompatibilityEvidence(StrictModel):
    contract_version: Literal["xpm-compatibility-evidence-1.0"]
    scope: dict[str, str]
    attestation: XpmAttestation
    image: str
    vendor_comparison_sha256: str = Field(pattern=SHA256_PATTERN)
    crossref_sha256: str = Field(pattern=SHA256_PATTERN)
    crossref_retrieved_at: AwareDatetime
    required_queries_complete: bool


class XpmCompatibilityException(StrictModel):
    rule_id: Literal["xpm-doi-journal-exact-1.0", "xpm-doi-article-exact-1.0"]
    occurrence_sha256: str = Field(pattern=SHA256_PATTERN)
    crossref_sha256: str = Field(pattern=SHA256_PATTERN)
    original_severity: Literal["error"] = "error"


class XpmCompatibilityAssessment(StrictModel):
    policy_version: Literal["xpm-homologation-compatibility-1.0"]
    scope_sha256: str = Field(pattern=SHA256_PATTERN)
    original: XpmResult
    exceptions: tuple[XpmCompatibilityException, ...]
    unresolved_counts: dict[str, int]
    reasons: tuple[str, ...]
    # Only two DOI rules are qualified in this increment; never an overall readiness decision.
    homologation_ready: Literal[False] = False
    release_approved: Literal[False] = False


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _text(value: str) -> str:
    return " ".join(value.split())


def assess_xpm_compatibility(
    *,
    xml: bytes,
    package: bytes,
    report: bytes,
    crossref: bytes,
    trusted: XpmCompatibilityEvidence,
    expected_scope: dict[str, str],
    now: datetime,
) -> XpmCompatibilityAssessment:
    scope = validate_scope(expected_scope)
    if validate_scope(trusted.scope) != scope:
        raise ValueError("xpm_compatibility_scope_mismatch")
    if (
        trusted.image != IMAGE
        or trusted.vendor_comparison_sha256 != VENDOR_COMPARISON_SHA256
        or trusted.attestation.tool_sha256 != TOOL_SHA256
        or trusted.attestation.xpm_version != "4.0.096"
    ):
        raise ValueError("xpm_compatibility_unqualified_tool")
    if (
        not 0 < len(package) <= 100 * 1024**2
        or not 0 < len(xml) <= 8 * 1024**2
        or _sha(package) != scope["package_sha256"]
        or _sha(xml) != scope["xml_sha256"]
        or trusted.attestation.candidate_package_sha256 != scope["package_sha256"]
    ):
        raise ValueError("xpm_compatibility_candidate_mismatch")
    with ZipFile(BytesIO(package)) as archive:
        members = archive.infolist()
        names = [n.filename for n in members]
        if (
            len(members) > 500
            or len({n.casefold() for n in names}) != len(names)
            or any("/" in n or "\\" in n or ":" in n or n in {".", ".."} for n in names)
        ):
            raise ValueError("xpm_compatibility_package_invalid")
        entries = [n for n in members if n.filename.endswith(".xml")]
        if len(entries) != 1 or entries[0].file_size != len(xml) or archive.read(entries[0]) != xml:
            raise ValueError("xpm_compatibility_package_xml_mismatch")
    if b"<!ENTITY" in xml.upper():
        raise ValueError("xpm_compatibility_unsafe_xml")
    root = etree.fromstring(
        xml, etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True)
    )
    if (
        root.tag != "article"
        or root.get("specific-use") != "sps-1.10"
        or root.get("dtd-version") != "1.3"
        or any(isinstance(n, etree._Entity) for n in root.iter())
    ):
        raise ValueError("xpm_compatibility_unqualified_profile")
    original = XpmReportParser().parse_attested(report, trusted.attestation)
    snapshot = bind_doi_snapshot(
        candidate=xml,
        snapshot=crossref,
        expected_candidate_sha256=scope["xml_sha256"],
        expected_snapshot_sha256=trusted.crossref_sha256,
        retrieved_at=trusted.crossref_retrieved_at,
        now=now,
    )
    message = snapshot.lookup(snapshot.doi, candidate_sha256=scope["xml_sha256"], now=now)[
        "message"
    ]
    doc = html.fromstring(report.decode("utf-8"), parser=html.HTMLParser(no_network=True))
    rows = [n for n in doc.iter("tr") if n.get("class") == "error"]
    exceptions = []
    for kind, path, source_field in (
        ("journal", "front/journal-meta/journal-title-group/journal-title", "container-title"),
        ("article", "front/article-meta/title-group/article-title", "title"),
    ):
        nodes, titles = root.findall(path), message.get(source_field)
        if (
            len(nodes) != 1
            or not isinstance(titles, list)
            or len(titles) != 1
            or not isinstance(titles[0], str)
            or not titles[0].strip()
            or _text("".join(map(str, nodes[0].itertext()))) != _text(titles[0])
        ):
            continue
        expected_message = _text(f"{snapshot.doi} is registered as belonging to {titles[0]}. ")
        matches = []
        for row in rows:
            cells = row.findall("td")
            if len(cells) != 4 or [n.get("class") for n in cells] != [
                "td_label",
                "td_status",
                "td_message",
                "td_xml",
            ]:
                continue
            if any(n.tag in {"script", "style", "template"} for n in row.iter()):
                continue
            if (
                _text("".join(map(str, cells[0].itertext()))) == "doi [?]"
                and re.fullmatch(
                    r"\[ERROR\] \[E[1-9]\d*\]", _text("".join(map(str, cells[1].itertext())))
                )
                and _text("".join(map(str, cells[2].itertext()))) == expected_message
                and not "".join(map(str, cells[3].itertext())).strip()
            ):
                matches.append(row)
        if len(matches) == 1:
            exceptions.append(
                XpmCompatibilityException(
                    rule_id="xpm-doi-journal-exact-1.0"
                    if kind == "journal"
                    else "xpm-doi-article-exact-1.0",
                    occurrence_sha256=_sha(etree.tostring(matches[0], method="c14n")),
                    crossref_sha256=trusted.crossref_sha256,
                )
            )
    if (
        len({e.occurrence_sha256 for e in exceptions}) != len(exceptions)
        or len(exceptions) > original.errors
    ):
        raise ValueError("xpm_compatibility_occurrence_ambiguous")
    counts = {
        k: getattr(original, k) for k in ("blocking_errors", "fatal_errors", "errors", "warnings")
    }
    counts["errors"] -= len(exceptions)
    reasons = ["compatibility-qualification-incomplete"]
    if not trusted.required_queries_complete:
        reasons.append("required-queries-incomplete")
    if any(counts.values()):
        reasons.append("unresolved-xpm-findings")
    return XpmCompatibilityAssessment(
        policy_version="xpm-homologation-compatibility-1.0",
        scope_sha256=scope_digest(scope),
        original=original,
        exceptions=tuple(exceptions),
        unresolved_counts=counts,
        reasons=tuple(reasons),
    )
