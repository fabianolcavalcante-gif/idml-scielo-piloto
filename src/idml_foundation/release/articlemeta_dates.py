"""Narrow, operator-provisioned SciELO date evidence; no network or heuristic dates."""

import hashlib
import json
import re
from datetime import date, datetime
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
from idml_foundation.publication_dates import refines_publication_date

VERSION = "articlemeta-date-catalog-1.0"
MAX_RESPONSE = 4 * 1024 * 1024
HISTORY_FIELDS = {"received": "v112", "accepted": "v114"}


def source_url(pid: str) -> str:
    if not re.fullmatch(r"S[0-9]{4}-[0-9]{3}[0-9X][0-9]{13}", pid):
        raise ValueError("articlemeta_pid_invalid")
    return "https://articlemeta.scielo.org/api/v1/article/?collection=scl&code=" + pid


def full_date(value: str) -> str:
    if not re.fullmatch(r"(?:19|20)\d{2}-\d{2}-\d{2}", value):
        raise ValueError("articlemeta_complete_date_required")
    return date.fromisoformat(value).isoformat()


def _field(article: dict[str, Any], key: str) -> str:
    entries = article.get(key)
    if not (
        isinstance(entries, list)
        and len(entries) == 1
        and isinstance(entries[0], dict)
        and isinstance(entries[0].get("_"), str)
    ):
        raise ValueError("articlemeta_field_missing_or_ambiguous")
    return str(entries[0]["_"])


def _legacy_date(article: dict[str, Any], field: str) -> str:
    value = _field(article, field)
    if not re.fullmatch(r"[0-9]{8}", value):
        raise ValueError("articlemeta_date_invalid")
    return full_date(f"{value[:4]}-{value[4:6]}-{value[6:]}")


class HistoryDateResolution(StrictModel):
    date_type: Literal["received", "accepted"]
    current_date: str
    source_date: str

    @model_validator(mode="after")
    def only_literal_month_day_disambiguation(self) -> Self:
        current, resolved = (
            date.fromisoformat(full_date(self.current_date)),
            date.fromisoformat(full_date(self.source_date)),
        )
        if current != resolved and (
            current.year != resolved.year
            or (current.day, current.month) != (resolved.month, resolved.day)
        ):
            raise ValueError("articlemeta_history_not_literal_date_disambiguation")
        return self


class ArticleMetaDateCatalog(StrictModel):
    version: Literal["articlemeta-date-catalog-1.0"]
    catalog_id: str = Field(pattern=SHA256_PATTERN)
    corpus_id: str = Field(min_length=3, max_length=100)
    journal_profile_id: str = Field(min_length=3, max_length=100)
    source_idml_sha256: str = Field(pattern=SHA256_PATTERN)
    response_sha256: str = Field(pattern=SHA256_PATTERN)
    collected_at: AwareDatetime
    pid: str
    doi: str = Field(min_length=7, max_length=200)
    current_publication_date: str | None
    publication_date: str
    history: tuple[HistoryDateResolution, ...]
    human_review_required: Literal[True]

    @model_validator(mode="after")
    def bounded_content_addressed_dates(self) -> Self:
        source_url(self.pid)
        full_date(self.publication_date)
        if self.current_publication_date and not refines_publication_date(
            self.current_publication_date, self.publication_date
        ):
            raise ValueError("articlemeta_publication_conflict")
        if len(self.history) != 2 or {h.date_type for h in self.history} != set(HISTORY_FIELDS):
            raise ValueError("articlemeta_received_and_accepted_required")
        dates = {h.date_type: h.source_date for h in self.history}
        if not dates["received"] <= dates["accepted"] < self.publication_date:
            raise ValueError("articlemeta_source_chronology_invalid")
        if payload_digest(self.model_dump(mode="json", exclude={"catalog_id"})) != self.catalog_id:
            raise ValueError("articlemeta_catalog_digest_mismatch")
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
            raise ValueError("articlemeta_article_scope_mismatch")
        current_history = {item.date_type: item.date for item in article.front.history_dates}
        evidence = []
        updates = {}
        for field, value, legacy in (
            ("pub", self.publication_date, "v223"),
            *((h.date_type, h.source_date, HISTORY_FIELDS[h.date_type]) for h in self.history),
        ):
            evidence_id = stable_id(
                article.article_id, "evidence", f"articlemeta:{self.catalog_id}:{legacy}"
            )
            evidence.append(
                Evidence(
                    id=evidence_id,
                    source_kind=SourceKind.SYSTEM,
                    locator=EvidenceLocator(
                        artifact_sha256=self.response_sha256,
                        logical_path=source_url(self.pid) + "#/article/" + legacy,
                        element_id=legacy,
                    ),
                    content_sha256=hashlib.sha256(value.encode()).hexdigest(),
                    description="SciELO ArticleMeta DOI/PID date evidence; pending human review",
                )
            )
            old_ids = current_history[field].evidence_ids if field in current_history else ()
            updates[field] = SourcedText(
                value=value,
                state=FieldState.PRESENT,
                evidence_ids=(*old_ids, evidence_id),
                confidence=1.0,
                transformation="articlemeta-publication-date"
                if field == "pub"
                else "articlemeta-confirmed-idml-date-convention",
            )
        # Already-applied catalogs are idempotent, but never accept a partial/stale application.
        ids = {e.id for e in article.evidence}
        if any(e.id in ids for e in evidence):
            if (
                all(e in article.evidence for e in evidence)
                and article.front.publication_date.value == self.publication_date
                and all(
                    current_history.get(h.date_type)
                    and current_history[h.date_type].value == h.source_date
                    for h in self.history
                )
            ):
                return article
            raise ValueError("articlemeta_partial_application")
        if article.front.publication_date.value != self.current_publication_date:
            raise ValueError("articlemeta_publication_precondition_changed")
        for h in self.history:
            current = current_history.get(h.date_type)
            if current is None or current.value != h.current_date:
                raise ValueError("articlemeta_history_precondition_changed")
            if (
                h.current_date != h.source_date
                and current.transformation != "correspondence-dd-mm-yyyy-to-iso-8601"
            ):
                raise ValueError("articlemeta_history_is_not_idml_date_interpretation")
        enriched = article.model_copy(
            update={
                "front": article.front.model_copy(
                    update={
                        "publication_date": updates["pub"],
                        "history_dates": tuple(
                            h.model_copy(update={"date": updates[h.date_type]})
                            if h.date_type in HISTORY_FIELDS
                            else h
                            for h in article.front.history_dates
                        ),
                    }
                ),
                "evidence": (*article.evidence, *evidence),
                "review_reasons": (
                    *article.review_reasons,
                    f"articlemeta_dates_pending_human:{self.catalog_id}",
                ),
            }
        )
        return CanonicalArticle.model_validate(enriched.model_dump(mode="json"))


def build_articlemeta_date_catalog(
    *,
    article: CanonicalArticle,
    source_idml_sha256: str,
    response: bytes,
    pid: str,
    collected_at: str,
    corpus_id: str,
) -> ArticleMetaDateCatalog:
    source_url(pid)
    if not 0 < len(response) <= MAX_RESPONSE:
        raise ValueError("articlemeta_response_budget")
    record = json.loads(response)
    metadata = record.get("article") if isinstance(record, dict) else None
    if not isinstance(metadata, dict) or not isinstance(record.get("doi"), str):
        raise ValueError("articlemeta_record_invalid")
    if (
        record.get("code") != pid
        or metadata.get("code") != pid
        or _field(metadata, "v880") != pid
        or record.get("collection") != "scl"
        or record["doi"].casefold() != _field(metadata, "v237").casefold()
    ):
        raise ValueError("articlemeta_record_identity_mismatch")
    published = _legacy_date(metadata, "v223")
    current: dict[str, str | None] = {
        h.date_type: h.date.value for h in article.front.history_dates
    }
    history = [
        dict(
            date_type=kind,
            current_date=current.get(kind),
            source_date=_legacy_date(metadata, field),
        )
        for kind, field in HISTORY_FIELDS.items()
    ]
    body: dict[str, Any] = dict(
        version=VERSION,
        corpus_id=corpus_id,
        journal_profile_id=article.journal_profile_id,
        source_idml_sha256=source_idml_sha256,
        response_sha256=hashlib.sha256(response).hexdigest(),
        collected_at=collected_at,
        pid=pid,
        doi=record["doi"].casefold(),
        current_publication_date=article.front.publication_date.value,
        publication_date=published,
        history=history,
        human_review_required=True,
    )
    # Normalize typed datetimes before hashing using the same JSON representation as validation.
    body["collected_at"] = datetime.fromisoformat(collected_at).isoformat()
    # Pydantic serializes UTC as Z; the catalog digest is calculated from that representation.
    if str(body["collected_at"]).endswith("+00:00"):
        body["collected_at"] = str(body["collected_at"])[:-6] + "Z"
    catalog = ArticleMetaDateCatalog.model_validate({**body, "catalog_id": payload_digest(body)})
    catalog.apply(article, source_idml_sha256=source_idml_sha256)
    return catalog
