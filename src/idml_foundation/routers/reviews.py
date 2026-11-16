from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import select

from idml_foundation.dependencies import Configuration, CorrelationId, Database, require_permission
from idml_foundation.models import DomainSnapshot, Resource, ReviewBuild, ReviewDecision, ReviewItem
from idml_foundation.pipeline.profile import load_profile
from idml_foundation.pipeline.validation import OfflineJatsValidator
from idml_foundation.rbac import Permission, TenantContext
from idml_foundation.schemas import (
    ReviewBuildRead,
    ReviewClaim,
    ReviewDecisionCreate,
    ReviewDecisionHistoryRead,
    ReviewDecisionRead,
    ReviewItemCreate,
    ReviewItemRead,
    SnapshotDiffEntry,
    SnapshotRead,
)
from idml_foundation.services.audit import record_audit
from idml_foundation.services.canonical_heads import lock_resource
from idml_foundation.services.reviews import (
    apply_review_decision,
    claim_review_item,
    snapshot_diff,
    validate_review_path,
)

router = APIRouter(prefix="/v1", tags=["reviews"])


@router.post("/reviews", response_model=ReviewItemRead, status_code=status.HTTP_201_CREATED)
def create_review_item(
    payload: ReviewItemCreate,
    db: Database,
    correlation_id: CorrelationId,
    context: Annotated[TenantContext, require_permission(Permission.RESOURCE_WRITE)],
) -> ReviewItem:
    validate_review_path(payload.field_path)
    resource = db.scalar(
        select(Resource).where(
            Resource.id == payload.resource_id,
            Resource.organization_id == context.organization_id,
        )
    )
    snapshot = db.scalar(
        select(DomainSnapshot).where(
            DomainSnapshot.id == payload.base_snapshot_id,
            DomainSnapshot.resource_id == payload.resource_id,
            DomainSnapshot.organization_id == context.organization_id,
            DomainSnapshot.model_kind == "canonical",
        )
    )
    if resource is None or snapshot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="resource not found")
    lock_resource(db, context.organization_id, resource.id)
    item = ReviewItem(
        organization_id=context.organization_id,
        resource_id=payload.resource_id,
        base_snapshot_id=payload.base_snapshot_id,
        job_id=payload.job_id,
        category=payload.category,
        rule_code=payload.rule_code,
        field_path=payload.field_path,
        message=payload.message,
        evidence=payload.evidence,
        alternatives=payload.alternatives,
        priority=payload.priority,
    )
    db.add(item)
    db.flush()
    record_audit(
        db,
        action="review.create",
        resource_type="review_item",
        resource_id=item.id,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        correlation_id=correlation_id,
        outcome="success",
        details={"rule_code": item.rule_code, "field_path": item.field_path},
    )
    return item


@router.get("/reviews", response_model=list[ReviewItemRead])
def list_review_items(
    db: Database,
    context: Annotated[TenantContext, require_permission(Permission.RESOURCE_READ)],
    state_filter: Annotated[str | None, Query(alias="state")] = None,
) -> list[ReviewItem]:
    statement = select(ReviewItem).where(ReviewItem.organization_id == context.organization_id)
    if state_filter:
        statement = statement.where(ReviewItem.state == state_filter)
    return list(
        db.scalars(statement.order_by(ReviewItem.priority, ReviewItem.created_at).limit(200))
    )


@router.get("/reviews/{item_id}", response_model=ReviewItemRead)
def get_review_item(
    item_id: str,
    db: Database,
    context: Annotated[TenantContext, require_permission(Permission.RESOURCE_READ)],
) -> ReviewItem:
    item = db.scalar(
        select(ReviewItem).where(
            ReviewItem.id == item_id,
            ReviewItem.organization_id == context.organization_id,
        )
    )
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="review not found")
    return item


@router.post("/reviews/{item_id}/claim", response_model=ReviewItemRead)
def claim_item(
    item_id: str,
    payload: ReviewClaim,
    db: Database,
    correlation_id: CorrelationId,
    context: Annotated[TenantContext, require_permission(Permission.REVIEW_WRITE)],
) -> ReviewItem:
    item = claim_review_item(
        db,
        organization_id=context.organization_id,
        item_id=item_id,
        user_id=context.user.id,
        expected_version=payload.expected_version,
    )
    if item is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="review version conflict")
    record_audit(
        db,
        action="review.claim",
        resource_type="review_item",
        resource_id=item.id,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        correlation_id=correlation_id,
        outcome="success",
        details={"version": item.version},
    )
    return item


@router.post("/reviews/{item_id}/decisions", response_model=ReviewDecisionRead)
def decide_review(
    item_id: str,
    payload: ReviewDecisionCreate,
    db: Database,
    settings: Configuration,
    correlation_id: CorrelationId,
    context: Annotated[TenantContext, require_permission(Permission.REVIEW_WRITE)],
) -> ReviewDecisionRead:
    vendor = Path(__file__).resolve().parents[3] / "vendor" / "jats" / "1.3"
    try:
        item, decision, build = apply_review_decision(
            db,
            organization_id=context.organization_id,
            item_id=item_id,
            user_id=context.user.id,
            payload=payload,
            profile=load_profile(settings.journal_profile_path),
            validator=OfflineJatsValidator(vendor),
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    record_audit(
        db,
        action="review.decide",
        resource_type="review_item",
        resource_id=item.id,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        correlation_id=correlation_id,
        outcome=item.state,
        details={
            "action": decision.action,
            "patch_sha256": decision.patch_sha256,
            "result_snapshot_id": decision.result_snapshot_id,
            "validation_valid": build.validation_valid if build else None,
        },
    )
    return ReviewDecisionRead(
        decision_id=decision.id,
        review_item_id=item.id,
        state=item.state,
        result_snapshot_id=decision.result_snapshot_id,
        xml_sha256=build.xml_sha256 if build else None,
        validation_valid=build.validation_valid if build else None,
        build_id=build.id if build else None,
        version=item.version,
    )


@router.get("/reviews/{item_id}/history", response_model=list[ReviewDecisionHistoryRead])
def get_review_history(
    item_id: str,
    db: Database,
    context: Annotated[TenantContext, require_permission(Permission.RESOURCE_READ)],
) -> list[ReviewDecision]:
    item_exists = db.scalar(
        select(ReviewItem.id).where(
            ReviewItem.id == item_id,
            ReviewItem.organization_id == context.organization_id,
        )
    )
    if item_exists is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="review not found")
    return list(
        db.scalars(
            select(ReviewDecision)
            .where(
                ReviewDecision.review_item_id == item_id,
                ReviewDecision.organization_id == context.organization_id,
            )
            .order_by(ReviewDecision.created_at)
        )
    )


@router.get("/snapshots/{snapshot_id}", response_model=SnapshotRead)
def get_snapshot(
    snapshot_id: str,
    db: Database,
    context: Annotated[TenantContext, require_permission(Permission.RESOURCE_READ)],
) -> SnapshotRead:
    snapshot = db.scalar(
        select(DomainSnapshot).where(
            DomainSnapshot.id == snapshot_id,
            DomainSnapshot.organization_id == context.organization_id,
        )
    )
    if snapshot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="snapshot not found")
    return SnapshotRead(
        id=snapshot.id,
        resource_id=snapshot.resource_id,
        model_kind=snapshot.model_kind,
        schema_version=snapshot.schema_version,
        revision=snapshot.revision,
        content_sha256=snapshot.content_sha256,
        parent_snapshot_id=snapshot.parent_snapshot_id,
        payload=snapshot.payload,
    )


@router.get("/snapshots/{before_id}/diff/{after_id}", response_model=list[SnapshotDiffEntry])
def diff_snapshots(
    before_id: str,
    after_id: str,
    db: Database,
    context: Annotated[TenantContext, require_permission(Permission.RESOURCE_READ)],
) -> list[SnapshotDiffEntry]:
    snapshots = list(
        db.scalars(
            select(DomainSnapshot).where(
                DomainSnapshot.id.in_((before_id, after_id)),
                DomainSnapshot.organization_id == context.organization_id,
            )
        )
    )
    by_id = {snapshot.id: snapshot for snapshot in snapshots}
    if set(by_id) != {before_id, after_id}:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="snapshot not found")
    if by_id[before_id].resource_id != by_id[after_id].resource_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="lineages differ")
    changes = snapshot_diff(by_id[before_id].payload, by_id[after_id].payload)
    return [SnapshotDiffEntry.model_validate(change) for change in changes[:1000]]


@router.get("/review-builds/{build_id}", response_model=ReviewBuildRead)
def get_review_build(
    build_id: str,
    db: Database,
    context: Annotated[TenantContext, require_permission(Permission.RESOURCE_READ)],
) -> ReviewBuildRead:
    build = db.scalar(
        select(ReviewBuild).where(
            ReviewBuild.id == build_id,
            ReviewBuild.organization_id == context.organization_id,
        )
    )
    if build is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="build not found")
    return ReviewBuildRead(
        id=build.id,
        snapshot_id=build.snapshot_id,
        xml_sha256=build.xml_sha256,
        validation=build.validation,
        validation_valid=build.validation_valid,
        created_at=build.created_at,
    )


@router.get("/review-builds/{build_id}/xml")
def download_review_xml(
    build_id: str,
    db: Database,
    correlation_id: CorrelationId,
    context: Annotated[TenantContext, require_permission(Permission.RESOURCE_READ)],
) -> Response:
    build = db.scalar(
        select(ReviewBuild).where(
            ReviewBuild.id == build_id,
            ReviewBuild.organization_id == context.organization_id,
        )
    )
    if build is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="build not found")
    decision = db.get(ReviewDecision, build.review_decision_id)
    record_audit(
        db,
        action="review.xml.download",
        resource_type="review_build",
        resource_id=build.id,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        correlation_id=correlation_id,
        outcome="success",
        details={"xml_sha256": build.xml_sha256, "decision_id": decision.id if decision else None},
    )
    return Response(
        content=build.xml_content,
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{build.xml_sha256[:16]}.xml"'},
    )
