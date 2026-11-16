import json
from typing import Annotated

from fastapi import APIRouter, Query, Response
from sqlalchemy import select

from idml_foundation.dependencies import (
    AuthenticatedContext,
    CorrelationId,
    Database,
    require_permission,
    require_recent_authentication,
)
from idml_foundation.models import AuditEvent
from idml_foundation.rbac import Permission, TenantContext
from idml_foundation.schemas import AuditEventRead
from idml_foundation.services.audit import record_audit

router = APIRouter(prefix="/v1/audit", tags=["audit"])


@router.get("", response_model=list[AuditEventRead])
def list_audit_events(
    db: Database,
    context: Annotated[TenantContext, require_permission(Permission.AUDIT_READ)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[AuditEvent]:
    return list(
        db.scalars(
            select(AuditEvent)
            .where(AuditEvent.organization_id == context.organization_id)
            .order_by(AuditEvent.created_at.desc())
            .limit(limit)
        )
    )


@router.get("/export")
def export_audit_events(
    db: Database,
    correlation_id: CorrelationId,
    context: Annotated[TenantContext, require_permission(Permission.AUDIT_READ)],
    recent: Annotated[AuthenticatedContext, require_recent_authentication(require_mfa=True)],
) -> Response:
    events = list(
        db.scalars(
            select(AuditEvent)
            .where(AuditEvent.organization_id == context.organization_id)
            .order_by(AuditEvent.created_at)
            .limit(10_000)
        )
    )
    payload = [AuditEventRead.model_validate(event).model_dump(mode="json") for event in events]
    record_audit(
        db,
        action="audit.export",
        resource_type="audit",
        organization_id=context.organization_id,
        actor_user_id=recent.user.id,
        correlation_id=correlation_id,
        outcome="success",
        details={"event_count": len(payload)},
    )
    return Response(
        content=json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="audit-export.json"'},
    )
