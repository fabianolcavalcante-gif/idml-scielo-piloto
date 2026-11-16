"""Administrative consent for public lookups, never consent to edit or publish XML."""

import json
import sys
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from idml_foundation.domain.common import content_digest
from idml_foundation.models import Artifact, Membership, Organization, Resource, User
from idml_foundation.services.audit import record_audit
from idml_foundation.services.canonical_heads import current_canonical_snapshot, lock_resource
from idml_foundation.services.snapshots import load_snapshot
from idml_foundation.services.validation_scope import validate_scope
from idml_foundation.services.web_source_policy import policy_for, public_article_permit
from idml_foundation.source_access_models import ArticleSourceDecision

PROFILE = "esa-aop-1.1.0"
PURPOSE = "public-validation-sources-1.0"


def administrative_actor(db: Session, organization_id: str, actor_id: str) -> bool:
    user = db.get(User, actor_id, populate_existing=True)
    org = db.get(Organization, organization_id, populate_existing=True)
    if user is None or not user.is_active or org is None or not org.is_active:
        return False
    if user.is_platform_admin:
        return True
    role = db.scalar(
        select(Membership.role).where(
            Membership.organization_id == organization_id,
            Membership.user_id == actor_id,
            Membership.is_active.is_(True),
        )
    )
    if role == "operator":
        policy = policy_for(organization_id)
        return policy is not None and policy.delegate_operators
    return role == "org_admin"


def latest(db: Session, organization_id: str, resource_id: str) -> ArticleSourceDecision | None:
    row = db.scalar(
        select(ArticleSourceDecision)
        .where(
            ArticleSourceDecision.organization_id == organization_id,
            ArticleSourceDecision.resource_id == resource_id,
        )
        .order_by(ArticleSourceDecision.sequence.desc())
        .limit(1)
        .execution_options(populate_existing=True)
    )
    if row is not None:
        r = row.receipt
        if (
            content_digest(r) != row.receipt_sha256
            or any(
                r.get(k) != getattr(row, k)
                for k in (
                    "organization_id",
                    "resource_id",
                    "actor_user_id",
                    "request_id",
                    "sequence",
                )
            )
            or r.get("decision_id") != row.id
            or r.get("version") != PURPOSE
        ):
            raise ValueError("source_decision_integrity")
    return row


def current_source(db: Session, organization_id: str, resource_id: str) -> Artifact:
    if (
        db.scalar(
            select(Resource.id).where(
                Resource.id == resource_id, Resource.organization_id == organization_id
            )
        )
        is None
    ):
        raise LookupError("article_not_found")
    snapshot = current_canonical_snapshot(
        db, organization_id=organization_id, resource_id=resource_id
    )
    if snapshot is None:
        raise ValueError("process_article_before_authorizing_sources")
    source = db.scalar(
        select(Artifact).where(
            Artifact.id == snapshot.source_artifact_id, Artifact.organization_id == organization_id
        )
    )
    if source is None or source.media_type != "application/vnd.adobe.indesign-idml-package":
        raise ValueError("source_idml_missing")
    # Profile comes from the persisted canonical document, never a consent payload.
    if getattr(load_snapshot(snapshot), "journal_profile_id", None) != PROFILE:
        raise ValueError("source_profile_not_qualified")
    return source


def decide(
    db: Session,
    *,
    organization_id: str,
    resource_id: str,
    actor_id: str,
    request_id: str,
    expected_sequence: int,
    action: str,
    days: int,
    correlation_id: str,
) -> ArticleSourceDecision:
    if not administrative_actor(db, organization_id, actor_id):
        raise PermissionError("source_administrator_required")
    if (
        str(UUID(request_id)) != request_id
        or action not in {"grant", "revoke"}
        or not 1 <= days <= 30
    ):
        raise ValueError("source_decision_invalid")
    lock_resource(db, organization_id, resource_id)
    request = dict(
        resource_id=resource_id,
        actor_user_id=actor_id,
        action=action,
        expected_sequence=expected_sequence,
        days=days,
    )
    hashed = content_digest(request)
    old = db.scalar(
        select(ArticleSourceDecision).where(
            ArticleSourceDecision.organization_id == organization_id,
            ArticleSourceDecision.request_id == request_id,
        )
    )
    if old is not None:
        if old.request_sha256 != hashed:
            raise ValueError("source_request_conflict")
        return old  # History only; never reactivates a revoked authorization.
    previous = latest(db, organization_id, resource_id)
    if expected_sequence != (previous.sequence if previous else 0):
        raise ValueError("source_sequence_conflict")
    source = current_source(db, organization_id, resource_id) if action == "grant" else None
    if action == "revoke" and previous is None:
        raise ValueError("source_authorization_missing")
    now = datetime.now(UTC)
    identifier = str(uuid4())
    source_hash = source.sha256 if source is not None else ""
    if source is None:
        assert previous is not None
        source_hash = previous.receipt["source_idml_sha256"]
    receipt: dict[str, Any] = dict(
        version=PURPOSE,
        decision_id=identifier,
        organization_id=organization_id,
        resource_id=resource_id,
        actor_user_id=actor_id,
        request_id=request_id,
        sequence=expected_sequence + 1,
        status="active" if action == "grant" else "revoked",
        source_idml_sha256=source_hash,
        journal_profile_id=PROFILE,
        destination="vps",
        issued_at=now.isoformat(),
        expires_at=(now + timedelta(days=days)).isoformat(),
        sources=["crossref", "orcid", "scielo_issue"],
        automatic_xml_changes_authorized=False,
        release_approved=False,
    )
    row = ArticleSourceDecision(
        id=identifier,
        organization_id=organization_id,
        resource_id=resource_id,
        actor_user_id=actor_id,
        request_id=request_id,
        request_sha256=hashed,
        sequence=expected_sequence + 1,
        receipt=receipt,
        receipt_sha256=content_digest(receipt),
    )
    db.add(row)
    db.flush()
    record_audit(
        db,
        action="article.sources." + action,
        resource_type="resource",
        resource_id=resource_id,
        organization_id=organization_id,
        actor_user_id=actor_id,
        correlation_id=correlation_id,
        outcome=receipt["status"],
        details={"decision_id": identifier, "decision_sha256": row.receipt_sha256},
    )
    return row


def resolve(db: Session, scope: dict[str, str]) -> dict[str, Any]:
    scope = validate_scope(scope)
    row = latest(db, scope["organization_id"], scope["resource_id"])
    owner = public_article_permit(scope, row.id if row else None)
    if owner is not None:
        organization = db.get(Organization, scope["organization_id"], populate_existing=True)
        if organization is None or not organization.is_active:
            raise ValueError("source_authorization_inactive")
        if (
            current_source(db, scope["organization_id"], scope["resource_id"]).sha256
            != scope["source_idml_sha256"]
        ):
            raise ValueError("source_authorization_source_changed")
        return dict(version=PURPOSE, scope=scope, **owner)
    if row is None:
        raise ValueError("source_authorization_missing")
    r = row.receipt
    now = datetime.now(UTC)
    issued, expires = (datetime.fromisoformat(r[k]) for k in ("issued_at", "expires_at"))
    if (
        r["status"] != "active"
        or issued.utcoffset() is None
        or expires.utcoffset() is None
        or not issued <= now < expires
        or expires - issued > timedelta(days=30)
        or any(r[k] != scope[k] for k in ("source_idml_sha256", "journal_profile_id"))
        or not administrative_actor(db, row.organization_id, row.actor_user_id)
    ):
        raise ValueError("source_authorization_inactive")
    if (
        current_source(db, row.organization_id, row.resource_id).sha256
        != scope["source_idml_sha256"]
    ):
        raise ValueError("source_authorization_source_changed")
    return dict(
        version=PURPOSE,
        decision_id=row.id,
        decision_sha256=row.receipt_sha256,
        scope=scope,
        expires_at=r["expires_at"],
    )


def main() -> None:
    """Fixed read-only supervisor entry point inside the API container; no HTTP bypass."""
    from idml_foundation.database import SessionLocal

    try:
        scope = json.loads(sys.stdin.buffer.read(4097))
        with SessionLocal() as db:
            result = resolve(db, scope)
        print(json.dumps(result))
    except Exception:
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
