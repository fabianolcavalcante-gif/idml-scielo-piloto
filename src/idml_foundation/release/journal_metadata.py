"""Two reviewed ESA registry corrections; never infer or overwrite editorial conflicts."""

import csv
import hashlib
import io
from datetime import datetime
from typing import Literal, Self

from pydantic import AwareDatetime, Field, model_validator

from idml_foundation.ai.security import payload_digest
from idml_foundation.domain.canonical import (
    CanonicalArticle,
    FieldState,
    JournalIdentity,
    SourcedText,
)
from idml_foundation.domain.common import (
    SHA256_PATTERN,
    Evidence,
    EvidenceLocator,
    SourceKind,
    StrictModel,
    stable_id,
)

REGISTRY_URL = "https://static.scielo.org/sps/titles-tab-v2-utf-8.csv"
REGISTRY_SHA256 = "003921e3d6597dd57406ef86885d140990a0174fe2b326be1e501be70dbfc00a"
TITLE = "Engenharia Sanitaria e Ambiental"
PUBLISHER = "Associação Brasileira de Engenharia Sanitária e Ambiental - ABES"
PREVIOUS_TITLE = "Engenharia Sanitária e Ambiental"
PREVIOUS_PUBLISHER = "Associação Brasileira de Engenharia Sanitária e Ambiental"
IDENTIFIERS = {"publisher-id": "esa", "print-issn": "1413-4152", "electronic-issn": "1809-4457"}


def journal_digest(journal: JournalIdentity) -> str:
    return payload_digest(journal.model_dump(mode="json"))


def _check_journal(journal: JournalIdentity) -> None:
    values = {item.kind: item.value.value for item in journal.identifiers}
    if len(values) != len(journal.identifiers) or values != IDENTIFIERS:
        raise ValueError("journal_registry_identity_mismatch")
    for current, allowed in (
        (journal.title, {PREVIOUS_TITLE, TITLE}),
        (journal.publisher_name, {PREVIOUS_PUBLISHER, PUBLISHER}),
    ):
        if current is None or current.state != FieldState.PRESENT or current.alternatives:
            raise ValueError("journal_registry_ambiguous_field")
        if current.value not in allowed:
            raise ValueError("journal_registry_editorial_conflict")


def verify_registry(data: bytes) -> None:
    if not 0 < len(data) <= 8 * 1024**2 or hashlib.sha256(data).hexdigest() != REGISTRY_SHA256:
        raise ValueError("journal_registry_unqualified_snapshot")
    matches = [
        row
        for row in csv.reader(io.StringIO(data.decode("utf-8-sig")), delimiter="\t")
        if len(row) >= 12
        and row[0] == "scl"
        and row[2:4] == [IDENTIFIERS["print-issn"], IDENTIFIERS["electronic-issn"]]
        and row[5] == "esa"
    ]
    if len(matches) != 1 or (matches[0][7], matches[0][9]) != (TITLE, PUBLISHER):
        raise ValueError("journal_registry_row_mismatch")


class JournalMetadataCatalog(StrictModel):
    version: Literal["journal-metadata-catalog-1.0"]
    catalog_id: str = Field(pattern=SHA256_PATTERN)
    corpus_id: str = Field(min_length=3, max_length=100)
    journal_profile_id: Literal["esa-aop-1.1.0"]
    source_idml_sha256: str = Field(pattern=SHA256_PATTERN)
    before_journal_sha256: str = Field(pattern=SHA256_PATTERN)
    before_journal: JournalIdentity
    response_sha256: str = Field(pattern=SHA256_PATTERN)
    collected_at: AwareDatetime
    human_review_required: Literal[True]

    @model_validator(mode="after")
    def bound(self) -> Self:
        _check_journal(self.before_journal)
        if journal_digest(self.before_journal) != self.before_journal_sha256:
            raise ValueError("journal_registry_before_mismatch")
        if self.response_sha256 != REGISTRY_SHA256:
            raise ValueError("journal_registry_unqualified_snapshot")
        if payload_digest(self.model_dump(mode="json", exclude={"catalog_id"})) != self.catalog_id:
            raise ValueError("journal_registry_catalog_mismatch")
        return self

    def apply(self, article: CanonicalArticle, *, source_idml_sha256: str) -> CanonicalArticle:
        if source_idml_sha256 != self.source_idml_sha256:
            raise ValueError("journal_registry_source_mismatch")
        if article.journal_profile_id != self.journal_profile_id:
            raise ValueError("journal_registry_profile_mismatch")
        journal = article.front.journal
        _check_journal(journal)
        evidence_id = stable_id(
            article.article_id, "evidence", "journal-registry:" + self.catalog_id
        )
        marker = "journal_metadata_registry_pending_human:" + self.catalog_id
        evidence = Evidence(
            id=evidence_id,
            source_kind=SourceKind.SYSTEM,
            locator=EvidenceLocator(
                artifact_sha256=self.response_sha256, logical_path=REGISTRY_URL
            ),
            content_sha256=self.catalog_id,
            description=(
                "Reviewed SciELO ESA registry title and publisher; original evidence retained"
            ),
        )

        def corrected(current: SourcedText, value: str) -> SourcedText:
            return current.model_copy(
                update={
                    "value": value,
                    "evidence_ids": (*current.evidence_ids, evidence_id),
                    "transformation": "scielo-journal-registry-exact-1.0",
                }
            )

        before = self.before_journal
        assert before.publisher_name is not None
        new_journal = before.model_copy(
            update={
                "title": corrected(before.title, TITLE),
                "publisher_name": corrected(before.publisher_name, PUBLISHER),
            }
        )
        if journal_digest(journal) != self.before_journal_sha256:
            # Idempotency requires exact provenance, not just coincidentally equal strings.
            if (
                journal == new_journal
                and evidence in article.evidence
                and marker in article.review_reasons
            ):
                return article
            raise ValueError("journal_registry_stale_or_changed_journal")
        if any(e.id == evidence_id for e in article.evidence):
            raise ValueError("journal_registry_evidence_collision")

        result = article.model_copy(
            update={
                "front": article.front.model_copy(update={"journal": new_journal}),
                "evidence": (*article.evidence, evidence),
                "review_reasons": (*article.review_reasons, marker),
            }
        )
        return CanonicalArticle.model_validate(result.model_dump(mode="json"))


def build_journal_metadata_catalog(
    article: CanonicalArticle,
    *,
    source_idml_sha256: str,
    registry: bytes,
    collected_at: datetime,
    corpus_id: str,
) -> JournalMetadataCatalog:
    verify_registry(registry)
    _check_journal(article.front.journal)
    value = {
        "version": "journal-metadata-catalog-1.0",
        "corpus_id": corpus_id,
        "journal_profile_id": article.journal_profile_id,
        "source_idml_sha256": source_idml_sha256,
        "before_journal_sha256": journal_digest(article.front.journal),
        "before_journal": article.front.journal.model_dump(mode="json"),
        "response_sha256": REGISTRY_SHA256,
        "collected_at": collected_at.isoformat(),
        "human_review_required": True,
    }
    # Pydantic uses the canonical JSON timestamp (UTC -> Z) for the content identity.
    value["collected_at"] = collected_at.isoformat().replace("+00:00", "Z")
    return JournalMetadataCatalog.model_validate({**value, "catalog_id": payload_digest(value)})
