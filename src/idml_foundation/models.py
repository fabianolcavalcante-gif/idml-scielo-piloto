from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from idml_foundation.database import Base


def new_id() -> str:
    return str(uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Organization(TimestampMixin, Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    token_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    mfa_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mfa_secret_ciphertext: Mapped[str | None] = mapped_column(Text)
    mfa_enabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mfa_last_counter: Mapped[int | None] = mapped_column(BigInteger)
    mfa_recovery_codes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Membership(TimestampMixin, Base):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_membership_org_user"),
        Index("ix_membership_user_org", "user_id", "organization_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(40), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ServiceAccount(TimestampMixin, Base):
    __tablename__ = "service_accounts"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_service_account_org_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    secret_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OneTimeToken(Base):
    __tablename__ = "one_time_tokens"
    __table_args__ = (Index("ix_one_time_token_user_purpose", "user_id", "purpose"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    organization_id: Mapped[str | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    purpose: Mapped[str] = mapped_column(String(40), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SessionToken(Base):
    __tablename__ = "session_tokens"
    __table_args__ = (Index("ix_session_user_active", "user_id", "expires_at", "revoked_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    token_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    authenticated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    mfa_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ip_hash: Mapped[str | None] = mapped_column(String(64))
    user_agent_hash: Mapped[str | None] = mapped_column(String(64))


class Resource(TimestampMixin, Base):
    """Minimal tenant-bound resource used by the foundation and isolation tests."""

    __tablename__ = "resources"
    __table_args__ = (Index("ix_resource_org_created", "organization_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class Artifact(TimestampMixin, Base):
    __tablename__ = "artifacts"
    __table_args__ = (
        UniqueConstraint("organization_id", "sha256", name="uq_artifact_org_sha256"),
        Index("ix_artifact_org_created", "organization_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    media_type: Mapped[str] = mapped_column(String(200), nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    scanner_status: Mapped[str] = mapped_column(String(40), nullable=False)
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Job(TimestampMixin, Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("organization_id", "idempotency_key", name="uq_job_org_idempotency"),
        Index("ix_job_org_state_created", "organization_id", "state", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(80), nullable=False)
    state: Mapped[str] = mapped_column(String(40), nullable=False, default="queued")
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(100))


class JobEffect(Base):
    __tablename__ = "job_effects"
    __table_args__ = (UniqueConstraint("job_id", "effect_key", name="uq_job_effect"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    effect_key: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class JobEvent(Base):
    __tablename__ = "job_events"
    __table_args__ = (
        UniqueConstraint("job_id", "sequence", name="uq_job_event_sequence"),
        Index("ix_job_event_org_created", "organization_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    from_state: Mapped[str | None] = mapped_column(String(40))
    to_state: Mapped[str] = mapped_column(String(40), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(40), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(100))
    correlation_id: Mapped[str] = mapped_column(String(100), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_org_created", "organization_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(80), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(100))
    correlation_id: Mapped[str] = mapped_column(String(100), nullable=False)
    outcome: Mapped[str] = mapped_column(String(40), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DomainSnapshot(TimestampMixin, Base):
    """Immutable, tenant-bound persisted Raw/Canonical model revision."""

    __tablename__ = "domain_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "resource_id", "model_kind", "revision", name="uq_snapshot_resource_kind_revision"
        ),
        UniqueConstraint(
            "resource_id",
            "model_kind",
            "content_sha256",
            name="uq_snapshot_resource_kind_content",
        ),
        Index("ix_snapshot_org_kind_created", "organization_id", "model_kind", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    resource_id: Mapped[str] = mapped_column(
        ForeignKey("resources.id", ondelete="RESTRICT"), nullable=False
    )
    source_artifact_id: Mapped[str | None] = mapped_column(
        ForeignKey("artifacts.id", ondelete="RESTRICT")
    )
    parent_snapshot_id: Mapped[str | None] = mapped_column(
        ForeignKey("domain_snapshots.id", ondelete="RESTRICT")
    )
    model_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(30), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class CanonicalHeadEvent(Base):
    """Append-only working-head lineage; never evidence of release approval."""

    __tablename__ = "canonical_head_events"
    __table_args__ = (
        UniqueConstraint("resource_id", "sequence", name="uq_canonical_head_sequence"),
        UniqueConstraint("organization_id", "request_id", name="uq_canonical_head_request"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    resource_id: Mapped[str] = mapped_column(ForeignKey("resources.id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("domain_snapshots.id"))
    previous_snapshot_id: Mapped[str | None] = mapped_column(ForeignKey("domain_snapshots.id"))
    previous_event_id: Mapped[str | None] = mapped_column(ForeignKey("canonical_head_events.id"))
    request_id: Mapped[str] = mapped_column(String(36))
    request_sha256: Mapped[str] = mapped_column(String(64))
    receipt: Mapped[dict[str, Any]] = mapped_column(JSON)
    receipt_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ReviewItem(TimestampMixin, Base):
    __tablename__ = "review_items"
    __table_args__ = (
        Index("ix_review_org_state_created", "organization_id", "state", "created_at"),
        Index("ix_review_resource_state", "resource_id", "state"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    resource_id: Mapped[str] = mapped_column(
        ForeignKey("resources.id", ondelete="RESTRICT"), nullable=False
    )
    base_snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("domain_snapshots.id", ondelete="RESTRICT"), nullable=False
    )
    job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    state: Mapped[str] = mapped_column(String(40), nullable=False, default="open")
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    rule_code: Mapped[str] = mapped_column(String(200), nullable=False)
    field_path: Mapped[str] = mapped_column(String(500), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    alternatives: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    assigned_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReviewDecision(Base):
    __tablename__ = "review_decisions"
    __table_args__ = (Index("ix_review_decision_item_created", "review_item_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    review_item_id: Mapped[str] = mapped_column(
        ForeignKey("review_items.id", ondelete="RESTRICT"), nullable=False
    )
    actor_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    base_snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("domain_snapshots.id", ondelete="RESTRICT"), nullable=False
    )
    result_snapshot_id: Mapped[str | None] = mapped_column(
        ForeignKey("domain_snapshots.id", ondelete="RESTRICT")
    )
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    patch: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    expected_version: Mapped[int] = mapped_column(Integer, nullable=False)
    patch_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ReviewBuild(Base):
    __tablename__ = "review_builds"
    __table_args__ = (
        UniqueConstraint("review_decision_id", name="uq_review_build_decision"),
        Index("ix_review_build_org_created", "organization_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    review_decision_id: Mapped[str] = mapped_column(
        ForeignKey("review_decisions.id", ondelete="RESTRICT"), nullable=False
    )
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("domain_snapshots.id", ondelete="RESTRICT"), nullable=False
    )
    xml_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    xml_content: Mapped[str] = mapped_column(Text, nullable=False)
    validation: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    validation_valid: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ReleaseRequest(TimestampMixin, Base):
    __tablename__ = "release_requests"
    __table_args__ = (
        UniqueConstraint("organization_id", "package_sha256", name="uq_release_org_package"),
        Index("ix_release_org_state_created", "organization_id", "state", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    resource_id: Mapped[str] = mapped_column(
        ForeignKey("resources.id", ondelete="RESTRICT"), nullable=False
    )
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("domain_snapshots.id", ondelete="RESTRICT"), nullable=False
    )
    package_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(40), nullable=False, default="pending")
    required_approvals: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    requested_by_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReleaseApproval(Base):
    __tablename__ = "release_approvals"
    __table_args__ = (
        UniqueConstraint("release_request_id", "approver_user_id", name="uq_release_approval_user"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    release_request_id: Mapped[str] = mapped_column(
        ForeignKey("release_requests.id", ondelete="RESTRICT"), nullable=False
    )
    approver_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AgentRun(Base):
    """Immutable accounting and policy record for one assistive invocation."""

    __tablename__ = "agent_runs"
    __table_args__ = (
        UniqueConstraint("organization_id", "idempotency_key", name="uq_agent_run_org_idempotency"),
        Index("ix_agent_run_org_created", "organization_id", "created_at"),
        Index("ix_agent_run_review_created", "review_item_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    resource_id: Mapped[str] = mapped_column(
        ForeignKey("resources.id", ondelete="RESTRICT"), nullable=False
    )
    review_item_id: Mapped[str] = mapped_column(
        ForeignKey("review_items.id", ondelete="RESTRICT"), nullable=False
    )
    base_snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("domain_snapshots.id", ondelete="RESTRICT"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    task_type: Mapped[str] = mapped_column(String(80), nullable=False)
    domain: Mapped[str] = mapped_column(String(40), nullable=False)
    orchestrator: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(80), nullable=False)
    output_schema_version: Mapped[str] = mapped_column(String(80), nullable=False)
    config_version: Mapped[str] = mapped_column(String(80), nullable=False)
    input_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    output_sha256: Mapped[str | None] = mapped_column(String(64))
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cached_input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_microusd: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    cost_source: Mapped[str] = mapped_column(String(20), nullable=False, default="unavailable")
    pricing_version: Mapped[str | None] = mapped_column(String(80))
    pricing_model_key: Mapped[str | None] = mapped_column(String(200))
    latency_ms: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    budget: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AgentProposal(Base):
    """Immutable, never auto-applied proposal produced by an AgentRun."""

    __tablename__ = "agent_proposals"
    __table_args__ = (
        UniqueConstraint("agent_run_id", name="uq_agent_proposal_run"),
        Index("ix_agent_proposal_org_created", "organization_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    agent_run_id: Mapped[str] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="RESTRICT"), nullable=False
    )
    review_item_id: Mapped[str] = mapped_column(
        ForeignKey("review_items.id", ondelete="RESTRICT"), nullable=False
    )
    base_snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("domain_snapshots.id", ondelete="RESTRICT"), nullable=False
    )
    domain: Mapped[str] = mapped_column(String(40), nullable=False)
    patch: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    alternatives: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    needs_human: Mapped[bool] = mapped_column(Boolean, nullable=False)
    proposal_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    validation: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
