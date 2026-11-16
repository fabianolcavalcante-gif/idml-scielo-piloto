from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import Field
from sqlalchemy import select

from idml_foundation.dependencies import CorrelationId, Database, require_permission
from idml_foundation.domain.common import StrictModel
from idml_foundation.models import Resource
from idml_foundation.rbac import Permission, TenantContext
from idml_foundation.services.article_source_access import (
    PROFILE,
    administrative_actor,
    current_source,
    decide,
    latest,
    resolve,
)

router = APIRouter(prefix="/v1/resources/{resource_id}/public-sources", tags=["sources"])


class DecisionInput(StrictModel):
    request_id: UUID
    expected_sequence: int = Field(ge=0)
    action: Literal["grant", "revoke"]
    days: int = Field(default=7, ge=1, le=30)


@router.get("")
def read_status(
    resource_id: str,
    db: Database,
    context: Annotated[TenantContext, require_permission(Permission.RESOURCE_READ)],
) -> dict[str, Any]:
    if (
        db.scalar(
            select(Resource.id).where(
                Resource.id == resource_id, Resource.organization_id == context.organization_id
            )
        )
        is None
    ):
        raise HTTPException(404, "article not found")
    row = latest(db, context.organization_id, resource_id)
    state = "not_authorized"
    expires = row.receipt["expires_at"] if row else None
    try:
        source = current_source(db, context.organization_id, resource_id)
        effective = resolve(
            db,
            dict(
                organization_id=context.organization_id,
                resource_id=resource_id,
                source_idml_sha256=source.sha256,
                journal_profile_id=PROFILE,
                xml_sha256="0" * 64,
                package_sha256="0" * 64,
            ),
        )
        state = "active"
        expires = effective["expires_at"]
    except ValueError:
        if row is not None:
            state = "revoked" if row.receipt["status"] == "revoked" else "inactive"
    return dict(
        status=state,
        sequence=row.sequence if row else 0,
        expires_at=expires,
        can_manage=administrative_actor(db, context.organization_id, context.user.id),
        automatic_xml_changes_authorized=False,
        release_approved=False,
    )


@router.post("")
def record_decision(
    resource_id: str,
    payload: DecisionInput,
    db: Database,
    correlation_id: CorrelationId,
    context: Annotated[TenantContext, require_permission(Permission.RESOURCE_WRITE)],
) -> dict[str, Any]:
    try:
        row = decide(
            db,
            organization_id=context.organization_id,
            resource_id=resource_id,
            actor_id=context.user.id,
            request_id=str(payload.request_id),
            expected_sequence=payload.expected_sequence,
            action=payload.action,
            days=payload.days,
            correlation_id=correlation_id,
        )
    except LookupError:
        raise HTTPException(404, "article not found") from None
    except PermissionError:
        raise HTTPException(403, "source authorization permission required") from None
    except ValueError:
        raise HTTPException(
            409,
            "Recarregue o artigo; confirme a conversão no perfil habilitado "
            "e a versão da autorização.",
        ) from None
    return dict(
        decision_id=row.id,
        sequence=row.sequence,
        status=row.receipt["status"],
        expires_at=row.receipt["expires_at"],
        release_approved=False,
    )
