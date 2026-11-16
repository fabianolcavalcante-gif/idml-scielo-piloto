from __future__ import annotations

import hashlib
import re
from collections import Counter
from collections.abc import Iterable
from pathlib import PurePosixPath
from typing import Any

from pydantic import Field

from idml_foundation.domain.common import SHA256_PATTERN, Evidence, StrictModel, content_digest
from idml_foundation.domain.raw import RawArticle

_FORMULA_NAME = re.compile(r"(?:^|[_-])eq(?:-txt)?[-_]?\d+$", re.IGNORECASE)
_FIGURE_NAME = re.compile(r"(?:^|[_-])fig(?:ure)?[-_]?\d+$", re.IGNORECASE)
_AUXILIARY_GLYPH = re.compile(r"^[A-Za-z]$")


class CorrectiveInventorySummary(StrictModel):
    report_version: str = "1.0.0"
    source_idml_sha256: str = Field(pattern=SHA256_PATTERN)
    counts: dict[str, int]
    anchored_object_classes: dict[str, int]
    asset_media_types: dict[str, int]
    asset_name_classes: dict[str, int]
    link_relationships: dict[str, int]
    review_reason_families: dict[str, int]
    evidence_coverage: dict[str, int]
    unresolved_external_assets: int = Field(ge=0)
    private_inventory_sha256: str = Field(pattern=SHA256_PATTERN)
    content_emitted: bool = False


def classify_asset_name(logical_path: str) -> str:
    stem = PurePosixPath(logical_path.replace("\\", "/")).stem
    normalized = stem.casefold()
    if _FORMULA_NAME.search(stem):
        return "formula"
    if _FIGURE_NAME.search(stem):
        return "figure"
    if _AUXILIARY_GLYPH.fullmatch(stem):
        return "auxiliary-glyph"
    if "logo" in normalized or "selo" in normalized or "license" in normalized:
        return "layout-branding"
    return "other"


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _evidence_record(evidence: Evidence) -> dict[str, Any]:
    return {
        "id": evidence.id,
        "source_kind": evidence.source_kind.value,
        "locator": evidence.locator.model_dump(mode="json"),
        "content_sha256": evidence.content_sha256,
        "description_sha256": _sha256_text(evidence.description),
    }


def _records_for(
    evidence_by_id: dict[str, Evidence], evidence_ids: Iterable[str]
) -> list[dict[str, Any]]:
    return [_evidence_record(evidence_by_id[evidence_id]) for evidence_id in evidence_ids]


def build_corrective_inventory(
    raw: RawArticle,
    *,
    review_reasons: Iterable[str] = (),
) -> tuple[CorrectiveInventorySummary, dict[str, Any]]:
    evidence_by_id = {item.id: item for item in raw.evidence}
    asset_by_id = {item.id: item for item in raw.assets}

    paragraph_style_usage: Counter[str] = Counter()
    character_style_usage: Counter[str] = Counter()
    for story in raw.stories:
        paragraph_style_usage.update(
            item.paragraph_style_id for item in story.paragraphs if item.paragraph_style_id
        )
        character_style_usage.update(
            item.character_style_id for item in story.runs if item.character_style_id
        )

    private_inventory: dict[str, Any] = {
        "inventory_version": "1.0.0",
        "source_idml_sha256": raw.source_artifact_sha256,
        "anchored_objects": [
            {
                "id": item.id,
                "source_self_id": item.source_self_id,
                "kind": item.kind.value,
                "placement": item.placement.value,
                "label_sha256": _sha256_text(item.label) if item.label else None,
                "anchor_run_id": item.anchor_run_id,
                "asset_ids": list(item.asset_ids),
                "asset_logical_paths": [
                    asset_by_id[asset_id].logical_path for asset_id in item.asset_ids
                ],
                "page_index": item.page_index,
                "box": item.box.model_dump(mode="json") if item.box else None,
                "evidence": _records_for(evidence_by_id, item.evidence_ids),
            }
            for item in raw.anchored_objects
        ],
        "assets": [
            {
                "id": item.id,
                "logical_path": item.logical_path,
                "name_class": classify_asset_name(item.logical_path),
                "media_type": item.media_type,
                "external": item.external,
                "sha256": item.sha256,
                "size_bytes": item.size_bytes,
                "evidence": _records_for(evidence_by_id, item.evidence_ids),
            }
            for item in raw.assets
        ],
        "styles": [
            {
                "id": item.id,
                "source_name": item.source_name,
                "normalized_name": item.normalized_name,
                "kind": item.kind.value,
                "paragraph_uses": paragraph_style_usage[item.id],
                "character_uses": character_style_usage[item.id],
                "evidence": _records_for(evidence_by_id, item.evidence_ids),
            }
            for item in raw.styles
            if paragraph_style_usage[item.id] or character_style_usage[item.id]
        ],
        "stories": [
            {
                "id": item.id,
                "source_self_id": item.source_self_id,
                "runs": len(item.runs),
                "paragraphs": len(item.paragraphs),
                "tables": list(item.table_ids),
                "anchored_objects": list(item.anchored_object_ids),
                "notes": list(item.note_ids),
                "evidence": _records_for(evidence_by_id, item.evidence_ids),
            }
            for item in raw.stories
        ],
        "links": [
            {
                "id": item.id,
                "source_id": item.source_id,
                "relationship": item.relationship,
                "target_sha256": _sha256_text(item.target),
                "evidence": _records_for(evidence_by_id, item.evidence_ids),
            }
            for item in raw.links
        ],
        "reading_order_issues": [
            {
                "code": item.code,
                "story_id": item.story_id,
                "frame_id": item.frame_id,
                "details": item.details,
                "evidence": _records_for(evidence_by_id, item.evidence_ids),
            }
            for item in raw.reading_order_issues
        ],
    }

    object_classes = Counter(
        f"{item.kind.value}:{item.placement.value}" for item in raw.anchored_objects
    )
    asset_media_types = Counter(item.media_type for item in raw.assets)
    asset_name_classes = Counter(classify_asset_name(item.logical_path) for item in raw.assets)
    link_relationships = Counter(item.relationship for item in raw.links)
    reason_families = Counter(reason.split(":", 1)[0] for reason in review_reasons)
    evidence_with_artifact_hash = sum(bool(item.locator.artifact_sha256) for item in raw.evidence)
    summary = CorrectiveInventorySummary(
        source_idml_sha256=raw.source_artifact_sha256,
        counts={
            "stories": len(raw.stories),
            "frames": len(raw.frames),
            "spreads": len(raw.spreads),
            "styles": len(raw.styles),
            "tables": len(raw.tables),
            "anchored_objects": len(raw.anchored_objects),
            "assets": len(raw.assets),
            "links": len(raw.links),
            "notes": len(raw.notes),
            "evidence": len(raw.evidence),
            "reading_order": len(raw.reading_order),
            "reading_order_issues": len(raw.reading_order_issues),
        },
        anchored_object_classes=dict(sorted(object_classes.items())),
        asset_media_types=dict(sorted(asset_media_types.items())),
        asset_name_classes=dict(sorted(asset_name_classes.items())),
        link_relationships=dict(sorted(link_relationships.items())),
        review_reason_families=dict(sorted(reason_families.items())),
        evidence_coverage={
            "anchored_objects_with_evidence": sum(
                bool(item.evidence_ids) for item in raw.anchored_objects
            ),
            "assets_with_evidence": sum(bool(item.evidence_ids) for item in raw.assets),
            "styles_with_evidence": sum(bool(item.evidence_ids) for item in raw.styles),
            "links_with_evidence": sum(bool(item.evidence_ids) for item in raw.links),
            "evidence_with_artifact_hash": evidence_with_artifact_hash,
        },
        unresolved_external_assets=sum(
            item.external and (item.sha256 is None or item.size_bytes is None)
            for item in raw.assets
        ),
        private_inventory_sha256=content_digest(private_inventory),
    )
    return summary, private_inventory
