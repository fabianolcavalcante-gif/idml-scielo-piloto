from typing import Annotated

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from idml_foundation.dependencies import (
    AuthenticatedContext,
    CorrelationId,
    Database,
    require_permission,
    require_recent_authentication,
)
from idml_foundation.models import (
    DomainSnapshot,
    ReleaseApproval,
    ReleaseRequest,
    Resource,
    utcnow,
)
from idml_foundation.rbac import Permission, TenantContext
from idml_foundation.schemas import (
    ReleaseApprovalCreate,
    ReleaseApprovalHistoryRead,
    ReleaseApprovalRead,
    ReleaseRequestCreate,
    ReleaseRequestRead,
)
from idml_foundation.services.audit import record_audit

router = APIRouter(prefix="/v1/releases", tags=["releases"])


@router.post("", response_model=ReleaseRequestRead, status_code=status.HTTP_201_CREATED)
def create_release_request(
    payload: ReleaseRequestCreate,
    db: Database,
    correlation_id: CorrelationId,
    context: Annotated[TenantContext, require_permission(Permission.RELEASE_REQUEST)],
    recent: Annotated[AuthenticatedContext, require_recent_authentication(require_mfa=True)],
) -> ReleaseRequest:
    resource = db.scalar(
        select(Resource).where(
            Resource.id == payload.resource_id,
            Resource.organization_id == context.organization_id,
        )
    )
    snapshot = db.scalar(
        select(DomainSnapshot).where(
            DomainSnapshot.id == payload.snapshot_id,
            DomainSnapshot.resource_id == payload.resource_id,
            DomainSnapshot.organization_id == context.organization_id,
            DomainSnapshot.model_kind == "canonical",
        )
    )
    if resource is None or snapshot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="resource not found")
    request = ReleaseRequest(
        organization_id=context.organization_id,
        resource_id=payload.resource_id,
        snapshot_id=payload.snapshot_id,
        package_sha256=payload.package_sha256,
        requested_by_user_id=recent.user.id,
        required_approvals=2,
    )
    db.add(request)
    db.flush()
    record_audit(
        db,
        action="release.request",
        resource_type="release_request",
        resource_id=request.id,
        organization_id=context.organization_id,
        actor_user_id=recent.user.id,
        correlation_id=correlation_id,
        outcome="pending",
        details={"package_sha256": request.package_sha256, "required_approvals": 2},
    )
    return request


@router.get("", response_model=list[ReleaseRequestRead])
def list_release_requests(
    db: Database,
    context: Annotated[TenantContext, require_permission(Permission.RESOURCE_READ)],
) -> list[ReleaseRequest]:
    return list(
        db.scalars(
            select(ReleaseRequest)
            .where(ReleaseRequest.organization_id == context.organization_id)
            .order_by(ReleaseRequest.created_at.desc())
            .limit(200)
        )
    )


@router.get("/{request_id}/approvals", response_model=list[ReleaseApprovalHistoryRead])
def list_release_approvals(
    request_id: str,
    db: Database,
    context: Annotated[TenantContext, require_permission(Permission.AUDIT_READ)],
) -> list[ReleaseApproval]:
    request_exists = db.scalar(
        select(ReleaseRequest.id).where(
            ReleaseRequest.id == request_id,
            ReleaseRequest.organization_id == context.organization_id,
        )
    )
    if request_exists is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="release not found")
    return list(
        db.scalars(
            select(ReleaseApproval)
            .where(
                ReleaseApproval.release_request_id == request_id,
                ReleaseApproval.organization_id == context.organization_id,
            )
            .order_by(ReleaseApproval.created_at)
        )
    )


@router.post("/{request_id}/approvals", response_model=ReleaseApprovalRead)
def approve_release(
    request_id: str,
    payload: ReleaseApprovalCreate,
    db: Database,
    correlation_id: CorrelationId,
    context: Annotated[TenantContext, require_permission(Permission.RELEASE_APPROVE)],
    recent: Annotated[AuthenticatedContext, require_recent_authentication(require_mfa=True)],
) -> ReleaseApprovalRead:
    request = db.scalar(
        select(ReleaseRequest)
        .where(
            ReleaseRequest.id == request_id,
            ReleaseRequest.organization_id == context.organization_id,
        )
        .with_for_update()
    )
    if request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="release not found")
    if request.state != "pending" or request.version != payload.expected_version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="release version conflict")
    if request.requested_by_user_id == recent.user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="requester cannot approve their own release",
        )
    approval = ReleaseApproval(
        organization_id=context.organization_id,
        release_request_id=request.id,
        approver_user_id=recent.user.id,
        justification=payload.justification,
        evidence_sha256=payload.evidence_sha256,
    )
    db.add(approval)
    try:
        db.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="user already approved this release",
        ) from exc
    approval_count = (
        db.scalar(
            select(func.count(ReleaseApproval.id)).where(
                ReleaseApproval.release_request_id == request.id
            )
        )
        or 0
    )
    request.version += 1
    if approval_count >= request.required_approvals:
        # Editorial approval is deliberately distinct from the technical release policy.
        request.state = "editorially_approved"
        request.approved_at = utcnow()
    record_audit(
        db,
        action="release.approve",
        resource_type="release_request",
        resource_id=request.id,
        organization_id=context.organization_id,
        actor_user_id=recent.user.id,
        correlation_id=correlation_id,
        outcome=request.state,
        details={
            "approval_count": approval_count,
            "required_approvals": request.required_approvals,
            "evidence_sha256": approval.evidence_sha256,
        },
    )
    return ReleaseApprovalRead(
        id=approval.id,
        release_request_id=request.id,
        approver_user_id=approval.approver_user_id,
        created_at=approval.created_at,
        request_state=request.state,
        request_version=request.version,
        approval_count=approval_count,
    )
