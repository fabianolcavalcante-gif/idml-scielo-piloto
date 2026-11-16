from __future__ import annotations

import hashlib
import re
from typing import Any, Literal, Self, cast

from lxml import etree
from pydantic import Field, model_validator

from idml_foundation.ai.security import payload_digest
from idml_foundation.domain.canonical import (
    CanonicalArticle,
    FieldState,
    Identifier,
)
from idml_foundation.domain.common import (
    SHA256_PATTERN,
    Evidence,
    EvidenceLocator,
    SourceKind,
    StrictModel,
    stable_id,
)

CATALOG_VERSION = "editorial-enrichment-catalog-1.0"
REPORT_VERSION = "editorial-enrichment-qualification-1.0"
_ORCID_URL = re.compile(r"https?://orcid\.org/\d{4}-\d{4}-\d{4}-\d{3}[\dXx]")
_MAX_XML_BYTES = 100 * 1024 * 1024
_NOTE_LABELS = {
    "associate-editor": "Associate editor:",
    "scientific-editor": "Scientific editor:",
}


def _value_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _xml_root(payload: bytes) -> etree._Element:
    if not payload or len(payload) > _MAX_XML_BYTES:
        raise ValueError("approved XML must contain between 1 byte and 100 MiB")
    return etree.fromstring(
        payload,
        parser=etree.XMLParser(
            resolve_entities=False,
            load_dtd=False,
            no_network=True,
            recover=False,
            huge_tree=False,
        ),
    )


def _node_text(node: etree._Element) -> str:
    return " ".join(str(value) for value in node.itertext()).strip()


class EditorialIdentifierEnrichment(StrictModel):
    kind: Literal["other"]
    value: str = Field(min_length=1, max_length=200)
    value_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def value_hash_matches(self) -> Self:
        if _value_sha256(self.value) != self.value_sha256:
            raise ValueError("editorial identifier enrichment hash mismatch")
        return self


class EditorialNoteEnrichment(StrictModel):
    note_type: Literal["associate-editor", "scientific-editor"]
    current_value_sha256: str = Field(pattern=SHA256_PATTERN)
    enriched_value: str = Field(min_length=20, max_length=2_000)
    enriched_value_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def value_hash_and_orcid_match(self) -> Self:
        if _value_sha256(self.enriched_value) != self.enriched_value_sha256:
            raise ValueError("editorial note enrichment hash mismatch")
        if _ORCID_URL.search(self.enriched_value) is None:
            raise ValueError("editorial note enrichment requires an ORCID URL")
        return self


class EditorialEnrichmentCatalog(StrictModel):
    version: Literal["editorial-enrichment-catalog-1.0"]
    catalog_id: str = Field(pattern=SHA256_PATTERN)
    corpus_id: str = Field(min_length=3, max_length=100)
    journal_profile_id: str = Field(min_length=3, max_length=100)
    source_idml_sha256: str = Field(pattern=SHA256_PATTERN)
    approved_xml_sha256: str = Field(pattern=SHA256_PATTERN)
    identifiers: tuple[EditorialIdentifierEnrichment, ...]
    notes: tuple[EditorialNoteEnrichment, ...]
    human_review_required: Literal[True]

    @model_validator(mode="after")
    def catalog_is_complete_and_content_addressed(self) -> Self:
        if len(self.identifiers) != 1 or len(self.notes) != 2:
            raise ValueError("editorial enrichment catalog is incomplete")
        if len({note.note_type for note in self.notes}) != len(self.notes):
            raise ValueError("editorial enrichment catalog contains duplicate notes")
        if payload_digest(self.model_dump(mode="json", exclude={"catalog_id"})) != self.catalog_id:
            raise ValueError("editorial enrichment catalog ID mismatch")
        return self

    def apply(
        self,
        article: CanonicalArticle,
        *,
        source_idml_sha256: str,
    ) -> CanonicalArticle:
        if source_idml_sha256 != self.source_idml_sha256:
            raise ValueError("editorial enrichment source IDML hash mismatch")
        if article.journal_profile_id != self.journal_profile_id:
            raise ValueError("editorial enrichment journal profile mismatch")
        evidence_id = stable_id(
            article.article_id,
            "evidence",
            f"editorial-enrichment:{self.catalog_id}",
        )
        identifiers = list(article.front.article_identifiers)
        existing_identifiers = {
            (item.kind, item.value.value) for item in article.front.article_identifiers
        }
        for entry in self.identifiers:
            if (entry.kind, entry.value) in existing_identifiers:
                continue
            identifiers.append(
                Identifier(
                    kind=entry.kind,
                    value={
                        "value": entry.value,
                        "state": FieldState.PRESENT,
                        "evidence_ids": (evidence_id,),
                        "transformation": "approved-reference-enrichment",
                        "confidence": 1.0,
                    },
                )
            )
        enrichment_by_type: dict[str, EditorialNoteEnrichment] = {
            entry.note_type: entry for entry in self.notes
        }
        notes = []
        for note in article.back.notes:
            note_entry = enrichment_by_type.get(note.note_type)
            if note_entry is None:
                notes.append(note)
                continue
            current = note.content.plain.value or ""
            label = _NOTE_LABELS[note.note_type]
            legacy_current = f"{label} {current}"
            if _value_sha256(current) == note_entry.current_value_sha256:
                enriched_value = note_entry.enriched_value
            elif _value_sha256(legacy_current) == note_entry.current_value_sha256:
                enriched_value = note_entry.enriched_value
                if enriched_value.startswith(label):
                    enriched_value = enriched_value.removeprefix(label).strip()
            else:
                raise ValueError("editorial enrichment current note hash mismatch")
            plain = note.content.plain.model_copy(
                update={
                    "value": enriched_value,
                    "state": FieldState.PRESENT,
                    "evidence_ids": tuple(
                        dict.fromkeys((*note.content.plain.evidence_ids, evidence_id))
                    ),
                    "transformation": "approved-reference-orcid-enrichment",
                    "confidence": 1.0,
                }
            )
            content = note.content.model_copy(update={"plain": plain})
            notes.append(
                note.model_copy(
                    update={
                        "content": content,
                        "evidence_ids": tuple(dict.fromkeys((*note.evidence_ids, evidence_id))),
                    }
                )
            )
        if {note.note_type for note in notes} & set(enrichment_by_type) != set(enrichment_by_type):
            raise ValueError("editorial enrichment target notes are unavailable")
        evidence = Evidence(
            id=evidence_id,
            source_kind=SourceKind.SYSTEM,
            locator=EvidenceLocator(
                artifact_sha256=self.approved_xml_sha256,
                logical_path="approved-reference.xml",
                element_id=self.catalog_id[:32],
            ),
            content_sha256=self.catalog_id,
            description="Content-addressed approved-reference editorial enrichment",
        )
        review_reasons = [
            reason
            for reason in article.review_reasons
            if reason
            not in {
                "associate_editor_orcid_requires_enrichment",
                "scientific_editor_orcid_requires_enrichment",
            }
        ]
        review_reasons.append(f"editorial_enrichment_pending_human:{self.catalog_id}")
        enriched = article.model_copy(
            update={
                "front": article.front.model_copy(
                    update={"article_identifiers": tuple(identifiers)}
                ),
                "back": article.back.model_copy(update={"notes": tuple(notes)}),
                "evidence": (*article.evidence, evidence),
                "review_reasons": tuple(review_reasons),
            }
        )
        return CanonicalArticle.model_validate(enriched.model_dump(mode="json"))


def build_editorial_enrichment_catalog(
    *,
    article: CanonicalArticle,
    source_idml_sha256: str,
    approved_xml: bytes,
    corpus_id: str,
) -> tuple[EditorialEnrichmentCatalog, dict[str, Any]]:
    root = _xml_root(approved_xml)
    approved_xml_sha256 = hashlib.sha256(approved_xml).hexdigest()
    identifier_values = [
        _node_text(node)
        for node in cast(
            list[etree._Element],
            root.xpath("front/article-meta/article-id[@pub-id-type='other']"),
        )
        if _node_text(node)
    ]
    if len(identifier_values) != 1:
        raise ValueError("approved XML must contain exactly one other article identifier")
    identifiers = (
        EditorialIdentifierEnrichment(
            kind="other",
            value=identifier_values[0],
            value_sha256=_value_sha256(identifier_values[0]),
        ),
    )
    source_notes = {note.note_type: note.content.plain.value or "" for note in article.back.notes}
    note_entries: list[EditorialNoteEnrichment] = []
    for note_type, label in (
        ("associate-editor", "Associate editor"),
        ("scientific-editor", "Scientific editor"),
    ):
        nodes = cast(
            list[etree._Element],
            root.xpath("front/article-meta/author-notes/fn | body//fn | back//fn"),
        )
        matching: list[str] = []
        for node in nodes:
            if (node.findtext("label") or "").strip().removesuffix(":") != label:
                continue
            paragraphs = cast(list[etree._Element], node.xpath("p"))
            matching.extend(_node_text(paragraph) for paragraph in paragraphs)
        current = source_notes.get(note_type)
        if len(matching) != 1 or current is None:
            raise ValueError(f"approved XML editorial enrichment is incomplete: {note_type}")
        approved = matching[0]
        if _ORCID_URL.search(approved) is None or not approved.startswith(current):
            raise ValueError(f"approved XML editorial enrichment is inconsistent: {note_type}")
        note_entries.append(
            EditorialNoteEnrichment(
                note_type=note_type,
                current_value_sha256=_value_sha256(current),
                enriched_value=approved,
                enriched_value_sha256=_value_sha256(approved),
            )
        )
    base = {
        "version": CATALOG_VERSION,
        "corpus_id": corpus_id,
        "journal_profile_id": article.journal_profile_id,
        "source_idml_sha256": source_idml_sha256,
        "approved_xml_sha256": approved_xml_sha256,
        "identifiers": [item.model_dump(mode="json") for item in identifiers],
        "notes": [item.model_dump(mode="json") for item in note_entries],
        "human_review_required": True,
    }
    catalog = EditorialEnrichmentCatalog.model_validate(
        {"catalog_id": payload_digest(base), **base}
    )
    report = {
        "version": REPORT_VERSION,
        "catalog_id": catalog.catalog_id,
        "corpus_id": corpus_id,
        "source_idml_sha256": source_idml_sha256,
        "approved_xml_sha256": approved_xml_sha256,
        "article_identifiers": len(catalog.identifiers),
        "editorial_orcids": len(catalog.notes),
        "human_review_required": True,
        "restricted_content_emitted": False,
    }
    return catalog, report
