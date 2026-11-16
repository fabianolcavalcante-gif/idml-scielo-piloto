"""Operator-curated award/source associations, never guessed from comma proximity.

A reviewed institutional document disambiguates an award already in the IDML.
It does not authorize importing other projects' awards, funders or article text.
"""

from dataclasses import dataclass
from typing import Any, Literal, Self

from pydantic import AwareDatetime, Field, model_validator

from idml_foundation.ai.security import payload_digest
from idml_foundation.domain.canonical import CanonicalArticle, FieldState, SourcedText
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
class FundingRule:
    agency: str
    award_id: str
    statement_sha256: str
    source_url: str
    source_sha256: str
    locator: str
    quote: str


RULES = {
    "embrapa-seg-21.17.02.001.05.00": FundingRule(
        agency="Brazilian Agricultural Research Corporation",
        award_id="21.17.02.001.05.00",
        statement_sha256="2193d3d76c7f2f9155be71a559c4c5f927022f3a4ebc2ff78833590a5dcaa72e",
        source_url=(
            "https://www.alice.cnptia.embrapa.br/alice/bitstream/doc/1147178/1/"
            "P-Uso-do-jardim-aquicola-no-tratamento-e-reuso-da-agua-de-piscicultura.pdf"
        ),
        source_sha256="27beb38146ab3755bca3e02f8afb38abfdd3cf28c156fe7fbf475e3e888617be",
        locator="page=1;printed-page=75;Apoio Financeiro",
        quote="Apoio Financeiro: Embrapa SEG 21.17.02.001.05.00",
    ),
}


class VerifiedFundingCatalog(StrictModel):
    version: Literal["verified-funding-catalog-1.0"]
    catalog_id: str = Field(pattern=SHA256_PATTERN)
    corpus_id: str = Field(min_length=3, max_length=100)
    journal_profile_id: str = Field(min_length=3, max_length=100)
    source_idml_sha256: str = Field(pattern=SHA256_PATTERN)
    doi: str = Field(min_length=7, max_length=200)
    funding_index: int = Field(ge=0, le=999)
    funding_sha256: str = Field(pattern=SHA256_PATTERN)
    preserved_funding_sha256: str = Field(pattern=SHA256_PATTERN)
    rule_id: str
    response_sha256: str = Field(pattern=SHA256_PATTERN)
    collected_at: AwareDatetime
    human_review_required: Literal[True]

    @model_validator(mode="after")
    def curated(self) -> Self:
        if self.rule_id not in RULES or self.response_sha256 != RULES[self.rule_id].source_sha256:
            raise ValueError("verified_funding_unreviewed_source")
        if self.catalog_id != payload_digest(self.model_dump(mode="json", exclude={"catalog_id"})):
            raise ValueError("verified_funding_catalog_digest")
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
            or dois != [self.doi]
        ):
            raise ValueError("verified_funding_scope_mismatch")
        if self.funding_index >= len(article.front.funding):
            raise ValueError("verified_funding_target_missing")
        target = article.front.funding[self.funding_index]
        rule = RULES[self.rule_id]
        statement = target.statement
        if (
            statement is None
            or statement.state != FieldState.PRESENT
            or not statement.value
            or not statement.evidence_ids
            or sha(statement.value.encode()) != rule.statement_sha256
            or rule.agency not in statement.value
            or rule.award_id not in statement.value
            or payload_digest(target.model_dump(mode="json", exclude={"agency", "award_id"}))
            != self.preserved_funding_sha256
        ):
            raise ValueError("verified_funding_statement_mismatch")
        eid = stable_id(article.article_id, "evidence", f"verified-funding:{self.catalog_id}")
        evidence = Evidence(
            id=eid,
            source_kind=SourceKind.SYSTEM,
            locator=EvidenceLocator(
                artifact_sha256=self.response_sha256,
                logical_path=rule.source_url + "#" + rule.locator,
            ),
            content_sha256=sha(rule.quote.encode()),
            description="Institutional award/source association; existing IDML award only",
        )
        ids = (*statement.evidence_ids, eid)
        expected = target.model_copy(
            update={
                "agency": SourcedText(
                    value=rule.agency,
                    state="present",
                    evidence_ids=ids,
                    confidence=1.0,
                    transformation="verified-funding-source",
                ),
                "award_id": SourcedText(
                    value=rule.award_id,
                    state="present",
                    evidence_ids=ids,
                    confidence=1.0,
                    transformation="verified-funding-award",
                ),
            }
        )
        reason = f"verified_funding_pending_human:{self.catalog_id}"
        if any(e.id == eid for e in article.evidence):
            if (
                evidence in article.evidence
                and target == expected
                and reason in article.review_reasons
            ):
                return article
            raise ValueError("verified_funding_partial_application")
        if (
            payload_digest(target) != self.funding_sha256
            or target.agency.state != FieldState.NEEDS_REVIEW
            or target.agency.value is not None
            or target.agency.transformation != "unresolved-funding-structure"
            or target.award_id is not None
            or "funding_structure_requires_authority" not in article.review_reasons
        ):
            raise ValueError("verified_funding_existing_decision_or_changed_target")
        funding = tuple(
            expected if index == self.funding_index else item
            for index, item in enumerate(article.front.funding)
        )
        unresolved = any(f.agency.state == FieldState.NEEDS_REVIEW for f in funding)
        reasons = tuple(
            r
            for r in article.review_reasons
            if unresolved or r != "funding_structure_requires_authority"
        )
        enriched = article.model_copy(
            update={
                "front": article.front.model_copy(update={"funding": funding}),
                "evidence": (*article.evidence, evidence),
                "review_reasons": (*reasons, reason),
            }
        )
        return CanonicalArticle.model_validate(enriched.model_dump(mode="json"))


def build_verified_funding_catalog(
    *,
    article: CanonicalArticle,
    source_idml_sha256: str,
    corpus_id: str,
    funding_index: int,
    rule_id: str,
    response: bytes,
    source_url: str,
    collected_at: str,
) -> VerifiedFundingCatalog:
    if (
        rule_id not in RULES
        or source_url != RULES[rule_id].source_url
        or not 0 < len(response) <= 4 * 1024**2
        or sha(response) != RULES[rule_id].source_sha256
    ):
        raise ValueError("verified_funding_source_mismatch")
    if not 0 <= funding_index < len(article.front.funding):
        raise ValueError("verified_funding_target_missing")
    dois = [
        i.value.value.casefold()
        for i in article.front.article_identifiers
        if i.kind == "doi" and i.value.value
    ]
    if len(dois) != 1:
        raise ValueError("verified_funding_doi_required")
    snapshot = SnapshotReference(sha256=sha(response), collected_at=collected_at)
    body: dict[str, Any] = dict(
        version="verified-funding-catalog-1.0",
        corpus_id=corpus_id,
        journal_profile_id=article.journal_profile_id,
        source_idml_sha256=source_idml_sha256,
        doi=dois[0],
        funding_index=funding_index,
        rule_id=rule_id,
        funding_sha256=payload_digest(article.front.funding[funding_index]),
        preserved_funding_sha256=payload_digest(
            article.front.funding[funding_index].model_dump(
                mode="json", exclude={"agency", "award_id"}
            )
        ),
        response_sha256=sha(response),
        collected_at=snapshot.model_dump(mode="json")["collected_at"],
        human_review_required=True,
    )
    catalog = VerifiedFundingCatalog.model_validate({**body, "catalog_id": payload_digest(body)})
    catalog.apply(article, source_idml_sha256=source_idml_sha256)
    return catalog
