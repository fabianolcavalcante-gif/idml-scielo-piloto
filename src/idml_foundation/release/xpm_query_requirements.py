"""Qualified Wayta applicability, not an external-query success or release waiver.

Server-only evidence: the supervised executor must verify artifacts and provenance.
Neither an API client nor an AI response can supply trusted evidence. This increment
does not integrate the contract into the live worker or change ReleasePolicy.
"""

from datetime import datetime, timedelta
from typing import Literal, Self

from lxml import etree
from pydantic import Field, model_validator

from idml_foundation.domain.common import SHA256_PATTERN, StrictModel
from idml_foundation.release.xpm_compatibility import XpmCompatibilityEvidence
from idml_foundation.release.xpm_sps_compatibility import (
    SpsCompatibilityAssessment,
    SpsCompatibilityEvidence,
    SpsRuntimeEvidence,
    assess_xpm_sps_compatibility,
)
from idml_foundation.services.validation_scope import validate_scope

ENDPOINT = "https://wayta.scielo.org/api/v1/institution"
NORMATIVE_SHA256 = "09ade688acbf1aa6c48324b660bf4baeb9293c92ff315a2d68c371251909bbef"
NATIVE_PROOF_SHA256 = "144d937523f966751d2ce73300131c1fbde1e6e380cbd1ad5de022e411459802"
VENDOR_FILES = {
    "xml/app_modules/app/ws/ws_institutions.py": (
        "fde363c6461aa3a2f7e52f8de1e0300934b8d1cfc5d321beed6583f583f9807c"
    ),
    "xml/app_modules/app/validations/article_content_validations.py": (
        "e0882113d47ee4fd64e2e4290e1e63d933c6324d6cf542f2f9323aedfc78c3b8"
    ),
}
# Qualification boundary of ESA 1.1, not a replacement for the ISO registry.
COUNTRIES = {"BR": {"Brazil", "Brasil"}, "IN": {"India"}, "JP": {"Japan"}}


class WaytaServiceObservation(StrictModel):
    contract_version: Literal["wayta-service-observation-1.0"]
    endpoint: Literal["https://wayta.scielo.org/api/v1/institution"]
    observed_at: datetime
    outcome: Literal[
        "blocked_address",
        "http_response",
        "response_too_large",
        "dns_error",
        "timeout",
        "tls_error",
        "connection_error",
    ]
    http_status: int | None = Field(default=None, ge=100, le=599, strict=True)
    response_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    public_addresses: int = Field(ge=0, le=64, strict=True)
    article_query_performed: Literal[False] = False
    semantic_result_validated: Literal[False] = False
    elapsed_seconds: float = Field(ge=0, le=60, allow_inf_nan=False)

    @model_validator(mode="after")
    def coherent_observation(self) -> Self:
        if self.observed_at.utcoffset() is None:
            raise ValueError("wayta_observation_timezone_required")
        if self.outcome == "http_response":
            if self.http_status is None or self.response_sha256 is None:
                raise ValueError("wayta_http_evidence_missing")
        elif self.http_status is not None or self.response_sha256 is not None:
            raise ValueError("wayta_transport_failure_is_not_http_response")
        if (self.outcome in {"blocked_address", "dns_error"}) != (self.public_addresses == 0):
            raise ValueError("wayta_address_evidence_inconsistent")
        return self


class WaytaRequirementEvidence(StrictModel):
    contract_version: Literal["wayta-requirement-evidence-1.0"]
    scope: dict[str, str]
    normative_sha256: str = Field(pattern=SHA256_PATTERN)
    native_proof_sha256: str = Field(pattern=SHA256_PATTERN)
    vendor_sha256: dict[str, str]
    service_report_sha256: str = Field(pattern=SHA256_PATTERN)
    observation: WaytaServiceObservation


class WaytaRequirementAssessment(StrictModel):
    policy_version: Literal["xpm-wayta-requirement-1.0"]
    base: SpsCompatibilityAssessment
    requirement: Literal["advisory_for_qualified_profile", "undetermined"]
    reasons: tuple[str, ...]
    affiliation_count: int = Field(ge=0)
    author_count: int = Field(ge=0)
    service_observation: WaytaServiceObservation
    service_report_sha256: str = Field(pattern=SHA256_PATTERN)
    normative_sha256: str = NORMATIVE_SHA256
    native_proof_sha256: str = NATIVE_PROOF_SHA256
    article_query_completed: Literal[False] = False
    institution_identity_verified: Literal[False] = False
    mandatory_affiliation_validation_required: Literal[True] = True
    homologation_ready: Literal[False] = False
    release_approved: Literal[False] = False


def _plain(node: etree._Element) -> str:
    return (node.text or "").strip() if len(node) == 0 else ""


def affiliation_profile(root: etree._Element) -> tuple[tuple[str, ...], int, int]:
    """Narrow applicability guard; unsupported shapes remain undetermined, not invalid."""
    reasons = set()
    affs = root.findall("front/article-meta/aff")
    authors = root.findall('front/article-meta/contrib-group/contrib[@contrib-type="author"]')
    if (
        len(root.findall("front/article-meta")) != 1
        or root.xpath(".//sub-article | .//response")
        or len(affs) != len(root.findall(".//aff"))
        or not affs
        or not authors
    ):
        reasons.add("affiliation-shape-not-qualified")
    ids = [n.get("id") for n in root.iter() if n.get("id") is not None]
    if len(ids) != len(set(ids)) or any(not i or i.strip() != i for i in ids):
        reasons.add("duplicate-or-empty-id")
    if root.xpath('.//institution[@content-type="normalized"]'):
        reasons.add("legacy-normalized-institution-not-qualified")
    aff_ids = {a.get("id") for a in affs}
    if None in aff_ids or "" in aff_ids:
        reasons.add("affiliation-id-missing")
    for aff in affs:
        institutions = aff.findall("institution")
        types = [n.get("content-type") for n in institutions]
        if (
            types.count("original") != 1
            or types.count("orgname") != 1
            or any(t not in {"original", "orgname", "orgdiv1", "orgdiv2"} for t in types)
            or len(types) != len(set(types))
            or any(not _plain(n) for n in institutions)
            or len(aff.findall(".//institution")) != len(institutions)
        ):
            reasons.add("institution-fields-not-qualified")
        countries = aff.findall("country")
        if len(countries) != 1 or _plain(countries[0]) not in COUNTRIES.get(
            countries[0].get("country", ""), set()
        ):
            reasons.add("country-missing-mismatched-or-outside-qualified-profile")
        for kind in ("city", "state"):
            nodes = aff.findall(f'addr-line/named-content[@content-type="{kind}"]')
            if len(nodes) != 1 or not _plain(nodes[0]):
                reasons.add("geography-not-qualified")
    referenced = set()
    for author in authors:
        refs = author.findall('xref[@ref-type="aff"]')
        targets = [r.get("rid", "") for r in refs]
        if (
            not targets
            or len(targets) != len(set(targets))
            or any(t not in aff_ids for t in targets)
        ):
            reasons.add("author-affiliation-link-not-qualified")
        referenced.update(targets)
    if referenced != aff_ids:
        reasons.add("unreferenced-affiliation")
    return tuple(sorted(reasons)), len(affs), len(authors)


def assess_wayta_requirement(
    *,
    xml: bytes,
    package: bytes,
    report: bytes,
    crossref: bytes,
    trusted: XpmCompatibilityEvidence,
    expected_scope: dict[str, str],
    now: datetime,
    sps_evidence: SpsCompatibilityEvidence | SpsRuntimeEvidence,
    wayta_evidence: WaytaRequirementEvidence,
) -> WaytaRequirementAssessment:
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
    # Revalidate even if an internal caller used model_copy/model_construct.
    evidence = WaytaRequirementEvidence.model_validate(wayta_evidence.model_dump(mode="python"))
    if (
        validate_scope(evidence.scope) != validate_scope(expected_scope)
        or evidence.normative_sha256 != NORMATIVE_SHA256
        or evidence.native_proof_sha256 != NATIVE_PROOF_SHA256
        or evidence.vendor_sha256 != VENDOR_FILES
    ):
        raise ValueError("wayta_evidence_mismatch")
    if now.utcoffset() is None or not timedelta(0) <= (
        now - evidence.observation.observed_at
    ) <= timedelta(hours=24):
        raise ValueError("wayta_observation_stale_or_future")
    root = etree.fromstring(
        xml, etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True)
    )
    reasons, aff_count, author_count = affiliation_profile(root)
    return WaytaRequirementAssessment(
        policy_version="xpm-wayta-requirement-1.0",
        base=base,
        requirement="undetermined" if reasons else "advisory_for_qualified_profile",
        reasons=(
            *reasons,
            "service-probe-is-not-article-query",
            "institution-identity-not-verified",
        ),
        affiliation_count=aff_count,
        author_count=author_count,
        service_observation=evidence.observation,
        service_report_sha256=evidence.service_report_sha256,
    )
