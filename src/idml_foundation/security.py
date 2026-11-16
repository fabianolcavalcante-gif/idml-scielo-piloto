import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import cast

from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session

from idml_foundation.models import SessionToken, User, utcnow
from idml_foundation.settings import Settings

password_hasher = PasswordHash.recommended()


def normalize_email(email: str) -> str:
    return email.strip().casefold()


def hash_password(password: str) -> str:
    if len(password) < 14:
        raise ValueError("password must contain at least 14 characters")
    return password_hasher.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    return password_hasher.verify(password, encoded)


def hash_session_token(raw_token: str, pepper: str) -> str:
    return hmac.new(pepper.encode(), raw_token.encode(), hashlib.sha256).hexdigest()


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


@dataclass(frozen=True)
class IssuedSession:
    raw_token: str
    expires_at: datetime


def issue_session(
    db: Session,
    user: User,
    settings: Settings,
    *,
    ip: str | None = None,
    user_agent: str | None = None,
    mfa_verified: bool = False,
) -> IssuedSession:
    raw = secrets.token_urlsafe(48)
    pepper = settings.session_pepper.get_secret_value()
    expires = utcnow() + timedelta(seconds=settings.session_ttl_seconds)
    session = SessionToken(
        user_id=user.id,
        token_hash=hash_session_token(raw, pepper),
        token_version=user.token_version,
        expires_at=expires,
        authenticated_at=utcnow(),
        mfa_verified_at=utcnow() if mfa_verified else None,
        ip_hash=hashlib.sha256(ip.encode()).hexdigest() if ip else None,
        user_agent_hash=hashlib.sha256(user_agent.encode()).hexdigest() if user_agent else None,
    )
    db.add(session)
    db.flush()
    return IssuedSession(raw_token=raw, expires_at=expires)


def authenticate_session_record(
    db: Session, raw_token: str, settings: Settings
) -> tuple[User, SessionToken] | None:
    digest = hash_session_token(raw_token, settings.session_pepper.get_secret_value())
    statement = (
        select(User, SessionToken)
        .join(SessionToken, SessionToken.user_id == User.id)
        .where(SessionToken.token_hash == digest)
    )
    row = db.execute(statement).first()
    if row is None:
        return None
    user, session = row
    if (
        not user.is_active
        or session.revoked_at is not None
        or _aware(session.expires_at) <= datetime.now(UTC)
        or session.token_version != user.token_version
    ):
        return None
    session.last_seen_at = utcnow()
    return cast(User, user), cast(SessionToken, session)


def authenticate_session(db: Session, raw_token: str, settings: Settings) -> User | None:
    authenticated = authenticate_session_record(db, raw_token, settings)
    return authenticated[0] if authenticated else None


def revoke_session(db: Session, raw_token: str, settings: Settings) -> bool:
    digest = hash_session_token(raw_token, settings.session_pepper.get_secret_value())
    token = db.scalar(select(SessionToken).where(SessionToken.token_hash == digest))
    if token is None or token.revoked_at is not None:
        return False
    token.revoked_at = utcnow()
    return True


def new_one_time_token() -> str:
    """Invitation and recovery tokens use the same opaque-token primitive."""
    return secrets.token_urlsafe(48)


def hash_one_time_token(raw_token: str, pepper: str) -> str:
    return hmac.new(pepper.encode(), raw_token.encode(), hashlib.sha256).hexdigest()
