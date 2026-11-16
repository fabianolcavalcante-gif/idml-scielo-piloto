from __future__ import annotations

import hashlib
import re
from typing import Any, Literal, Self

from pydantic import Field, model_validator

from idml_foundation.ai.security import payload_digest
from idml_foundation.domain.canonical import (
    CanonicalArticle,
    ContributorName,
    FieldState,
    Identifier,
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

CATALOG_VERSION = "crossref-metadata-authority-catalog-1.0"
REPORT_VERSION = "crossref-metadata-authority-qualification-1.0"
_ORCID_URL = re.compile(r"https://orcid\.org/\d{4}-\d{4}-\d{4}-\d{3}[\dX]")
_OTHER_ID = re.compile(r"\d{5}$")


def _value_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class CrossrefAuthorAuthority(StrictModel):
    contributor_id: str = Field(min_length=3, max_length=120)
    current_given_names_sha256: str = Field(pattern=SHA256_PATTERN)
    current_surname_sha256: str = Field(pattern=SHA256_PATTERN)
    orcid: str = Field(pattern=r"^https://orcid\.org/")
    given_names: str = Field(min_length=1, max_length=200)
    surname: str = Field(min_length=1, max_length=200)
    record_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def orcid_is_complete(self) -> Self:
        if _ORCID_URL.fullmatch(self.orcid) is None:
            raise ValueError("Crossref author authority requires a complete ORCID URL")
        return self


class CrossrefMetadataAuthorityCatalog(StrictModel):
    version: Literal["crossref-metadata-authority-catalog-1.0"]
    catalog_id: str = Field(pattern=SHA256_PATTERN)
    corpus_id: str = Field(min_length=3, max_length=100)
    journal_profile_id: str = Field(min_length=3, max_length=100)
    source_idml_sha256: str = Field(pattern=SHA256_PATTERN)
    crossref_response_sha256: str = Field(pattern=SHA256_PATTERN)
    doi: str = Field(min_length=7, max_length=200)
    journal_title: str = Field(min_length=1, max_length=500)
    other_id: str = Field(pattern=r"^\d{5}$")
    authors: tuple[CrossrefAuthorAuthority, ...] = Field(min_length=1, max_length=100)
    human_review_required: Literal[True]

    @model_validator(mode="after")
    def catalog_is_complete_and_content_addressed(self) -> Self:
        contributor_ids = [item.contributor_id for item in self.authors]
        orcids = [item.orcid.casefold() for item in self.authors]
        if len(contributor_ids) != len(set(contributor_ids)) or len(orcids) != len(set(orcids)):
            raise ValueError("Crossref metadata authority contains duplicate authors")
        payload = self.model_dump(mode="json", exclude={"catalog_id"})
        if payload_digest(payload) != self.catalog_id:
            raise ValueError("Crossref metadata authority catalog ID mismatch")
        return self

    def apply(
        self,
        article: CanonicalArticle,
        *,
        source_idml_sha256: str,
    ) -> CanonicalArticle:
        if source_idml_sha256 != self.source_idml_sha256:
            raise ValueError("Crossref metadata authority source IDML hash mismatch")
        if article.journal_profile_id != self.journal_profile_id:
            raise ValueError("Crossref metadata authority journal profile mismatch")
        dois = [
            item.value.value.casefold()
            for item in article.front.article_identifiers
            if item.kind == "doi" and item.value.value
        ]
        if dois != [self.doi.casefold()]:
            raise ValueError("Crossref metadata authority DOI mismatch")
        if len(article.front.contributors) != len(self.authors):
            raise ValueError("Crossref metadata authority contributor count mismatch")

        evidence_id = stable_id(
            article.article_id,
            "evidence",
            f"crossref-metadata-authority:{self.catalog_id}",
        )
        contributors = []
        for contributor, authority in zip(article.front.contributors, self.authors, strict=True):
            if contributor.id != authority.contributor_id or contributor.name is None:
                raise ValueError("Crossref metadata authority contributor identity mismatch")
            given_names = contributor.name.given_names.value or ""
            surname = contributor.name.surname.value or ""
            if (
                _value_sha256(given_names) != authority.current_given_names_sha256
                or _value_sha256(surname) != authority.current_surname_sha256
            ):
                raise ValueError("Crossref metadata authority current name hash mismatch")
            if contributor.orcid is None or contributor.orcid.value != authority.orcid:
                raise ValueError("Crossref metadata authority source ORCID mismatch")

            def authoritative_name(value: str, current: SourcedText) -> dict[str, object]:
                return {
                    "value": value,
                    "state": FieldState.PRESENT,
                    "evidence_ids": tuple(dict.fromkeys((*current.evidence_ids, evidence_id))),
                    "transformation": "crossref-doi-authority",
                    "confidence": 1.0,
                }

            contributors.append(
                contributor.model_copy(
                    update={
                        "name": ContributorName(
                            given_names=authoritative_name(
                                authority.given_names, contributor.name.given_names
                            ),
                            surname=authoritative_name(authority.surname, contributor.name.surname),
                            prefix=contributor.name.prefix,
                            suffix=contributor.name.suffix,
                        ),
                        "evidence_ids": tuple(
                            dict.fromkeys((*contributor.evidence_ids, evidence_id))
                        ),
                    }
                )
            )

        other_identifiers = [
            item
            for item in article.front.article_identifiers
            if item.kind == "other" and item.value.value
        ]
        if other_identifiers and [item.value.value for item in other_identifiers] != [
            self.other_id
        ]:
            raise ValueError("Crossref metadata authority conflicts with existing other ID")
        identifiers = list(article.front.article_identifiers)
        if not other_identifiers:
            identifiers.append(
                Identifier(
                    kind="other",
                    value={
                        "value": self.other_id,
                        "state": FieldState.PRESENT,
                        "evidence_ids": (evidence_id,),
                        "transformation": "crossref-alternative-id-authority",
                        "confidence": 1.0,
                    },
                )
            )

        journal_title = article.front.journal.title.model_copy(
            update={
                "value": self.journal_title,
                "state": FieldState.PRESENT,
                "evidence_ids": tuple(
                    dict.fromkeys((*article.front.journal.title.evidence_ids, evidence_id))
                ),
                "transformation": "crossref-container-title-authority",
                "confidence": 1.0,
            }
        )
        evidence = Evidence(
            id=evidence_id,
            source_kind=SourceKind.SYSTEM,
            locator=EvidenceLocator(
                artifact_sha256=self.crossref_response_sha256,
                logical_path=f"https://api.crossref.org/works/{self.doi}",
                element_id=self.catalog_id[:32],
            ),
            content_sha256=self.catalog_id,
            description="Content-addressed Crossref DOI metadata authority snapshot",
        )
        enriched = article.model_copy(
            update={
                "front": article.front.model_copy(
                    update={
                        "journal": article.front.journal.model_copy(
                            update={"title": journal_title}
                        ),
                        "article_identifiers": tuple(identifiers),
                        "contributors": tuple(contributors),
                    }
                ),
                "evidence": (*article.evidence, evidence),
                "review_reasons": (
                    *article.review_reasons,
                    f"crossref_metadata_authority_pending_human:{self.catalog_id}",
                ),
            }
        )
        return CanonicalArticle.model_validate(enriched.model_dump(mode="json"))


def build_crossref_metadata_authority_catalog(
    *,
    article: CanonicalArticle,
    source_idml_sha256: str,
    crossref_response: bytes,
    corpus_id: str,
) -> tuple[CrossrefMetadataAuthorityCatalog, dict[str, Any]]:
    if not crossref_response or len(crossref_response) > 10 * 1024 * 1024:
        raise ValueError("Crossref response must contain between 1 byte and 10 MiB")
    import json

    response = json.loads(crossref_response)
    message = response.get("message") if isinstance(response, dict) else None
    if response.get("status") != "ok" or not isinstance(message, dict):
        raise ValueError("Crossref response is not a successful work record")
    doi = str(message.get("DOI", "")).strip().casefold()
    article_dois = [
        item.value.value.casefold()
        for item in article.front.article_identifiers
        if item.kind == "doi" and item.value.value
    ]
    if article_dois != [doi]:
        raise ValueError("Crossref work DOI does not match the source article")
    container_titles = message.get("container-title")
    if not isinstance(container_titles, list) or len(container_titles) != 1:
        raise ValueError("Crossref work must contain exactly one journal title")
    journal_title = str(container_titles[0]).strip()
    if not journal_title:
        raise ValueError("Crossref journal title is empty")

    alternative_ids = message.get("alternative-id")
    if not isinstance(alternative_ids, list):
        raise ValueError("Crossref work has no alternative article identifier")
    other_ids = {
        match.group(0)
        for value in alternative_ids
        if (match := _OTHER_ID.search(str(value))) is not None
    }
    if len(other_ids) != 1:
        raise ValueError("Crossref work must resolve exactly one five-digit other ID")
    other_id = next(iter(other_ids))

    crossref_authors = message.get("author")
    if not isinstance(crossref_authors, list) or len(crossref_authors) != len(
        article.front.contributors
    ):
        raise ValueError("Crossref author count does not match the source article")
    authors: list[CrossrefAuthorAuthority] = []
    for contributor, record in zip(article.front.contributors, crossref_authors, strict=True):
        if contributor.name is None or contributor.orcid is None or not isinstance(record, dict):
            raise ValueError("Crossref author authority requires source names and ORCIDs")
        orcid = str(record.get("ORCID", "")).strip()
        given_names = str(record.get("given", "")).strip()
        surname = str(record.get("family", "")).strip()
        if contributor.orcid.value != orcid or not given_names or not surname:
            raise ValueError("Crossref author does not match the source ORCID sequence")
        authors.append(
            CrossrefAuthorAuthority(
                contributor_id=contributor.id,
                current_given_names_sha256=_value_sha256(contributor.name.given_names.value or ""),
                current_surname_sha256=_value_sha256(contributor.name.surname.value or ""),
                orcid=orcid,
                given_names=given_names,
                surname=surname,
                record_sha256=payload_digest(record),
            )
        )

    response_sha256 = hashlib.sha256(crossref_response).hexdigest()
    base = {
        "version": CATALOG_VERSION,
        "corpus_id": corpus_id,
        "journal_profile_id": article.journal_profile_id,
        "source_idml_sha256": source_idml_sha256,
        "crossref_response_sha256": response_sha256,
        "doi": doi,
        "journal_title": journal_title,
        "other_id": other_id,
        "authors": [item.model_dump(mode="json") for item in authors],
        "human_review_required": True,
    }
    catalog = CrossrefMetadataAuthorityCatalog.model_validate(
        {"catalog_id": payload_digest(base), **base}
    )
    report = {
        "version": REPORT_VERSION,
        "catalog_id": catalog.catalog_id,
        "corpus_id": corpus_id,
        "source_idml_sha256": source_idml_sha256,
        "crossref_response_sha256": response_sha256,
        "authors": len(authors),
        "article_identifiers": 1,
        "journal_titles": 1,
        "human_review_required": True,
        "restricted_content_emitted": False,
    }
    return catalog, report
