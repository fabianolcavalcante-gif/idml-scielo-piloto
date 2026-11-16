from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select, update

from idml_foundation.dependencies import (
    AuthContext,
    AuthenticatedContext,
    Configuration,
    CorrelationId,
    CurrentUser,
    Database,
    RateLimiter,
    oauth2_scheme,
    require_recent_authentication,
)
from idml_foundation.mfa import (
    consume_recovery_code,
    decrypt_secret,
    encrypt_secret,
    generate_recovery_codes,
    generate_totp_secret,
    hash_recovery_code,
    provisioning_uri,
    verify_totp,
)
from idml_foundation.models import OneTimeToken, SessionToken, User, utcnow
from idml_foundation.rate_limit import RateLimitResult, RateLimitUnavailable
from idml_foundation.schemas import (
    CurrentUserRead,
    LoginRequest,
    MfaConfirmRequest,
    MfaConfirmResponse,
    MfaSetupRequest,
    MfaSetupResponse,
    PasswordRecoveryComplete,
    PasswordRecoveryIssued,
    PasswordRecoveryRequest,
    SessionRead,
    SessionResponse,
)
from idml_foundation.security import (
    hash_one_time_token,
    hash_password,
    issue_session,
    new_one_time_token,
    normalize_email,
    revoke_session,
    verify_password,
)
from idml_foundation.services.audit import record_audit

router = APIRouter(prefix="/v1/auth", tags=["authentication"])
_DUMMY_PASSWORD_HASH = hash_password("rate-limit timing equalization password")
_DEVICE_COOKIE = "__Secure-idml-recovery"


def issue_recovery_secret(
    db: Database, user: User, settings: Configuration, *, purpose: str, lifetime: timedelta
) -> str:
    raw = new_one_time_token()
    db.add(
        OneTimeToken(
            user_id=user.id,
            purpose=purpose,
            token_hash=hash_one_time_token(raw, settings.session_pepper.get_secret_value()),
            expires_at=utcnow() + lifetime,
        )
    )
    return raw


def _rate_identities(request: Request, email: str) -> tuple[str, str]:
    client = request.client.host if request.client else "unknown"
    return f"account:{normalize_email(email)}", f"client:{client}"


def _enforce_rate_result(result: RateLimitResult) -> None:
    if not result.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="too many requests",
            headers={"Retry-After": str(result.retry_after_seconds)},
        )


def _check_rate_limit(
    limiter: RateLimiter,
    *,
    scope: str,
    identities: tuple[str, ...],
    limit: int,
) -> None:
    try:
        _enforce_rate_result(limiter.check(scope, identities, limit))
    except RateLimitUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="authentication temporarily unavailable",
        ) from exc


def _hit_rate_limit(
    limiter: RateLimiter,
    *,
    scope: str,
    identities: tuple[str, ...],
    limit: int,
    window_seconds: int,
) -> None:
    try:
        limiter.hit(scope, identities, limit, window_seconds)
    except RateLimitUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="authentication temporarily unavailable",
        ) from exc


def _record_login_denied(
    db: Database,
    *,
    correlation_id: str,
    reason: str,
    actor_user_id: str | None = None,
) -> None:
    record_audit(
        db,
        action="auth.login",
        resource_type="session",
        correlation_id=correlation_id,
        outcome="denied",
        actor_user_id=actor_user_id,
        details={"reason": reason},
    )
    # The request intentionally raises after this point. Persist the security event
    # independently of the dependency's rollback-on-error behavior.
    db.commit()


@router.post("/login", response_model=SessionResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Database,
    settings: Configuration,
    limiter: RateLimiter,
    correlation_id: CorrelationId,
) -> SessionResponse:
    identities = _rate_identities(request, str(payload.email))
    _check_rate_limit(
        limiter,
        scope="login",
        identities=identities,
        limit=settings.auth_login_max_failures,
    )
    user = db.scalar(
        select(User).where(User.email == normalize_email(str(payload.email))).with_for_update()
    )
    password_hash = (
        user.password_hash if user is not None and user.is_active else _DUMMY_PASSWORD_HASH
    )
    password_valid = verify_password(payload.password, password_hash)
    valid = user is not None and user.is_active and password_valid
    if not valid or user is None:
        _hit_rate_limit(
            limiter,
            scope="login",
            identities=identities,
            limit=settings.auth_login_max_failures,
            window_seconds=settings.auth_login_window_seconds,
        )
        _record_login_denied(
            db,
            correlation_id=correlation_id,
            reason="invalid_credentials",
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")

    mfa_verified = False
    if user.mfa_enabled_at is not None:
        if user.mfa_secret_ciphertext is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials"
            )
        if payload.mfa_code:
            secret = decrypt_secret(user.mfa_secret_ciphertext, settings)
            counter = verify_totp(
                secret,
                payload.mfa_code,
                last_counter=user.mfa_last_counter,
            )
            if counter is None:
                _hit_rate_limit(
                    limiter,
                    scope="login",
                    identities=identities,
                    limit=settings.auth_login_max_failures,
                    window_seconds=settings.auth_login_window_seconds,
                )
                _record_login_denied(
                    db,
                    correlation_id=correlation_id,
                    reason="invalid_mfa",
                    actor_user_id=user.id,
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials"
                )
            user.mfa_last_counter = counter
            mfa_verified = True
        elif payload.recovery_code:
            accepted, remaining = consume_recovery_code(
                payload.recovery_code, user.mfa_recovery_codes, settings
            )
            if not accepted:
                _hit_rate_limit(
                    limiter,
                    scope="login",
                    identities=identities,
                    limit=settings.auth_login_max_failures,
                    window_seconds=settings.auth_login_window_seconds,
                )
                _record_login_denied(
                    db,
                    correlation_id=correlation_id,
                    reason="invalid_mfa",
                    actor_user_id=user.id,
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials"
                )
            user.mfa_recovery_codes = remaining
            mfa_verified = True
        else:
            _hit_rate_limit(
                limiter,
                scope="login",
                identities=identities,
                limit=settings.auth_login_max_failures,
                window_seconds=settings.auth_login_window_seconds,
            )
            _record_login_denied(
                db,
                correlation_id=correlation_id,
                reason="mfa_required",
                actor_user_id=user.id,
            )
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="MFA required")

    try:
        limiter.reset("login", identities)
    except RateLimitUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="authentication temporarily unavailable",
        ) from exc

    issued = issue_session(
        db,
        user,
        settings,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        mfa_verified=mfa_verified,
    )
    user.last_login_at = utcnow()
    if payload.trust_browser:
        lifetime = timedelta(days=30)
        device = issue_recovery_secret(
            db, user, settings, purpose="recovery_device", lifetime=lifetime
        )
        response.set_cookie(
            _DEVICE_COOKIE,
            device,
            max_age=int(lifetime.total_seconds()),
            secure=True,
            httponly=True,
            samesite="strict",
            path="/v1/auth/recovery",
        )
    record_audit(
        db,
        action="auth.login",
        resource_type="session",
        correlation_id=correlation_id,
        outcome="success",
        actor_user_id=user.id,
        details={"mfa_verified": mfa_verified},
    )
    return SessionResponse(
        access_token=issued.raw_token,
        expires_at=issued.expires_at,
        mfa_required=user.mfa_required and user.mfa_enabled_at is None,
        mfa_verified=mfa_verified,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    db: Database,
    settings: Configuration,
    correlation_id: CorrelationId,
    authenticated: AuthContext,
    token: Annotated[str, Depends(oauth2_scheme)],
) -> None:
    revoked = revoke_session(db, token, settings)
    record_audit(
        db,
        action="auth.logout",
        resource_type="session",
        correlation_id=correlation_id,
        outcome="success" if revoked else "not_found",
        actor_user_id=authenticated.user.id,
    )


@router.get("/me", response_model=CurrentUserRead)
def me(user: CurrentUser) -> CurrentUserRead:
    return CurrentUserRead(
        id=user.id,
        email=user.email,
        is_platform_admin=user.is_platform_admin,
        mfa_required=user.mfa_required,
        mfa_enabled=user.mfa_enabled_at is not None,
    )


@router.get("/sessions", response_model=list[SessionRead])
def list_sessions(db: Database, user: CurrentUser) -> list[SessionToken]:
    return list(
        db.scalars(
            select(SessionToken)
            .where(SessionToken.user_id == user.id)
            .order_by(SessionToken.created_at.desc())
            .limit(50)
        )
    )


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_user_session(
    session_id: str,
    db: Database,
    user: CurrentUser,
    correlation_id: CorrelationId,
) -> None:
    session = db.scalar(
        select(SessionToken).where(
            SessionToken.id == session_id,
            SessionToken.user_id == user.id,
        )
    )
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")
    session.revoked_at = session.revoked_at or utcnow()
    record_audit(
        db,
        action="auth.session.revoke",
        resource_type="session",
        resource_id=session.id,
        correlation_id=correlation_id,
        outcome="success",
        actor_user_id=user.id,
    )


@router.post("/mfa/setup", response_model=MfaSetupResponse)
def setup_mfa(
    payload: MfaSetupRequest,
    db: Database,
    settings: Configuration,
    user: CurrentUser,
    correlation_id: CorrelationId,
) -> MfaSetupResponse:
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    if user.mfa_enabled_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="MFA already enabled")
    secret = generate_totp_secret()
    user.mfa_secret_ciphertext = encrypt_secret(secret, settings)
    user.mfa_enabled_at = None
    user.mfa_last_counter = None
    user.mfa_recovery_codes = []
    record_audit(
        db,
        action="auth.mfa.setup",
        resource_type="user",
        resource_id=user.id,
        correlation_id=correlation_id,
        outcome="pending_confirmation",
        actor_user_id=user.id,
    )
    return MfaSetupResponse(
        secret=secret,
        provisioning_uri=provisioning_uri(secret, user.email),
    )


@router.post("/mfa/confirm", response_model=MfaConfirmResponse)
def confirm_mfa(
    payload: MfaConfirmRequest,
    db: Database,
    settings: Configuration,
    user: CurrentUser,
    correlation_id: CorrelationId,
) -> MfaConfirmResponse:
    if user.mfa_secret_ciphertext is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="MFA setup not started")
    secret = decrypt_secret(user.mfa_secret_ciphertext, settings)
    counter = verify_totp(secret, payload.code, last_counter=user.mfa_last_counter)
    if counter is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid code")
    recovery_codes = generate_recovery_codes()
    user.mfa_last_counter = counter
    user.mfa_recovery_codes = [hash_recovery_code(code, settings) for code in recovery_codes]
    user.mfa_enabled_at = utcnow()
    user.token_version += 1
    record_audit(
        db,
        action="auth.mfa.enable",
        resource_type="user",
        resource_id=user.id,
        correlation_id=correlation_id,
        outcome="success",
        actor_user_id=user.id,
    )
    return MfaConfirmResponse(recovery_codes=recovery_codes)


@router.post("/recovery/support", response_model=PasswordRecoveryIssued)
def issue_support_link(
    payload: PasswordRecoveryRequest,
    db: Database,
    settings: Configuration,
    correlation_id: CorrelationId,
    recent: Annotated[AuthenticatedContext, require_recent_authentication(require_mfa=True)],
) -> PasswordRecoveryIssued:
    if not recent.user.is_platform_admin:
        raise HTTPException(status_code=403, detail="platform administrator required")
    user = db.scalar(
        select(User)
        .where(User.email == normalize_email(str(payload.email)), User.is_active.is_(True))
        .with_for_update()
    )
    if user is None:
        raise HTTPException(status_code=404, detail="active account not found")
    raw = issue_recovery_secret(
        db, user, settings, purpose="password_recovery", lifetime=timedelta(minutes=30)
    )
    record_audit(
        db,
        action="auth.recovery.support",
        resource_type="user",
        resource_id=user.id,
        actor_user_id=recent.user.id,
        correlation_id=correlation_id,
        outcome="success",
    )
    return PasswordRecoveryIssued(reset_token=raw)


@router.post("/recovery/request", response_model=PasswordRecoveryIssued)
def request_recovery(
    payload: PasswordRecoveryRequest,
    request: Request,
    db: Database,
    settings: Configuration,
    limiter: RateLimiter,
    correlation_id: CorrelationId,
) -> PasswordRecoveryIssued:
    email = normalize_email(str(payload.email))
    raw_device = request.cookies.get(_DEVICE_COOKIE, "")
    user = None
    if raw_device and len(raw_device) <= 200:
        user = db.scalar(
            select(User)
            .join(OneTimeToken, OneTimeToken.user_id == User.id)
            .where(
                User.email == email,
                User.is_active.is_(True),
                OneTimeToken.purpose == "recovery_device",
                OneTimeToken.token_hash
                == hash_one_time_token(raw_device, settings.session_pepper.get_secret_value()),
                OneTimeToken.consumed_at.is_(None),
                OneTimeToken.expires_at > utcnow(),
            )
            .with_for_update()
        )
    scope = "recovery-browser" if user is not None else "recovery"
    identities = (f"account:{email}",) if user is not None else _rate_identities(request, email)
    _check_rate_limit(
        limiter, scope=scope, identities=identities, limit=settings.auth_recovery_max_requests
    )
    _hit_rate_limit(
        limiter,
        scope=scope,
        identities=identities,
        limit=settings.auth_recovery_max_requests,
        window_seconds=settings.auth_recovery_window_seconds,
    )
    reset_token = None
    if user is not None:
        reset_token = issue_recovery_secret(
            db, user, settings, purpose="password_recovery", lifetime=timedelta(minutes=30)
        )
    record_audit(
        db,
        action="auth.recovery.request",
        resource_type="user",
        correlation_id=correlation_id,
        outcome="accepted",
    )
    return PasswordRecoveryIssued(reset_token=reset_token)


@router.post("/recovery/complete", status_code=status.HTTP_204_NO_CONTENT)
def complete_recovery(
    payload: PasswordRecoveryComplete,
    db: Database,
    settings: Configuration,
    correlation_id: CorrelationId,
) -> None:
    digest = hash_one_time_token(payload.token, settings.session_pepper.get_secret_value())
    user_id = db.scalar(
        select(OneTimeToken.user_id).where(
            OneTimeToken.token_hash == digest,
            OneTimeToken.purpose == "password_recovery",
            OneTimeToken.consumed_at.is_(None),
        )
    )
    user = db.scalar(select(User).where(User.id == user_id).with_for_update())
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid token")
    consumed_at = utcnow()
    claimed = db.scalar(
        update(OneTimeToken)
        .where(
            OneTimeToken.token_hash == digest,
            OneTimeToken.purpose == "password_recovery",
            OneTimeToken.consumed_at.is_(None),
            OneTimeToken.expires_at > consumed_at,
        )
        .values(consumed_at=consumed_at)
        .returning(OneTimeToken.id)
    )
    if claimed is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid token")
    user.password_hash = hash_password(payload.new_password)
    user.token_version += 1
    outstanding = db.scalars(
        select(OneTimeToken).where(
            OneTimeToken.user_id == user.id,
            OneTimeToken.purpose.in_(("password_recovery", "recovery_device")),
            OneTimeToken.consumed_at.is_(None),
        )
    )
    for outstanding_token in outstanding:
        outstanding_token.consumed_at = consumed_at
    record_audit(
        db,
        action="auth.recovery.complete",
        resource_type="user",
        resource_id=user.id,
        correlation_id=correlation_id,
        outcome="success",
        actor_user_id=user.id,
    )
