"""Curated institutional states, never inferred from a city or an untrusted URL.

Rules bind a reviewed address fragment to an exact institution/unit/city/country.
Changed fragments require renewed curation, not a fuzzy or geocoded fallback.
"""

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Literal, Self

from lxml import etree
from pydantic import AwareDatetime, Field, model_validator

from idml_foundation.ai.security import payload_digest
from idml_foundation.domain.canonical import Affiliation, CanonicalArticle, SourcedText
from idml_foundation.domain.common import (
    SHA256_PATTERN,
    Evidence,
    EvidenceLocator,
    SourceKind,
    StrictModel,
    stable_id,
)
from idml_foundation.release.articlemeta_orcids import normalized_name, sha


@dataclass(frozen=True)
class SourceRule:
    url: str
    xpath: str
    nodes: int
    fragment_sha256: str
    document_sha256: str | None = None


SOURCES = {
    "easwari_disclosure": SourceRule(
        "https://srmeaswari.ac.in/wp-content/uploads/2025/03/AICTE-MD-Submitted-in-2024-2025.pdf",
        "page=2;institution-address;state-ut",
        1,
        "57a989d4b599086c8571f8a7a57f8ed5c3858ba07a525daeeb936e3cbda64a21",
        "e606701ca231e10269ce23fbb4b9e6c598b2398cd565c169c9d5094ee16dd3c9",
    ),
    "tokyo_department": SourceRule(
        "https://ml.c.u-tokyo.ac.jp/en/contact/",
        "//div[contains(concat(' ', normalize-space(@class), ' '), ' entry-content ')]/div",
        6,
        "47d708fd3f54223d7fdf874b87d50bb399d7bfd3833714c9d7fbbd88c804c48c",
    ),
    "tokyo_government": SourceRule(
        "https://www.english.metro.tokyo.lg.jp/w/000-101-007591",
        "//div[@class='orlfr-article']/p[contains(., 'regional local government')]",
        1,
        "27a9bed5ef25652754ccde36ec8161a4d8bb58d9573324317a7779397489825a",
    ),
    "cahcet": SourceRule(
        "https://cahcet.in/?page_id=659",
        "//p[span[contains(., 'C. Abdul Hakeem College')]]",
        1,
        "f3a40fa2d89183c2c8bc09d7dfc056af16b5474fb4de336649ed7f79794eb6cb",
    ),
    "easwari": SourceRule(
        "https://www.nirfindia.org/Rankings/2024/EngineeringRanking200.html",
        "//tr[td[1][normalize-space(.)='Easwari Engineering College']]",
        1,
        "a68da48c8e8f3a63feb051967bf4b430a693465d38851baf0b30a319ea5ee0ae",
    ),
    "tindivanam": SourceRule(
        "https://viluppuram.nic.in/public-utility/university-college-of-engineering-tindivanam/",
        "//h1 | //main//a[contains(text(), 'Melpakkam')]",
        2,
        "69152f13696d1b9573ff05772252ee1382ee36787e417370395cbcf562db62a1",
    ),
    "syed_hameedha": SourceRule(
        "https://www.shartsandscience-edu.in/contact.php",
        "//p[b[normalize-space(.)='SYED HAMEEDHA ARTS AND SCIENCE COLLEGE']]",
        1,
        "67d238feae1509fcb009f625fa7f66cc7b0b54e5de0b3edb14cec157e793150e",
    ),
}


@dataclass(frozen=True)
class LocationRule:
    institution: str
    department: str
    city: str
    country: str
    country_code: str
    state: str
    sources: tuple[str, ...]


RULES = {
    "tokyo_gss": LocationRule(
        "University of Tokyo",
        "Graduate School of Arts and Sciences, Department of General Systems Studies",
        "Tokyo",
        "Japan",
        "JP",
        "Tokyo",
        ("tokyo_department", "tokyo_government"),
    ),
    "cahcet_it": LocationRule(
        "C. Abdul Hakeem College of Engineering & Technology",
        "Department of Information Technology",
        "Melvisharam",
        "India",
        "IN",
        "Tamil Nadu",
        ("cahcet",),
    ),
    "easwari_it": LocationRule(
        "Easwari Engineering College",
        "Department of Information Technology",
        "Chennai",
        "India",
        "IN",
        "Tamil Nadu",
        ("easwari",),
    ),
    "tindivanam_it": LocationRule(
        "University College of Engineering Tindivanam",
        "Department of Information Technology",
        "Tindivanam",
        "India",
        "IN",
        "Tamil Nadu",
        ("tindivanam",),
    ),
    "syed_hameedha_cs": LocationRule(
        "Syed Hameedha Arts and Science College",
        "Department of Computer Science",
        "Kilakarai",
        "India",
        "IN",
        "Tamil Nadu",
        ("syed_hameedha",),
    ),
}


RULES["easwari_it_disclosure"] = replace(RULES["easwari_it"], sources=("easwari_disclosure",))


def matches(aff: Affiliation, rule: LocationRule) -> bool:
    for key in ("institution", "department", "city", "country", "country_code"):
        field = getattr(aff, key)
        if (
            field is None
            or field.state != "present"
            or normalized_name(field.value or "") != (normalized_name(getattr(rule, key)))
        ):
            return False
    return True


def affiliation_digest(aff: Affiliation) -> str:
    return payload_digest(aff.model_dump(mode="json", exclude={"state_or_province"}))


class LocationSnapshot(StrictModel):
    key: str
    sha256: str = Field(pattern=SHA256_PATTERN)
    fragment_sha256: str = Field(pattern=SHA256_PATTERN)
    collected_at: AwareDatetime

    @model_validator(mode="after")
    def curated(self) -> Self:
        if self.key not in SOURCES or self.fragment_sha256 != SOURCES[self.key].fragment_sha256:
            raise ValueError("institution_location_unreviewed_source")
        pinned = SOURCES[self.key].document_sha256
        if pinned is not None and self.sha256 != pinned:
            raise ValueError("institution_location_document_changed")
        return self


def verify_snapshot(key: str, raw: bytes, url: str, collected_at: str) -> LocationSnapshot:
    if key not in SOURCES or url != SOURCES[key].url:
        raise ValueError("institution_location_source_mismatch")
    if not 0 < len(raw) <= 4 * 1024**2:
        raise ValueError("institution_location_source_budget")
    rule = SOURCES[key]
    if rule.document_sha256 is not None:
        # The exact PDF and its page-two address fragment were verified together.
        return LocationSnapshot(
            key=key,
            sha256=sha(raw),
            fragment_sha256=rule.fragment_sha256,
            collected_at=collected_at,
        )
    # HTML is inert data: no scripts, links, external entities or URLs are executed/fetched.
    tree = etree.fromstring(raw, etree.HTMLParser(no_network=True))
    nodes: Any = tree.xpath(rule.xpath) if tree is not None else []
    if len(nodes) != rule.nodes:
        raise ValueError("institution_location_ambiguous_fragment")
    fragment = " ".join(" ".join(" ".join(n.itertext()) for n in nodes).split())
    return LocationSnapshot(
        key=key, sha256=sha(raw), fragment_sha256=sha(fragment.encode()), collected_at=collected_at
    )


class LocationAddition(StrictModel):
    affiliation_id: str = Field(min_length=1, max_length=200)
    affiliation_sha256: str = Field(pattern=SHA256_PATTERN)
    rule_id: str


class InstitutionLocationCatalog(StrictModel):
    version: Literal["institution-location-catalog-1.0"]
    catalog_id: str = Field(pattern=SHA256_PATTERN)
    corpus_id: str = Field(min_length=3, max_length=100)
    journal_profile_id: str = Field(min_length=3, max_length=100)
    source_idml_sha256: str = Field(pattern=SHA256_PATTERN)
    doi: str = Field(min_length=7, max_length=200)
    snapshots: tuple[LocationSnapshot, ...] = Field(min_length=1, max_length=6)
    additions: tuple[LocationAddition, ...] = Field(min_length=1, max_length=1000)
    human_review_required: Literal[True]

    @model_validator(mode="after")
    def bound(self) -> Self:
        if any(a.rule_id not in RULES for a in self.additions):
            raise ValueError("institution_location_unknown_rule")
        required = {s for a in self.additions for s in RULES[a.rule_id].sources}
        if (
            {s.key for s in self.snapshots} != required
            or len(self.snapshots) != len(required)
            or len({a.affiliation_id for a in self.additions}) != len(self.additions)
        ):
            raise ValueError("institution_location_incomplete_or_duplicate")
        if self.catalog_id != payload_digest(self.model_dump(mode="json", exclude={"catalog_id"})):
            raise ValueError("institution_location_catalog_digest")
        return self

    @property
    def collected_at(self) -> datetime:
        return min(s.collected_at for s in self.snapshots)

    @property
    def evidence_sha256(self) -> str:
        return payload_digest({s.key: s.model_dump(mode="json") for s in self.snapshots})

    def apply(self, article: CanonicalArticle, *, source_idml_sha256: str) -> CanonicalArticle:
        dois = [
            i.value.value.casefold()
            for i in article.front.article_identifiers
            if i.kind == "doi" and i.value.value
        ]
        if (
            source_idml_sha256 != self.source_idml_sha256
            or article.journal_profile_id != self.journal_profile_id
            or dois != [self.doi]
        ):
            raise ValueError("institution_location_scope_mismatch")
        affs = {a.id: a for a in article.front.affiliations}
        refs = {s.key: s for s in self.snapshots}
        values, evidence = {}, []
        for entry in self.additions:
            target = affs.get(entry.affiliation_id)
            rule = RULES[entry.rule_id]
            if (
                target is None
                or affiliation_digest(target) != entry.affiliation_sha256
                or not matches(target, rule)
            ):
                raise ValueError("institution_location_affiliation_changed")
            ids = []
            for key in rule.sources:
                spec, snapshot = SOURCES[key], refs[key]
                eid = stable_id(
                    article.article_id,
                    "evidence",
                    f"institution-location:{self.catalog_id}:{target.id}:{key}",
                )
                ids.append(eid)
                evidence.append(
                    Evidence(
                        id=eid,
                        source_kind=SourceKind.SYSTEM,
                        locator=EvidenceLocator(
                            artifact_sha256=snapshot.sha256,
                            logical_path=spec.url + "#xpath=" + spec.xpath,
                        ),
                        content_sha256=snapshot.fragment_sha256,
                        description="Curated official address; state only, pending expert review",
                    )
                )
            values[target.id] = SourcedText(
                value=rule.state,
                state="present",
                evidence_ids=tuple(ids),
                confidence=1.0,
                transformation="curated-institution-location",
            )
        reason = f"institution_locations_pending_human:{self.catalog_id}"
        if any(e.id in {a.id for a in article.evidence} for e in evidence):
            if (
                all(e in article.evidence for e in evidence)
                and all(affs[k].state_or_province == v for k, v in values.items())
                and reason in article.review_reasons
            ):
                return article
            raise ValueError("institution_location_partial_application")
        if any(affs[k].state_or_province is not None for k in values):
            raise ValueError("institution_location_existing_decision")
        enriched = article.model_copy(
            update={
                "front": article.front.model_copy(
                    update={
                        "affiliations": tuple(
                            a.model_copy(update={"state_or_province": values[a.id]})
                            if a.id in values
                            else a
                            for a in article.front.affiliations
                        )
                    }
                ),
                "evidence": (*article.evidence, *evidence),
                "review_reasons": (*article.review_reasons, reason),
            }
        )
        return CanonicalArticle.model_validate(enriched.model_dump(mode="json"))


def build_institution_location_catalog(
    *,
    article: CanonicalArticle,
    source_idml_sha256: str,
    corpus_id: str,
    assignments: dict[str, str],
    snapshots: dict[str, tuple[bytes, str, str]],
) -> InstitutionLocationCatalog:
    """Explicit operator assignments; no automatic search over institutions or cities."""
    affs = {a.id: a for a in article.front.affiliations}
    if not assignments or any(k not in affs or v not in RULES for k, v in assignments.items()):
        raise ValueError("institution_location_invalid_assignment")
    required = {s for r in assignments.values() for s in RULES[r].sources}
    if set(snapshots) != required:
        raise ValueError("institution_location_sources_incomplete")
    dois = [
        i.value.value.casefold()
        for i in article.front.article_identifiers
        if i.kind == "doi" and i.value.value
    ]
    if len(dois) != 1:
        raise ValueError("institution_location_doi_required")
    body: dict[str, Any] = dict(
        version="institution-location-catalog-1.0",
        corpus_id=corpus_id,
        journal_profile_id=article.journal_profile_id,
        source_idml_sha256=source_idml_sha256,
        doi=dois[0],
        human_review_required=True,
        snapshots=[
            verify_snapshot(k, *snapshots[k]).model_dump(mode="json") for k in sorted(required)
        ],
        additions=[
            LocationAddition(
                affiliation_id=k, affiliation_sha256=affiliation_digest(affs[k]), rule_id=v
            ).model_dump(mode="json")
            for k, v in assignments.items()
        ],
    )
    catalog = InstitutionLocationCatalog.model_validate(
        {**body, "catalog_id": payload_digest(body)}
    )
    catalog.apply(article, source_idml_sha256=source_idml_sha256)
    return catalog
