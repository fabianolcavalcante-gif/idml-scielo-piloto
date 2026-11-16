"""Working-head transitions, not publication or automatic promotion authority.

Internal server service. No restore endpoint/agent tool is exposed. Caller commits.
Legacy resources retain their highest revision until the first explicit transition.
"""

from uuid import UUID, uuid4

from sqlalchemy import event, select, update
from sqlalchemy.orm import Session

from idml_foundation.database import ensure_write_transaction
from idml_foundation.domain.common import content_digest
from idml_foundation.models import (
    CanonicalHeadEvent,
    DomainSnapshot,
    Resource,
    ReviewDecision,
    ReviewItem,
    utcnow,
)


@event.listens_for(CanonicalHeadEvent, "before_update")
@event.listens_for(CanonicalHeadEvent, "before_delete")
def _immutable(*_: object) -> None:
    raise ValueError("canonical_head_history_is_append_only")


def lock_resource(db: Session, organization_id: str, resource_id: str) -> Resource:
    ensure_write_transaction(db)
    resource = db.scalar(
        select(Resource)
        .where(Resource.id == resource_id, Resource.organization_id == organization_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if resource is None:
        raise LookupError("resource not found in organization")
    return resource


def _event(db: Session, organization_id: str, resource_id: str) -> CanonicalHeadEvent | None:
    row = db.scalar(
        select(CanonicalHeadEvent)
        .where(
            CanonicalHeadEvent.organization_id == organization_id,
            CanonicalHeadEvent.resource_id == resource_id,
        )
        .order_by(CanonicalHeadEvent.sequence.desc())
        .limit(1)
        .execution_options(populate_existing=True)
    )
    return _verified(row) if row is not None else None


def _verified(row: CanonicalHeadEvent) -> CanonicalHeadEvent:
    receipt = row.receipt
    if (
        content_digest(receipt) != row.receipt_sha256
        or receipt.get("organization_id") != row.organization_id
        or receipt.get("resource_id") != row.resource_id
        or receipt.get("snapshot_id") != row.snapshot_id
        or receipt.get("previous_snapshot_id") != row.previous_snapshot_id
        or receipt.get("previous_event_id") != row.previous_event_id
        or receipt.get("sequence") != row.sequence
        or receipt.get("request_id") != row.request_id
        or receipt.get("request_sha256") != row.request_sha256
        or receipt.get("release_approved") is not False
        or receipt.get("requires_revalidation") is not True
    ):
        raise ValueError("canonical_head_integrity_failure")
    return row


def current_canonical_snapshot(
    db: Session, *, organization_id: str, resource_id: str
) -> DomainSnapshot | None:
    row = _event(db, organization_id, resource_id)
    query = select(DomainSnapshot).where(
        DomainSnapshot.organization_id == organization_id,
        DomainSnapshot.resource_id == resource_id,
        DomainSnapshot.model_kind == "canonical",
    )
    if row is not None:
        query = query.where(DomainSnapshot.id == row.snapshot_id)
    else:
        query = query.order_by(DomainSnapshot.revision.desc()).limit(1)
    snapshot = db.scalar(query.execution_options(populate_existing=True))
    if row is not None and (
        snapshot is None or snapshot.content_sha256 != row.receipt["snapshot_sha256"]
    ):
        raise ValueError("canonical_head_integrity_failure")
    return snapshot


def _append_head(
    db: Session,
    *,
    resource: Resource,
    snapshot: DomainSnapshot,
    previous: DomainSnapshot | None,
    action: str,
    request_id: UUID,
    request_sha256: str,
    rebase_reviews: bool,
) -> CanonicalHeadEvent:
    """Only callers holding the resource lock may transition a trusted draft."""
    last = _event(db, resource.organization_id, resource.id)
    if previous is not None:
        resource.version += 1
    receipt = {
        "version": "canonical-working-head-1.0",
        "organization_id": resource.organization_id,
        "resource_id": resource.id,
        "sequence": last.sequence + 1 if last else 1,
        "snapshot_id": snapshot.id,
        "snapshot_sha256": snapshot.content_sha256,
        "previous_snapshot_id": previous.id if previous else None,
        "previous_snapshot_sha256": previous.content_sha256 if previous else None,
        "previous_event_id": last.id if last else None,
        "previous_receipt_sha256": last.receipt_sha256 if last else None,
        "request_id": str(request_id),
        "request_sha256": request_sha256,
        "action": action,
        "resource_version": resource.version,
        "requires_revalidation": True,
        "release_approved": False,
    }
    row = CanonicalHeadEvent(
        organization_id=resource.organization_id,
        resource_id=resource.id,
        sequence=receipt["sequence"],
        snapshot_id=snapshot.id,
        previous_snapshot_id=previous.id if previous else None,
        previous_event_id=last.id if last else None,
        request_id=str(request_id),
        request_sha256=request_sha256,
        receipt=receipt,
        receipt_sha256=content_digest(receipt),
    )
    db.add(row)
    if rebase_reviews and previous is not None:
        db.execute(
            update(ReviewItem)
            .where(
                ReviewItem.organization_id == resource.organization_id,
                ReviewItem.resource_id == resource.id,
                ReviewItem.state.in_(("open", "claimed")),
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
    return row


def record_snapshot_head(
    db: Session, resource: Resource, snapshot: DomainSnapshot, previous: DomainSnapshot | None
) -> CanonicalHeadEvent:
    """Internal writer hook for newly stored canonical drafts (not IA candidates)."""
    return _append_head(
        db,
        resource=resource,
        snapshot=snapshot,
        previous=previous,
        action="snapshot",
        request_id=uuid4(),
        request_sha256=content_digest({"snapshot_id": snapshot.id}),
        rebase_reviews=False,
    )


def restore_working_head(
    db: Session,
    *,
    organization_id: str,
    resource_id: str,
    target_snapshot_id: str,
    expected_snapshot_id: str,
    expected_resource_version: int,
    request_id: UUID,
) -> CanonicalHeadEvent:
    """Restore a prior non-human draft, preserving snapshots and invalidating old work.

    Does not restore a release, authorize an agent or inherit validation. Refuses
    all resources with human decisions; a reviewed-article undo needs its own policy.
    A replay returns historical evidence, never moves the current head again.
    """
    request_id = UUID(str(request_id))
    digest = content_digest(
        {
            "resource_id": resource_id,
            "target_snapshot_id": target_snapshot_id,
            "expected_snapshot_id": expected_snapshot_id,
            "expected_resource_version": expected_resource_version,
        }
    )
    ensure_write_transaction(db)
    with db.begin_nested():
        resource = lock_resource(db, organization_id, resource_id)
        replay = db.scalar(
            select(CanonicalHeadEvent).where(
                CanonicalHeadEvent.organization_id == organization_id,
                CanonicalHeadEvent.request_id == str(request_id),
            )
        )
        if replay is not None:
            if replay.request_sha256 != digest or replay.resource_id != resource_id:
                raise ValueError("canonical_head_request_conflict")
            return _verified(replay)
        current = current_canonical_snapshot(
            db, organization_id=organization_id, resource_id=resource_id
        )
        if (
            current is None
            or current.id != expected_snapshot_id
            or resource.version != expected_resource_version
        ):
            raise RuntimeError("canonical_head_version_conflict")
        if target_snapshot_id == current.id:
            raise ValueError("canonical_head_restore_no_change")
        if db.scalar(
            select(ReviewItem.id)
            .where(
                ReviewItem.organization_id == organization_id,
                ReviewItem.resource_id == resource_id,
                ReviewItem.state == "claimed",
            )
            .limit(1)
        ):
            raise ValueError("canonical_head_human_claim_protected")
        if db.scalar(
            select(ReviewDecision.id)
            .join(ReviewItem, ReviewItem.id == ReviewDecision.review_item_id)
            .where(
                ReviewDecision.organization_id == organization_id,
                ReviewItem.organization_id == organization_id,
                ReviewItem.resource_id == resource_id,
            )
            .limit(1)
        ):
            raise ValueError("canonical_head_human_decisions_protected")
        target = db.scalar(
            select(DomainSnapshot).where(
                DomainSnapshot.id == target_snapshot_id,
                DomainSnapshot.organization_id == organization_id,
                DomainSnapshot.resource_id == resource_id,
                DomainSnapshot.model_kind == "canonical",
            )
        )
        seen = db.scalar(
            select(CanonicalHeadEvent)
            .where(
                CanonicalHeadEvent.organization_id == organization_id,
                CanonicalHeadEvent.resource_id == resource_id,
                (CanonicalHeadEvent.snapshot_id == target_snapshot_id)
                | (CanonicalHeadEvent.previous_snapshot_id == target_snapshot_id),
            )
            .limit(1)
        )
        if (
            target is None
            or seen is None
            or target.source_artifact_id != current.source_artifact_id
            or content_digest(target.payload) != target.content_sha256
            or content_digest(current.payload) != current.content_sha256
        ):
            raise ValueError("canonical_head_restore_target_invalid")
        _verified(seen)
        seen_sha = seen.receipt[
            "snapshot_sha256" if seen.snapshot_id == target.id else "previous_snapshot_sha256"
        ]
        if target.content_sha256 != seen_sha:
            raise ValueError("canonical_head_restore_target_invalid")
        return _append_head(
            db,
            resource=resource,
            snapshot=target,
            previous=current,
            action="restore",
            request_id=request_id,
            request_sha256=digest,
            rebase_reviews=True,
        )
