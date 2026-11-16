"""Private, append-only staging records. No candidate is a canonical snapshot/head."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column

from idml_foundation.database import Base
from idml_foundation.models import new_id, utcnow


class AutomationGrantRecord(Base):
    __tablename__ = "automation_grants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    resource_id: Mapped[str] = mapped_column(ForeignKey("resources.id"), index=True)
    base_snapshot_id: Mapped[str] = mapped_column(ForeignKey("domain_snapshots.id"), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    payload_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AutomationGrantRevocation(Base):
    __tablename__ = "automation_grant_revocations"

    grant_id: Mapped[str] = mapped_column(ForeignKey("automation_grants.id"), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    decision_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AutomationAttempt(Base):
    __tablename__ = "automation_attempts"
    __table_args__ = (
        UniqueConstraint("organization_id", "resource_id", "intent_sha256", name="uq_auto_intent"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    resource_id: Mapped[str] = mapped_column(ForeignKey("resources.id"), index=True)
    base_snapshot_id: Mapped[str] = mapped_column(ForeignKey("domain_snapshots.id"))
    intent_sha256: Mapped[str] = mapped_column(String(64))
    # Receipt is redacted; the candidate/XML/validation remain private tenant data.
    receipt: Mapped[dict[str, Any]] = mapped_column(JSON)
    receipt_sha256: Mapped[str] = mapped_column(String(64))
    candidate: Mapped[dict[str, Any] | None] = mapped_column(JSON(none_as_null=True))
    xml_content: Mapped[str | None] = mapped_column(Text)
    validation: Mapped[dict[str, Any] | None] = mapped_column(JSON(none_as_null=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AutomationDiscard(Base):
    __tablename__ = "automation_discards"

    attempt_id: Mapped[str] = mapped_column(ForeignKey("automation_attempts.id"), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    receipt: Mapped[dict[str, Any]] = mapped_column(JSON)
    receipt_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AutomationRevalidation(Base):
    __tablename__ = "automation_revalidations"
    __table_args__ = (
        UniqueConstraint("organization_id", "request_id", name="uq_auto_revalidation_request"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    resource_id: Mapped[str] = mapped_column(ForeignKey("resources.id"), index=True)
    attempt_id: Mapped[str] = mapped_column(ForeignKey("automation_attempts.id"), index=True)
    request_id: Mapped[str] = mapped_column(String(36))
    request_sha256: Mapped[str] = mapped_column(String(64))
    xml_artifact_id: Mapped[str] = mapped_column(ForeignKey("artifacts.id"))
    package_artifact_id: Mapped[str] = mapped_column(ForeignKey("artifacts.id"))
    receipt: Mapped[dict[str, Any]] = mapped_column(JSON)
    receipt_sha256: Mapped[str] = mapped_column(String(64))
    reports: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


def _immutable(*_: object) -> None:
    raise ValueError("autocorrection_history_is_append_only")


for _model in (
    AutomationGrantRecord,
    AutomationGrantRevocation,
    AutomationAttempt,
    AutomationDiscard,
    AutomationRevalidation,
):
    event.listen(_model, "before_update", _immutable)
    event.listen(_model, "before_delete", _immutable)
