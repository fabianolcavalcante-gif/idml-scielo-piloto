from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from idml_foundation.dependencies import (
    AuthenticatedContext,
    Configuration,
    CorrelationId,
    CurrentUser,
    Database,
    require_permission,
    require_recent_authentication,
)
from idml_foundation.models import Membership, OneTimeToken, Organization, User, utcnow
from idml_foundation.rbac import Permission, Role, TenantContext
from idml_foundation.schemas import (
    InvitationAccept,
    InvitationCreate,
    InvitationIssued,
    MembershipRead,
    MembershipUpdate,
    OrganizationRead,
)
from idml_foundation.security import (
    hash_one_time_token,
    hash_password,
    new_one_time_token,
    normalize_email,
    verify_password,
)
from idml_foundation.services.audit import record_audit

router = APIRouter(prefix="/v1/organizations", tags=["organizations"])


@router.get("", response_model=list[OrganizationRead])
def list_organizations(db: Database, user: CurrentUser) -> list[OrganizationRead]:
    rows = db.execute(
        select(Organization, Membership)
        .join(Membership, Membership.organization_id == Organization.id)
        .where(
            Membership.user_id == user.id,
            Membership.is_active.is_(True),
            Organization.is_active.is_(True),
        )
        .order_by(Organization.name)
    )
    return [
        OrganizationRead(id=org.id, slug=org.slug, name=org.name, role=membership.role)
        for org, membership in rows
    ]


@router.get("/{org_id}/members", response_model=list[MembershipRead])
def list_members(
    org_id: str,
    db: Database,
    context: Annotated[TenantContext, require_permission(Permission.ORGANIZATION_MANAGE)],
) -> list[MembershipRead]:
    if context.organization_id != org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="organization not found")
    rows = db.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.organization_id == org_id)
        .order_by(User.email)
    )
    return [
        MembershipRead(
            id=membership.id,
            user_id=user.id,
            email=user.email,
            role=membership.role,
            is_active=membership.is_active,
        )
        for membership, user in rows
    ]


@router.post("/{org_id}/invitations", response_model=InvitationIssued)
def invite_member(
    org_id: str,
    payload: InvitationCreate,
    db: Database,
    settings: Configuration,
    correlation_id: CorrelationId,
    context: Annotated[TenantContext, require_permission(Permission.MEMBERSHIP_MANAGE)],
    recent: Annotated[AuthenticatedContext, require_recent_authentication(require_mfa=True)],
) -> InvitationIssued:
    if context.organization_id != org_id or recent.user.id != context.user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="organization not found")
    email = normalize_email(str(payload.email))
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(
            email=email,
            password_hash=hash_password(new_one_time_token()),
            is_active=False,
        )
        db.add(user)
        db.flush()
    membership = db.scalar(
        select(Membership).where(
            Membership.organization_id == org_id,
            Membership.user_id == user.id,
        )
    )
    if membership is None:
        membership = Membership(
            organization_id=org_id,
            user_id=user.id,
            role=Role(payload.role).value,
            is_active=False,
        )
        db.add(membership)
        db.flush()
    elif membership.is_active:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="membership exists")
    else:
        membership.role = Role(payload.role).value
    raw = new_one_time_token()
    db.add(
        OneTimeToken(
            user_id=user.id,
            organization_id=org_id,
            purpose="invitation",
            token_hash=hash_one_time_token(raw, settings.session_pepper.get_secret_value()),
            expires_at=utcnow() + timedelta(days=7),
        )
    )
    record_audit(
        db,
        action="membership.invite",
        resource_type="membership",
        resource_id=membership.id,
        organization_id=org_id,
        actor_user_id=context.user.id,
        correlation_id=correlation_id,
        outcome="success",
        details={"role": membership.role},
    )
    return InvitationIssued(
        development_token=raw if settings.environment in {"development", "test"} else None
    )


@router.post("/invitations/accept", status_code=status.HTTP_204_NO_CONTENT)
def accept_invitation(
    payload: InvitationAccept,
    db: Database,
    settings: Configuration,
    correlation_id: CorrelationId,
) -> None:
    digest = hash_one_time_token(payload.token, settings.session_pepper.get_secret_value())
    token = db.scalar(
        select(OneTimeToken).where(
            OneTimeToken.token_hash == digest,
            OneTimeToken.purpose == "invitation",
            OneTimeToken.consumed_at.is_(None),
        )
    )
    expires_at = token.expires_at if token else datetime.min.replace(tzinfo=UTC)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if token is None or token.organization_id is None or expires_at <= datetime.now(UTC):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid token")
    user = db.get(User, token.user_id)
    membership = db.scalar(
        select(Membership).where(
            Membership.user_id == token.user_id,
            Membership.organization_id == token.organization_id,
        )
    )
    if user is None or membership is None or membership.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid token")
    if user.is_active:
        if not verify_password(payload.password, user.password_hash):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid token")
    else:
        user.password_hash = hash_password(payload.password)
        user.is_active = True
    user.token_version += 1
    membership.is_active = True
    token.consumed_at = utcnow()
    record_audit(
        db,
        action="membership.accept",
        resource_type="membership",
        resource_id=membership.id,
        organization_id=token.organization_id,
        actor_user_id=user.id,
        correlation_id=correlation_id,
        outcome="success",
        details={"role": membership.role},
    )


@router.patch("/{org_id}/members/{membership_id}", response_model=MembershipRead)
def update_membership(
    org_id: str,
    membership_id: str,
    payload: MembershipUpdate,
    db: Database,
    correlation_id: CorrelationId,
    context: Annotated[TenantContext, require_permission(Permission.MEMBERSHIP_MANAGE)],
    recent: Annotated[AuthenticatedContext, require_recent_authentication(require_mfa=True)],
) -> MembershipRead:
    if context.organization_id != org_id or recent.user.id != context.user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="organization not found")
    row = db.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(
            Membership.id == membership_id,
            Membership.organization_id == org_id,
        )
        .with_for_update()
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="membership not found")
    membership, user = row
    removing_admin = membership.role == Role.ORG_ADMIN.value and (
        payload.role != Role.ORG_ADMIN.value or not payload.is_active
    )
    if removing_admin:
        other_admins = db.scalar(
            select(func.count(Membership.id)).where(
                Membership.organization_id == org_id,
                Membership.id != membership.id,
                Membership.role == Role.ORG_ADMIN.value,
                Membership.is_active.is_(True),
            )
        )
        if not other_admins:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="organization must retain an active administrator",
            )
    membership.role = Role(payload.role).value
    membership.is_active = payload.is_active
    user.token_version += 1
    record_audit(
        db,
        action="membership.update",
        resource_type="membership",
        resource_id=membership.id,
        organization_id=org_id,
        actor_user_id=context.user.id,
        correlation_id=correlation_id,
        outcome="success",
        details={"role": membership.role, "is_active": membership.is_active},
    )
    return MembershipRead(
        id=membership.id,
        user_id=user.id,
        email=user.email,
        role=membership.role,
        is_active=membership.is_active,
    )
