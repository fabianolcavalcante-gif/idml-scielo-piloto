from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from idml_foundation.database import get_db
from idml_foundation.ingest.scanner import ContentScanner, build_scanner
from idml_foundation.models import Membership, Organization, SessionToken, User
from idml_foundation.rate_limit import AuthRateLimiter, get_auth_rate_limiter
from idml_foundation.rbac import Permission, Role, TenantContext
from idml_foundation.security import authenticate_session_record
from idml_foundation.settings import Settings, get_settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/v1/auth/login")
Database = Annotated[Session, Depends(get_db)]
Configuration = Annotated[Settings, Depends(get_settings)]


@dataclass(frozen=True)
class AuthenticatedContext:
    user: User
    session: SessionToken


def get_authenticated_context(
    db: Database,
    settings: Configuration,
    token: Annotated[str, Depends(oauth2_scheme)],
) -> AuthenticatedContext:
    authenticated = authenticate_session_record(db, token, settings)
    if authenticated is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or expired session",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user, session = authenticated
    return AuthenticatedContext(user=user, session=session)


AuthContext = Annotated[AuthenticatedContext, Depends(get_authenticated_context)]


def get_current_user(authenticated: AuthContext) -> User:
    return authenticated.user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_tenant_context(
    db: Database,
    user: CurrentUser,
    organization_id: Annotated[str, Header(alias="X-Organization-ID")],
) -> TenantContext:
    organization = db.scalar(
        select(Organization).where(
            Organization.id == organization_id,
            Organization.is_active.is_(True),
        )
    )
    if organization is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="organization not found")
    if user.is_platform_admin:
        return TenantContext(user=user, organization_id=organization_id, role=Role.ORG_ADMIN)
    membership = db.scalar(
        select(Membership).where(
            Membership.organization_id == organization_id,
            Membership.user_id == user.id,
            Membership.is_active.is_(True),
        )
    )
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="organization not found")
    try:
        role = Role(membership.role)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="membership role is invalid"
        ) from exc
    return TenantContext(user=user, organization_id=organization_id, role=role)


Tenant = Annotated[TenantContext, Depends(get_tenant_context)]


def require_permission(permission: Permission) -> object:
    def dependency(context: Tenant) -> TenantContext:
        context.require(permission)
        return context

    return Depends(dependency)


def require_recent_authentication(*, require_mfa: bool) -> object:
    def dependency(authenticated: AuthContext) -> AuthenticatedContext:
        authenticated_at = authenticated.session.authenticated_at
        if authenticated_at.tzinfo is None:
            authenticated_at = authenticated_at.replace(tzinfo=UTC)
        if authenticated_at < datetime.now(UTC) - timedelta(minutes=10):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="recent authentication required",
            )
        if require_mfa:
            verified_at = authenticated.session.mfa_verified_at
            if authenticated.user.mfa_enabled_at is None or verified_at is None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="MFA verification required",
                )
        return authenticated

    return Depends(dependency)


def get_correlation_id(request: Request) -> str:
    return str(request.state.correlation_id)


CorrelationId = Annotated[str, Depends(get_correlation_id)]


def get_content_scanner(settings: Configuration) -> ContentScanner:
    return build_scanner(settings)


Scanner = Annotated[ContentScanner, Depends(get_content_scanner)]


def get_rate_limiter(settings: Configuration) -> AuthRateLimiter:
    return get_auth_rate_limiter(settings)


RateLimiter = Annotated[AuthRateLimiter, Depends(get_rate_limiter)]
