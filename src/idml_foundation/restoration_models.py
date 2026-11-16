"""Private append-only validation evidence for restored working drafts."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column

from idml_foundation.database import Base
from idml_foundation.models import new_id, utcnow


class RestoredPackageValidation(Base):
    __tablename__ = "restored_package_validations"
    __table_args__ = (
        UniqueConstraint("organization_id", "request_id", name="uq_restored_validation_request"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    resource_id: Mapped[str] = mapped_column(ForeignKey("resources.id"), index=True)
    restore_event_id: Mapped[str] = mapped_column(ForeignKey("canonical_head_events.id"))
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("domain_snapshots.id"))
    request_id: Mapped[str] = mapped_column(String(36))
    request_sha256: Mapped[str] = mapped_column(String(64))
    xml_artifact_id: Mapped[str] = mapped_column(ForeignKey("artifacts.id"))
    package_artifact_id: Mapped[str] = mapped_column(ForeignKey("artifacts.id"))
    receipt: Mapped[dict[str, Any]] = mapped_column(JSON)
    receipt_sha256: Mapped[str] = mapped_column(String(64))
    reports: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


@event.listens_for(RestoredPackageValidation, "before_update")
@event.listens_for(RestoredPackageValidation, "before_delete")
def _immutable(*_: object) -> None:
    raise ValueError("restored_validation_history_is_append_only")
