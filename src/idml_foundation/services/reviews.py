from __future__ import annotations

import copy
import hashlib
from typing import Any

from sqlalchemy import event, func, select, update
from sqlalchemy.orm import Mapper, Session

from idml_foundation.database import ensure_write_transaction
from idml_foundation.domain.canonical import CanonicalArticle
from idml_foundation.domain.common import canonical_bytes, content_digest
from idml_foundation.models import (
    DomainSnapshot,
    ReleaseApproval,
    ReviewBuild,
    ReviewDecision,
    ReviewItem,
    utcnow,
)
from idml_foundation.pipeline.jats_builder import JatsBuilder
from idml_foundation.pipeline.profile import JournalProfile
from idml_foundation.pipeline.validation import OfflineJatsValidator
from idml_foundation.schemas import JsonPatchOperation, ReviewDecisionCreate
from idml_foundation.services.canonical_heads import current_canonical_snapshot, lock_resource
from idml_foundation.services.snapshots import load_snapshot, store_snapshot

_FORBIDDEN_SEGMENTS = {
    "article_id",
    "content_sha256",
    "evidence",
    "evidence_ids",
    "id",
    "journal_profile_id",
    "schema_version",
    "source_raw_sha256",
}


@event.listens_for(ReviewDecision, "before_update")
@event.listens_for(ReviewDecision, "before_delete")
@event.listens_for(ReviewBuild, "before_update")
@event.listens_for(ReviewBuild, "before_delete")
@event.listens_for(ReleaseApproval, "before_update")
@event.listens_for(ReleaseApproval, "before_delete")
def _prevent_review_history_mutation(
    mapper: Mapper[Any], connection: object, target: object
) -> None:
    del mapper, connection, target
    raise ValueError("decision history is append-only")


def _segments(path: str) -> list[str]:
    if not path.startswith("/") or path == "/":
        raise ValueError("patch path must be a non-root JSON Pointer")
    segments = [part.replace("~1", "/").replace("~0", "~") for part in path[1:].split("/")]
    if any(not segment for segment in segments):
        raise ValueError("patch path contains an empty segment")
    if _FORBIDDEN_SEGMENTS.intersection(segments):
        raise ValueError("patch path targets an immutable field")
    return segments


def validate_review_path(path: str) -> None:
    segments = _segments(path)
    if segments[0] not in {"front", "body", "back", "assets"}:
        raise ValueError("review path is outside editable canonical content")


def _pointer_value(document: Any, path: str) -> Any:
    current = document
    for segment in _segments(path):
        if isinstance(current, list):
            try:
                current = current[int(segment)]
            except (ValueError, IndexError) as exc:
                raise ValueError("patch path contains an invalid list index") from exc
        elif isinstance(current, dict) and segment in current:
            current = current[segment]
        else:
            raise ValueError("patch path does not exist")
    return current


def _replace_pointer(document: Any, operation: JsonPatchOperation) -> None:
    segments = _segments(operation.path)
    current = document
    for segment in segments[:-1]:
        if isinstance(current, list):
            try:
                current = current[int(segment)]
            except (ValueError, IndexError) as exc:
                raise ValueError("patch path contains an invalid list index") from exc
        elif isinstance(current, dict) and segment in current:
            current = current[segment]
        else:
            raise ValueError("patch path does not exist")
    leaf = segments[-1]
    if isinstance(current, list):
        try:
            index = int(leaf)
            current[index] = operation.value
        except (ValueError, IndexError) as exc:
            raise ValueError("patch path contains an invalid list index") from exc
    elif isinstance(current, dict) and leaf in current:
        current[leaf] = operation.value
    else:
        raise ValueError("patch path does not exist")


def _path_is_scoped(operation_path: str, item_path: str) -> bool:
    return operation_path == item_path or operation_path.startswith(f"{item_path}/")


def _rich_text_root(path: str) -> str | None:
    """Return the RichText root for one of its coupled scalar/inline paths."""
    plain_suffix = "/plain/value"
    if path.endswith(plain_suffix):
        return path[: -len(plain_suffix)]
    marker = "/inlines"
    if marker in path:
        root, remainder = path.split(marker, maxsplit=1)
        if not remainder or remainder.startswith("/"):
            return root
    return None


def _atomic_rich_text_paths(root: str) -> tuple[str, str]:
    return f"{root}/plain/value", f"{root}/inlines"


def _formula_root(path: str) -> str | None:
    for suffix in ("/source/value", "/representation"):
        if path.endswith(suffix):
            return path[: -len(suffix)]
    return None


def _atomic_formula_paths(root: str) -> tuple[str, str]:
    return f"{root}/source/value", f"{root}/representation"


def validate_patch_scope_and_atomicity(
    document: dict[str, Any],
    patch: tuple[JsonPatchOperation, ...],
    item_path: str,
) -> None:
    """Validate scope and coupled RichText changes before mutating a candidate.

    `plain.value` and `inlines` are one semantic value. Replacing only one side can
    create an invalid or misleading canonical article, so both operations must be
    present in the same transaction. The companion sibling is allowed even when
    the review item points at the scalar `plain.value` path.
    """
    paths = [operation.path for operation in patch]
    if len(paths) != len(set(paths)):
        raise ValueError("patch contains duplicate paths")

    item_rich_root = _rich_text_root(item_path)
    item_atomic_paths = (
        set(_atomic_rich_text_paths(item_rich_root)) if item_rich_root is not None else set()
    )
    item_formula_root = _formula_root(item_path)
    item_formula_paths = (
        set(_atomic_formula_paths(item_formula_root)) if item_formula_root is not None else set()
    )
    touched_roots: set[str] = set()
    touched_formula_roots: set[str] = set()
    for operation in patch:
        validate_review_path(operation.path)
        if not _path_is_scoped(operation.path, item_path):
            if operation.path not in item_atomic_paths | item_formula_paths:
                raise ValueError("patch path is outside the review item scope")
        root = _rich_text_root(operation.path)
        if root is not None:
            try:
                candidate = _pointer_value(document, root)
            except ValueError:
                candidate = None
            if (
                isinstance(candidate, dict)
                and isinstance(candidate.get("plain"), dict)
                and "value" in candidate["plain"]
                and isinstance(candidate.get("inlines"), list)
            ):
                touched_roots.add(root)
        formula_root = _formula_root(operation.path)
        if formula_root is not None:
            try:
                formula = _pointer_value(document, formula_root)
            except ValueError:
                formula = None
            if (
                isinstance(formula, dict)
                and formula.get("kind") == "formula"
                and isinstance(formula.get("source"), dict)
                and "value" in formula["source"]
                and "representation" in formula
            ):
                touched_formula_roots.add(formula_root)

    path_set = set(paths)
    for root in touched_roots:
        plain_path, inlines_path = _atomic_rich_text_paths(root)
        if any(path.startswith(f"{inlines_path}/") for path in path_set):
            raise ValueError(f"RichText patches must replace the complete {inlines_path} array")
        relevant = {
            path
            for path in path_set
            if path == plain_path or path == inlines_path or path.startswith(f"{inlines_path}/")
        }
        if relevant and {plain_path, inlines_path} - path_set:
            raise ValueError(
                "RichText changes require an atomic patch replacing both "
                f"{plain_path} and {inlines_path}"
            )
    for root in touched_formula_roots:
        source_path, representation_path = _atomic_formula_paths(root)
        relevant = {path for path in path_set if path in {source_path, representation_path}}
        if relevant and {source_path, representation_path} - path_set:
            raise ValueError(
                "formula changes require an atomic patch replacing both "
                f"{source_path} and {representation_path}"
            )


def claim_review_item(
    db: Session,
    *,
    organization_id: str,
    item_id: str,
    user_id: str,
    expected_version: int,
) -> ReviewItem | None:
    resource_id = db.scalar(
        select(ReviewItem.resource_id).where(
            ReviewItem.id == item_id, ReviewItem.organization_id == organization_id
        )
    )
    if resource_id is None:
        return None
    lock_resource(db, organization_id, resource_id)
    result = db.execute(
        update(ReviewItem)
        .where(
            ReviewItem.id == item_id,
            ReviewItem.organization_id == organization_id,
            ReviewItem.state == "open",
            ReviewItem.version == expected_version,
        )
        .values(
            state="claimed",
            assigned_user_id=user_id,
            version=ReviewItem.version + 1,
            updated_at=utcnow(),
        )
    )
    if result.rowcount != 1:  # type: ignore[attr-defined]
        return None
    return db.scalar(
        select(ReviewItem).where(
            ReviewItem.id == item_id,
            ReviewItem.organization_id == organization_id,
        )
    )


def apply_review_decision(
    db: Session,
    *,
    organization_id: str,
    item_id: str,
    user_id: str,
    payload: ReviewDecisionCreate,
    profile: JournalProfile,
    validator: OfflineJatsValidator,
) -> tuple[ReviewItem, ReviewDecision, ReviewBuild | None]:
    ensure_write_transaction(db)
    with db.begin_nested():
        resource_id = db.scalar(
            select(ReviewItem.resource_id).where(
                ReviewItem.id == item_id, ReviewItem.organization_id == organization_id
            )
        )
        if resource_id is None:
            raise LookupError("review item not found")
        lock_resource(db, organization_id, resource_id)
        return _apply_review_decision(
            db,
            organization_id=organization_id,
            item_id=item_id,
            user_id=user_id,
            payload=payload,
            profile=profile,
            validator=validator,
        )


def _apply_review_decision(
    db: Session,
    *,
    organization_id: str,
    item_id: str,
    user_id: str,
    payload: ReviewDecisionCreate,
    profile: JournalProfile,
    validator: OfflineJatsValidator,
) -> tuple[ReviewItem, ReviewDecision, ReviewBuild | None]:
    item = db.scalar(
        select(ReviewItem)
        .where(
            ReviewItem.id == item_id,
            ReviewItem.organization_id == organization_id,
        )
        .execution_options(populate_existing=True)
    )
    if item is None:
        raise LookupError("review item not found")
    if item.state not in {"open", "claimed"}:
        raise RuntimeError("review item is not active")
    if item.assigned_user_id not in {None, user_id}:
        raise PermissionError("review item is claimed by another user")
    if item.version != payload.expected_version:
        raise RuntimeError("review item version conflict")

    claimed = db.execute(
        update(ReviewItem)
        .where(
            ReviewItem.id == item.id,
            ReviewItem.organization_id == organization_id,
            ReviewItem.version == payload.expected_version,
            ReviewItem.state.in_(("open", "claimed")),
        )
        .values(version=ReviewItem.version + 1, updated_at=utcnow())
        .execution_options(synchronize_session=False)
    )
    if claimed.rowcount != 1:  # type: ignore[attr-defined]
        raise RuntimeError("review item version conflict")
    item.version += 1

    patch_payload = [operation.model_dump(mode="json") for operation in payload.patch]
    patch_sha = hashlib.sha256(canonical_bytes({"patch": patch_payload})).hexdigest()
    decision = ReviewDecision(
        organization_id=organization_id,
        review_item_id=item.id,
        actor_user_id=user_id,
        base_snapshot_id=item.base_snapshot_id,
        action=payload.action,
        patch=patch_payload,
        justification=payload.justification,
        expected_version=payload.expected_version,
        patch_sha256=patch_sha,
    )

    if payload.action == "reject":
        if payload.patch:
            raise ValueError("reject decision cannot include a patch")
        db.add(decision)
        item.state = "rejected"
        item.assigned_user_id = user_id
        item.resolved_at = utcnow()
        db.flush()
        return item, decision, None
    if not payload.patch:
        raise ValueError("apply_patch decision requires at least one operation")

    base_snapshot = db.scalar(
        select(DomainSnapshot).where(
            DomainSnapshot.id == item.base_snapshot_id,
            DomainSnapshot.organization_id == organization_id,
            DomainSnapshot.resource_id == item.resource_id,
            DomainSnapshot.model_kind == "canonical",
        )
    )
    if base_snapshot is None:
        raise ValueError("review base snapshot is unavailable")
    current_snapshot = current_canonical_snapshot(
        db, organization_id=organization_id, resource_id=item.resource_id
    )
    if current_snapshot is None or current_snapshot.id != base_snapshot.id:
        raise RuntimeError("review base snapshot is stale")
    base_document = load_snapshot(base_snapshot)
    if not isinstance(base_document, CanonicalArticle):
        raise ValueError("review base is not canonical")
    updated_payload = copy.deepcopy(base_snapshot.payload)
    validate_patch_scope_and_atomicity(updated_payload, payload.patch, item.field_path)
    for operation in payload.patch:
        _replace_pointer(updated_payload, operation)
    reasons = updated_payload.get("review_reasons", [])
    updated_payload["review_reasons"] = [reason for reason in reasons if reason != item.rule_code]
    updated_document = CanonicalArticle.model_validate(updated_payload)
    if updated_document == base_document:
        raise ValueError("patch does not change the canonical model")

    next_revision = (
        db.scalar(
            select(func.max(DomainSnapshot.revision)).where(
                DomainSnapshot.organization_id == organization_id,
                DomainSnapshot.resource_id == item.resource_id,
                DomainSnapshot.model_kind == "canonical",
            )
        )
        or 0
    ) + 1
    snapshot, created = store_snapshot(
        db,
        organization_id=organization_id,
        resource_id=item.resource_id,
        document=updated_document,
        revision=next_revision,
        source_artifact_id=base_snapshot.source_artifact_id,
        parent_snapshot_id=base_snapshot.id,
    )
    if not created:
        raise ValueError("patch duplicates an existing canonical revision")
    decision.result_snapshot_id = snapshot.id
    db.add(decision)
    db.flush()
    xml = JatsBuilder(sps_version=profile.sps_version).build(updated_document)
    validation = validator.validate(
        xml, asset_names={asset.logical_name for asset in updated_document.assets}
    )
    build = ReviewBuild(
        organization_id=organization_id,
        review_decision_id=decision.id,
        snapshot_id=snapshot.id,
        xml_sha256=hashlib.sha256(xml).hexdigest(),
        xml_content=xml.decode("utf-8"),
        validation=validation.model_dump(mode="json"),
        validation_valid=validation.valid,
    )
    db.add(build)
    item.state = "resolved"
    item.assigned_user_id = user_id
    item.resolved_at = utcnow()
    db.execute(
        update(ReviewItem)
        .where(
            ReviewItem.organization_id == organization_id,
            ReviewItem.resource_id == item.resource_id,
            ReviewItem.id != item.id,
            ReviewItem.state.in_(("open", "claimed")),
            ReviewItem.base_snapshot_id == base_snapshot.id,
        )
        .values(
            base_snapshot_id=snapshot.id,
            version=ReviewItem.version + 1,
            state="open",
            assigned_user_id=None,
            updated_at=utcnow(),
        )
    )
    db.flush()
    return item, decision, build


def snapshot_diff(before: Any, after: Any, path: str = "") -> list[dict[str, Any]]:
    if before == after:
        return []
    if isinstance(before, dict) and isinstance(after, dict):
        changes: list[dict[str, Any]] = []
        for key in sorted(set(before) | set(after)):
            escaped = key.replace("~", "~0").replace("/", "~1")
            child = f"{path}/{escaped}"
            if key not in before:
                changes.append({"path": child, "after": after[key]})
            elif key not in after:
                changes.append({"path": child, "before": before[key]})
            else:
                changes.extend(snapshot_diff(before[key], after[key], child))
        return changes
    if isinstance(before, list) and isinstance(after, list):
        changes = []
        for index in range(max(len(before), len(after))):
            child = f"{path}/{index}"
            if index >= len(before):
                changes.append({"path": child, "after": after[index]})
            elif index >= len(after):
                changes.append({"path": child, "before": before[index]})
            else:
                changes.extend(snapshot_diff(before[index], after[index], child))
        return changes
    return [{"path": path or "/", "before": before, "after": after}]


def validate_proposed_patch(
    db: Session,
    *,
    organization_id: str,
    item_id: str,
    expected_version: int,
    patch: tuple[JsonPatchOperation, ...],
    profile: JournalProfile,
    validator: OfflineJatsValidator,
) -> dict[str, Any]:
    """Validate an assistive patch without persisting or applying it."""
    item = db.scalar(
        select(ReviewItem).where(
            ReviewItem.id == item_id,
            ReviewItem.organization_id == organization_id,
        )
    )
    if item is None:
        raise LookupError("review item not found")
    if item.state not in {"open", "claimed"} or item.version != expected_version:
        raise RuntimeError("review item version conflict")
    if not patch:
        raise ValueError("proposal requires at least one operation")
    snapshot = db.scalar(
        select(DomainSnapshot).where(
            DomainSnapshot.id == item.base_snapshot_id,
            DomainSnapshot.organization_id == organization_id,
            DomainSnapshot.resource_id == item.resource_id,
            DomainSnapshot.model_kind == "canonical",
        )
    )
    if snapshot is None:
        raise ValueError("review base snapshot is unavailable")
    current_snapshot = current_canonical_snapshot(
        db, organization_id=organization_id, resource_id=item.resource_id
    )
    if current_snapshot is None or current_snapshot.id != snapshot.id:
        raise RuntimeError("review base snapshot is stale")
    updated_payload = copy.deepcopy(snapshot.payload)
    validate_patch_scope_and_atomicity(updated_payload, patch, item.field_path)
    for operation in patch:
        _replace_pointer(updated_payload, operation)
    updated_document = CanonicalArticle.model_validate(updated_payload)
    base_document = load_snapshot(snapshot)
    if updated_document == base_document:
        raise ValueError("proposal does not change the canonical model")
    xml = JatsBuilder(sps_version=profile.sps_version).build(updated_document)
    validation = validator.validate(
        xml, asset_names={asset.logical_name for asset in updated_document.assets}
    )
    return {
        "accepted": True,
        "base_snapshot_id": snapshot.id,
        "candidate_content_sha256": content_digest(updated_document),
        "xml_sha256": hashlib.sha256(xml).hexdigest(),
        "validation_valid": validation.valid,
        "validation": validation.model_dump(mode="json"),
    }
