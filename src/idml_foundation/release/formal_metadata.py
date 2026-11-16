from __future__ import annotations

import hashlib
import json
from typing import Any, Literal, Self, cast

from lxml import etree
from pydantic import Field, model_validator

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
from idml_foundation.publication_dates import publication_parts, refines_publication_date

CATALOG_VERSION = "formal-metadata-authority-catalog-1.0"
REPORT_VERSION = "formal-metadata-authority-qualification-1.0"


class FormalMetadataAuthorityCatalog(StrictModel):
    version: Literal["formal-metadata-authority-catalog-1.0"]
    catalog_id: str = Field(pattern=SHA256_PATTERN)
    corpus_id: str = Field(min_length=3, max_length=100)
    journal_profile_id: str = Field(min_length=3, max_length=100)
    source_idml_sha256: str = Field(pattern=SHA256_PATTERN)
    crossref_response_sha256: str = Field(pattern=SHA256_PATTERN)
    doi: str = Field(min_length=7, max_length=200)
    publication_date: str = Field(pattern=r"^(?:19|20)\d{2}(?:-\d{2}(?:-\d{2})?)?$")
    volume: str = Field(min_length=1, max_length=40)
    license_url: str = Field(pattern=r"^https://creativecommons\.org/licenses/")
    formal_reference_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    human_review_required: Literal[True]

    @model_validator(mode="after")
    def catalog_is_content_addressed(self) -> Self:
        publication_parts(self.publication_date)
        if payload_digest(self.model_dump(mode="json", exclude={"catalog_id"})) != self.catalog_id:
            raise ValueError("formal metadata authority catalog ID mismatch")
        return self

    def apply(
        self,
        article: CanonicalArticle,
        *,
        source_idml_sha256: str,
    ) -> CanonicalArticle:
        if source_idml_sha256 != self.source_idml_sha256:
            raise ValueError("formal metadata authority source IDML hash mismatch")
        if article.journal_profile_id != self.journal_profile_id:
            raise ValueError("formal metadata authority journal profile mismatch")
        dois = [
            item.value.value.casefold()
            for item in article.front.article_identifiers
            if item.kind == "doi" and item.value.value
        ]
        if dois != [self.doi.casefold()]:
            raise ValueError("formal metadata authority DOI mismatch")

        evidence_id = stable_id(
            article.article_id,
            "evidence",
            f"formal-metadata-authority:{self.catalog_id}",
        )

        def authoritative(value: str, transformation: str) -> SourcedText:
            return SourcedText(
                value=value,
                state=FieldState.PRESENT,
                evidence_ids=(evidence_id,),
                transformation=transformation,
                confidence=1.0,
            )

        for current, expected, label in (
            (article.front.publication_date.value, self.publication_date, "publication date"),
            (article.front.volume.value if article.front.volume else None, self.volume, "volume"),
            (
                article.front.license_url.value if article.front.license_url else None,
                self.license_url,
                "license URL",
            ),
        ):
            matches = (
                refines_publication_date(current, expected)
                if current is not None and label == "publication date"
                else current == expected
            )
            if current is not None and not matches:
                raise ValueError(f"formal metadata authority conflicts with existing {label}")

        evidence = Evidence(
            id=evidence_id,
            source_kind=SourceKind.SYSTEM,
            locator=EvidenceLocator(
                artifact_sha256=self.crossref_response_sha256,
                logical_path=f"https://api.crossref.org/works/{self.doi}",
                element_id=self.catalog_id[:32],
            ),
            content_sha256=self.catalog_id,
            description="Content-addressed Crossref formal publication metadata snapshot",
        )
        date_evidence = evidence
        if self.formal_reference_sha256:
            date_evidence = Evidence(
                id=stable_id(article.article_id, "evidence", f"formal-reference:{self.catalog_id}"),
                source_kind=SourceKind.SYSTEM,
                locator=EvidenceLocator(
                    artifact_sha256=self.formal_reference_sha256,
                    logical_path="formal-reference/front/article-meta/pub-date[@date-type='pub']",
                    element_id=self.catalog_id[:32],
                ),
                content_sha256=self.formal_reference_sha256,
                description="Authorized formal reference publication date; not Crossref precision",
            )
        date_value = authoritative(
            self.publication_date,
            (
                "approved-reference-publication-date-authority"
                if self.formal_reference_sha256
                else "crossref-published-year-authority"
                if len(publication_parts(self.publication_date)) == 1
                else "crossref-publication-date-authority"
            ),
        ).model_copy(update={"evidence_ids": (date_evidence.id,)})
        enriched = article.model_copy(
            update={
                "front": article.front.model_copy(
                    update={
                        "publication_date": date_value,
                        "volume": authoritative(self.volume, "crossref-volume-authority"),
                        "license_url": authoritative(
                            self.license_url,
                            "crossref-license-authority",
                        ),
                    }
                ),
                "evidence": (
                    *article.evidence,
                    evidence,
                    *((date_evidence,) if date_evidence.id != evidence.id else ()),
                ),
                "review_reasons": (
                    *article.review_reasons,
                    f"formal_metadata_authority_pending_human:{self.catalog_id}",
                ),
            }
        )
        return CanonicalArticle.model_validate(enriched.model_dump(mode="json"))


def _publication_date(message: dict[str, Any]) -> str:
    dates: set[str] = set()
    for key in ("published", "published-online", "issued"):
        if key not in message:
            continue
        value = message[key]
        parts = value.get("date-parts") if isinstance(value, dict) else None
        if not (
            isinstance(parts, list)
            and len(parts) == 1
            and isinstance(parts[0], list)
            and 1 <= len(parts[0]) <= 3
            and all(type(part) is int for part in parts[0])
        ):
            raise ValueError("Crossref publication date-parts are malformed or ambiguous")
        dates.add("-".join(str(n) if i == 0 else f"{n:02d}" for i, n in enumerate(parts[0])))
    if not dates:
        raise ValueError("Crossref work has no publication date")
    for value in dates:
        publication_parts(value)
    most_precise = max(dates, key=len)
    if not all(refines_publication_date(value, most_precise) for value in dates):
        raise ValueError("Crossref publication dates conflict")
    return most_precise


def _license_url(message: dict[str, Any]) -> str:
    licenses = message.get("license")
    if not isinstance(licenses, list):
        raise ValueError("Crossref work has no license records")
    urls = {
        str(item.get("URL", "")).strip().replace("http://", "https://", 1)
        for item in licenses
        if isinstance(item, dict) and item.get("URL")
    }
    urls.discard("")
    if len(urls) != 1:
        raise ValueError("Crossref work must resolve exactly one license URL")
    url = next(iter(urls))
    if not url.startswith("https://creativecommons.org/licenses/"):
        raise ValueError("Crossref work does not declare a supported Creative Commons license")
    return url


def build_formal_metadata_authority_catalog(
    *,
    article: CanonicalArticle,
    source_idml_sha256: str,
    crossref_response: bytes,
    corpus_id: str,
    formal_reference_xml: bytes | None = None,
) -> tuple[FormalMetadataAuthorityCatalog, dict[str, Any]]:
    if not crossref_response or len(crossref_response) > 10 * 1024 * 1024:
        raise ValueError("Crossref response must contain between 1 byte and 10 MiB")
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
    volume = str(message.get("volume", "")).strip()
    if not volume:
        raise ValueError("Crossref work has no volume")
    response_sha256 = hashlib.sha256(crossref_response).hexdigest()
    publication_date = _publication_date(message)
    formal_reference_sha256 = None
    if formal_reference_xml is not None:
        parser = etree.XMLParser(
            resolve_entities=False,
            load_dtd=False,
            no_network=True,
            recover=False,
            huge_tree=False,
        )
        root = etree.fromstring(formal_reference_xml, parser=parser)
        doi_nodes = cast(
            list[etree._Element],
            root.xpath("front/article-meta/article-id[@pub-id-type='doi']"),
        )
        reference_dois = {str(item.text or "").strip().casefold() for item in doi_nodes}
        if reference_dois != {doi}:
            raise ValueError("formal reference DOI does not match the source article")
        dates = cast(
            list[etree._Element],
            root.xpath("front/article-meta/pub-date[@date-type='pub']"),
        )
        if len(dates) != 1:
            raise ValueError("formal reference must contain exactly one publication date")
        day = dates[0].findtext("day")
        month = dates[0].findtext("month")
        year = dates[0].findtext("year")
        if not all((day, month, year)):
            raise ValueError("formal reference publication date must contain day, month, and year")
        publication_date = f"{year}-{month}-{day}"
        publication_parts(publication_date)
        if not refines_publication_date(_publication_date(message), publication_date):
            raise ValueError("formal reference publication date conflicts with Crossref")
        formal_reference_sha256 = hashlib.sha256(formal_reference_xml).hexdigest()
    base = {
        "version": CATALOG_VERSION,
        "corpus_id": corpus_id,
        "journal_profile_id": article.journal_profile_id,
        "source_idml_sha256": source_idml_sha256,
        "crossref_response_sha256": response_sha256,
        "doi": doi,
        "publication_date": publication_date,
        "volume": volume,
        "license_url": _license_url(message),
        "formal_reference_sha256": formal_reference_sha256,
        "human_review_required": True,
    }
    catalog = FormalMetadataAuthorityCatalog.model_validate(
        {"catalog_id": payload_digest(base), **base}
    )
    report = {
        "version": REPORT_VERSION,
        "catalog_id": catalog.catalog_id,
        "corpus_id": corpus_id,
        "source_idml_sha256": source_idml_sha256,
        "crossref_response_sha256": response_sha256,
        "publication_fields": 3,
        "formal_reference_sha256": formal_reference_sha256,
        "human_review_required": True,
        "restricted_content_emitted": False,
    }
    return catalog, report
