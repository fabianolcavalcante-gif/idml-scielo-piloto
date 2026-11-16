"""Evidence-bound operator classification; never infer type from a URL or call AI."""

from dataclasses import dataclass
from typing import Any, Literal, Self

from pydantic import AwareDatetime, Field, model_validator

from idml_foundation.ai.security import payload_digest
from idml_foundation.domain.canonical import CanonicalArticle, Reference
from idml_foundation.domain.common import (
    SHA256_PATTERN,
    Evidence,
    EvidenceLocator,
    SourceKind,
    StrictModel,
    stable_id,
)
from idml_foundation.release.articlemeta_orcids import SnapshotReference, sha


@dataclass(frozen=True)
class ReferenceTypeRule:
    citation_sha256: str
    publication_type: Literal["webpage", "report"]
    source_url: str
    source_sha256: str
    locator: str
    quote: str
    locator_review_required: bool = False
    renewed_sha256: tuple[str, ...] = ()

    def accepts(self, digest: str) -> bool:
        return digest == self.source_sha256 or digest in self.renewed_sha256


# Reviewed institutional snapshots, not publication titles copied into the XML.
# New citations/sources require a new reviewed rule and a tenant-authorized bundle.
RULES = {
    "saae-mananciais": ReferenceTypeRule(
        "77c377509bc7ef29c598895a21e4dc3c544db8a4e9e56adfc561e44a62052e23",
        "webpage",
        "https://saaesaocarlos.com.br/servicos/agua/mananciais/",
        "96bf965b710358a15881bb7f5a9bf7a2b536b36f913526adfdc0135fa689724f",
        "h1;institutional-water-services-page",
        "Mananciais",
        True,
        ("f91bd7ba245d72a2eb2121330a65a38b6cea2e5346a769f7c6248913b6057b52",),
    ),
    "srac-3700": ReferenceTypeRule(
        "83bc30ccab4d261095df9183af7f500329d7ae2d4984c031d04b940c898294ff",
        "report",
        "https://srac.msstate.edu/pdfs/Fact%20Sheets/3700%20Pond%20Aeration.pdf",
        "65d0acdb5990beb43d5467015ef7eb4a6b212bca347d18e9a8c7e3d14928b210",
        "page=1;title-author-date-number",
        "SRAC Publication No. 3700",
    ),
    "who-situation-106": ReferenceTypeRule(
        "f31a522bceb91f7ffa17d0981aa70447f010ad58c4b4ea18a7a707774c8905f8",
        "report",
        "https://www.who.int/publications/m/item/situation-report---106",
        "612eeb73deadfe99aec131b987d93691a15343d4f41543fac27ca835f3b3e40b",
        "h1;5-May-2020;emergency-situation-update;PDF-link",
        "Situation Report - 106",
        True,
        ("7d1e2ec84435b6d8b95a64511f07fac1801a012b3d65cec7f9ace0c2373185da",),
    ),
}


class ReferenceTypeEntry(StrictModel):
    reference_id: str = Field(min_length=1, max_length=150)
    before_sha256: str = Field(pattern=SHA256_PATTERN)
    rule_id: str
    response_sha256: str = Field(pattern=SHA256_PATTERN)


class ReferenceTypeCatalog(StrictModel):
    version: Literal["reference-type-catalog-1.0"]
    catalog_id: str = Field(pattern=SHA256_PATTERN)
    corpus_id: str = Field(min_length=3, max_length=100)
    journal_profile_id: str = Field(min_length=3, max_length=100)
    source_idml_sha256: str = Field(pattern=SHA256_PATTERN)
    doi: str = Field(min_length=7, max_length=200)
    collected_at: AwareDatetime
    entries: tuple[ReferenceTypeEntry, ...] = Field(min_length=1, max_length=100)
    evidence_sha256: str = Field(pattern=SHA256_PATTERN)
    human_review_required: Literal[True]

    @model_validator(mode="after")
    def curated(self) -> Self:
        if len({e.reference_id for e in self.entries}) != len(self.entries):
            raise ValueError("reference_type_duplicate_target")
        for entry in self.entries:
            rule = RULES.get(entry.rule_id)
            if rule is None or not rule.accepts(entry.response_sha256):
                raise ValueError("reference_type_unreviewed_source")
        if self.evidence_sha256 != payload_digest(
            {e.rule_id: e.response_sha256 for e in self.entries}
        ):
            raise ValueError("reference_type_evidence_digest")
        if self.catalog_id != payload_digest(self.model_dump(mode="json", exclude={"catalog_id"})):
            raise ValueError("reference_type_catalog_digest")
        return self

    def apply(self, article: CanonicalArticle, *, source_idml_sha256: str) -> CanonicalArticle:
        dois = [
            i.value.value.casefold()
            for i in article.front.article_identifiers
            if i.kind == "doi" and i.value.value
        ]
        if (
            source_idml_sha256 != self.source_idml_sha256
            or article.journal_profile_id != self.journal_profile_id
            or dois != [self.doi.casefold()]
        ):
            raise ValueError("reference_type_scope_mismatch")
        references = list(article.back.references)
        evidence = list(article.evidence)
        reasons = list(article.review_reasons)
        for entry in self.entries:
            matches = [i for i, r in enumerate(references) if r.id == entry.reference_id]
            if len(matches) != 1:
                raise ValueError("reference_type_target_missing")
            index = matches[0]
            target, rule = references[index], RULES[entry.rule_id]
            eid = stable_id(
                article.article_id, "evidence", f"reference-type:{self.catalog_id}:{target.id}"
            )
            item = Evidence(
                id=eid,
                source_kind=SourceKind.SYSTEM,
                locator=EvidenceLocator(
                    artifact_sha256=entry.response_sha256,
                    logical_path=rule.source_url + "#" + rule.locator,
                ),
                content_sha256=sha(rule.quote.encode()),
                description="Operator-qualified reference type; literal IDML fields preserved",
            )
            if sha((target.mixed_citation.plain.value or "").encode()) != rule.citation_sha256:
                raise ValueError("reference_type_citation_mismatch")
            pending = f"verified_reference_type_pending_human:{self.catalog_id}:{target.id}"
            if any(e.id == eid for e in evidence):
                original = target.model_copy(
                    update={
                        "publication_type": "other",
                        "title": target.source,
                        "source": target.publisher_name,
                        "publisher_name": None,
                        "evidence_ids": tuple(e for e in target.evidence_ids if e != eid),
                        "review_reasons": ("reference_type_unresolved",),
                    }
                )
                if (
                    item not in evidence
                    or pending not in reasons
                    or (
                        rule.locator_review_required
                        and f"reference_source_locator_review:{target.id}" not in reasons
                    )
                    or payload_digest(original) != entry.before_sha256
                    or target != _classified(original, rule, eid)
                ):
                    raise ValueError("reference_type_partial_application")
                continue
            if (
                payload_digest(target) != entry.before_sha256
                or target.publication_type != "other"
                or target.review_reasons != ("reference_type_unresolved",)
                or target.publisher_name is not None
                or not target.title
                or not target.title.value
                or not target.source
                or not target.source.value
                or target.title.state != "present"
                or target.source.state != "present"
                or target.title.transformation != "deterministic-reference-title-extraction"
                or target.source.transformation != "deterministic-reference-source-extraction"
                or target.title.value not in (target.mixed_citation.plain.value or "")
                or target.source.value not in (target.mixed_citation.plain.value or "")
            ):
                raise ValueError("reference_type_existing_decision_or_changed_target")
            references[index] = _classified(target, rule, eid)
            evidence.append(item)
            unresolved = f"reference_type_unresolved:{target.id}"
            if unresolved not in reasons:
                raise ValueError("reference_type_review_state_missing")
            reasons.remove(unresolved)
            reasons.append(pending)
            if rule.locator_review_required:
                reasons.append(f"reference_source_locator_review:{target.id}")
        result = article.model_copy(
            update={
                "back": article.back.model_copy(update={"references": tuple(references)}),
                "evidence": tuple(evidence),
                "review_reasons": tuple(reasons),
            }
        )
        return CanonicalArticle.model_validate(result.model_dump(mode="json"))


def _classified(target: Reference, rule: ReferenceTypeRule, eid: str) -> Reference:
    # Reassign existing SourcedText objects; do not import title/year/URL from a website.
    return target.model_copy(
        update={
            "publication_type": rule.publication_type,
            "title": None,
            "source": target.title,
            "publisher_name": target.source,
            "evidence_ids": (*target.evidence_ids, eid),
            "review_reasons": (
                ("reference_source_locator_review",) if rule.locator_review_required else ()
            ),
        }
    )


def build_reference_type_catalog(
    *,
    article: CanonicalArticle,
    source_idml_sha256: str,
    corpus_id: str,
    selections: dict[str, str],
    responses: dict[str, bytes],
    collected_at: str,
) -> ReferenceTypeCatalog:
    entries = []
    for reference_id, rule_id in selections.items():
        rule, response = RULES.get(rule_id), responses.get(rule_id, b"")
        if rule is None or not 0 < len(response) <= 8 * 1024**2 or not rule.accepts(sha(response)):
            raise ValueError("reference_type_snapshot_mismatch")
        targets = [r for r in article.back.references if r.id == reference_id]
        if len(targets) != 1:
            raise ValueError("reference_type_target_missing")
        entries.append(
            ReferenceTypeEntry(
                reference_id=reference_id,
                before_sha256=payload_digest(targets[0]),
                rule_id=rule_id,
                response_sha256=sha(response),
            )
        )
    dois = [
        i.value.value.casefold()
        for i in article.front.article_identifiers
        if i.kind == "doi" and i.value.value
    ]
    if len(dois) != 1:
        raise ValueError("reference_type_doi_required")
    body: dict[str, Any] = dict(
        version="reference-type-catalog-1.0",
        corpus_id=corpus_id,
        journal_profile_id=article.journal_profile_id,
        source_idml_sha256=source_idml_sha256,
        doi=dois[0],
        collected_at=SnapshotReference(
            sha256=source_idml_sha256, collected_at=collected_at
        ).model_dump(mode="json")["collected_at"],
        entries=[e.model_dump() for e in entries],
        evidence_sha256=payload_digest({e.rule_id: e.response_sha256 for e in entries}),
        human_review_required=True,
    )
    catalog = ReferenceTypeCatalog.model_validate({**body, "catalog_id": payload_digest(body)})
    catalog.apply(article, source_idml_sha256=source_idml_sha256)
    return catalog
