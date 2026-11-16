"""Append-only administrative decisions for public validation sources."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column

from idml_foundation.database import Base
from idml_foundation.models import new_id, utcnow


class ArticleSourceDecision(Base):
    __tablename__ = "article_source_decisions"
    __table_args__ = (
        UniqueConstraint("organization_id", "request_id", name="uq_source_decision_request"),
        UniqueConstraint("resource_id", "sequence", name="uq_source_decision_sequence"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    resource_id: Mapped[str] = mapped_column(ForeignKey("resources.id"), index=True)
    actor_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    request_id: Mapped[str] = mapped_column(String(36))
    request_sha256: Mapped[str] = mapped_column(String(64))
    sequence: Mapped[int] = mapped_column(Integer)
    receipt: Mapped[dict[str, Any]] = mapped_column(JSON)
    receipt_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


@event.listens_for(ArticleSourceDecision, "before_update")
@event.listens_for(ArticleSourceDecision, "before_delete")
def _immutable(*_: object) -> None:
    raise ValueError("source_decisions_are_append_only")
