"""Atomic working-draft promotion after fresh private revalidation.

Internal opt-in service: no route, worker or publication authority. Caller commits.
Successful request replay returns history and never moves the head a second time.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from idml_foundation.ai.autocorrection_contracts import (
    AutomationContext,
    AutomationIntent,
    intent_digest,
)
from idml_foundation.database import ensure_write_transaction
from idml_foundation.domain.common import content_digest
from idml_foundation.models import (
    CanonicalHeadEvent,
    DomainSnapshot,
    ReviewDecision,
    ReviewItem,
    utcnow,
)
from idml_foundation.pipeline.profile import JournalProfile
from idml_foundation.pipeline.validation import OfflineJatsValidator
from idml_foundation.services.autocorrection_history import read_revalidation, revalidate_and_store
from idml_foundation.services.autocorrection_package import _current_candidate
from idml_foundation.services.autocorrection_promotion_policy import POLICY, draft_admission
from idml_foundation.services.canonical_heads import (
    _event,
    _verified,
    current_canonical_snapshot,
    lock_resource,
)
from idml_foundation.services.package_validation import Executor
from idml_foundation.services.xpm_execution import XpmExecutor
from idml_foundation.settings import Settings


def _no_human_work(db: Session, organization_id: str, resource_id: str) -> None:
    if db.scalar(
        select(ReviewItem.id)
        .where(
            ReviewItem.organization_id == organization_id,
            ReviewItem.resource_id == resource_id,
            ReviewItem.state == "claimed",
        )
        .limit(1)
    ) or db.scalar(
        select(ReviewDecision.id)
        .join(ReviewItem, ReviewItem.id == ReviewDecision.review_item_id)
        .where(
            ReviewDecision.organization_id == organization_id,
            ReviewItem.organization_id == organization_id,
            ReviewItem.resource_id == resource_id,
        )
        .limit(1)
    ):
        raise ValueError("automation_promotion_human_work_protected")


def promote_revalidated_candidate(
    db: Session,
    *,
    organization_id: str,
    request_id: UUID,
    attempt_id: str,
    intent: AutomationIntent,
    context: AutomationContext,
    pdf_artifact_id: str,
    pdf_sha256: str,
    profile: JournalProfile,
    settings: Settings,
    validator: OfflineJatsValidator,
    executor: Executor | None = None,
    xpm_executor: XpmExecutor | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> dict[str, Any]:
    request_id = UUID(str(request_id))
    if str(context.scope.organization_id) != organization_id or intent.scope != context.scope:
        raise PermissionError("automation_scope_mismatch")
    resource_id = str(context.scope.resource_id)
    request_sha = content_digest(
        dict(
            action="autocorrection-promotion",
            policy=POLICY,
            resource_id=resource_id,
            attempt_id=attempt_id,
            intent_sha256=intent_digest(intent),
            pdf_artifact_id=pdf_artifact_id,
            pdf_sha256=pdf_sha256,
            profile_sha256=content_digest(profile),
        )
    )
    ensure_write_transaction(db)
    with db.begin_nested():
        resource = lock_resource(db, organization_id, resource_id)
        previous_request = db.scalar(
            select(CanonicalHeadEvent).where(
                CanonicalHeadEvent.organization_id == organization_id,
                CanonicalHeadEvent.request_id == str(request_id),
            )
        )
        if previous_request is not None:
            _verified(previous_request)
            if (
                previous_request.request_sha256 != request_sha
                or previous_request.resource_id != resource_id
            ):
                raise ValueError("automation_promotion_request_conflict")
            receipt = previous_request.receipt
            record = read_revalidation(
                db,
                organization_id=organization_id,
                record_id=receipt["revalidation_id"],
                settings=settings,
            )
            target = db.get(DomainSnapshot, previous_request.snapshot_id)
            if (
                record.receipt_sha256 != receipt["revalidation_receipt_sha256"]
                or target is None
                or target.content_sha256 != receipt["snapshot_sha256"]
                or content_digest(target.payload) != target.content_sha256
            ):
                raise ValueError("automation_promotion_history_invalid")
            return dict(
                applied_now=False,
                historical_replay=True,
                event_id=previous_request.id,
                revalidation_id=record.id,
                decision=receipt["draft_admission"],
                release_approved=False,
            )
        _no_human_work(db, organization_id, resource_id)
        # A fresh unpredictable revalidation request prevents a historical receipt
        # (including a previously blocked request) from becoming admission authority.
        record = revalidate_and_store(
            db,
            organization_id=organization_id,
            request_id=uuid4(),
            attempt_id=attempt_id,
            intent=intent,
            context=context,
            pdf_artifact_id=pdf_artifact_id,
            pdf_sha256=pdf_sha256,
            profile=profile,
            settings=settings,
            validator=validator,
            executor=executor,
            xpm_executor=xpm_executor,
            clock=clock,
        )
        now = clock()
        checked = datetime.fromisoformat(record.receipt["checked_at"])
        if now.utcoffset() is None or checked > now or (now - checked).total_seconds() > 60:
            raise ValueError("automation_promotion_revalidation_expired")
        _, candidate = _current_candidate(
            db,
            organization_id=organization_id,
            attempt_id=attempt_id,
            intent=intent,
            context=context,
            profile=profile,
            settings=settings,
            now=now,
        )
        _no_human_work(db, organization_id, resource_id)
        scope = dict(
            organization_id=organization_id,
            resource_id=resource_id,
            source_idml_sha256=context.scope.source_idml_sha256,
            journal_profile_id=profile.profile_id,
            xml_sha256=record.receipt["xml_sha256"],
            package_sha256=record.receipt["package_sha256"],
        )
        decision = draft_admission(
            offline=record.reports["offline"],
            formal=record.reports["formal"],
            xml_sha256=scope["xml_sha256"],
            package_sha256=scope["package_sha256"],
            validation_scope=scope,
        )
        if not decision["eligible"]:
            return dict(
                applied_now=False,
                historical_replay=False,
                event_id=None,
                revalidation_id=record.id,
                decision=decision,
                release_approved=False,
            )
        previous = current_canonical_snapshot(
            db, organization_id=organization_id, resource_id=resource_id
        )
        assert previous is not None  # Already checked under the resource lock.
        digest = content_digest(candidate)
        if db.scalar(
            select(DomainSnapshot.id).where(
                DomainSnapshot.resource_id == resource_id,
                DomainSnapshot.model_kind == "canonical",
                DomainSnapshot.content_sha256 == digest,
            )
        ):
            raise ValueError("automation_promotion_candidate_already_exists")
        last = _event(db, organization_id, resource_id)
        revision = (
            db.scalar(
                select(func.max(DomainSnapshot.revision)).where(
                    DomainSnapshot.organization_id == organization_id,
                    DomainSnapshot.resource_id == resource_id,
                    DomainSnapshot.model_kind == "canonical",
                )
            )
            or 0
        )
        target = DomainSnapshot(
            organization_id=organization_id,
            resource_id=resource_id,
            source_artifact_id=previous.source_artifact_id,
            parent_snapshot_id=previous.id,
            model_kind="canonical",
            schema_version=candidate.schema_version,
            revision=revision + 1,
            content_sha256=digest,
            payload=candidate.model_dump(mode="json", exclude_none=False),
        )
        db.add(target)
        db.flush()
        resource.version += 1
        receipt = dict(
            version="canonical-working-head-1.0",
            organization_id=organization_id,
            resource_id=resource_id,
            sequence=last.sequence + 1 if last else 1,
            snapshot_id=target.id,
            snapshot_sha256=digest,
            previous_snapshot_id=previous.id,
            previous_snapshot_sha256=previous.content_sha256,
            previous_event_id=last.id if last else None,
            previous_receipt_sha256=last.receipt_sha256 if last else None,
            request_id=str(request_id),
            request_sha256=request_sha,
            action="autocorrection-promotion",
            resource_version=resource.version,
            requires_revalidation=True,
            release_approved=False,
            revalidation_id=record.id,
            revalidation_receipt_sha256=record.receipt_sha256,
            attempt_id=attempt_id,
            draft_admission=decision,
        )
        event = CanonicalHeadEvent(
            organization_id=organization_id,
            resource_id=resource_id,
            sequence=receipt["sequence"],
            snapshot_id=target.id,
            previous_snapshot_id=previous.id,
            previous_event_id=last.id if last else None,
            request_id=str(request_id),
            request_sha256=request_sha,
            receipt=receipt,
            receipt_sha256=content_digest(receipt),
        )
        db.add(event)
        db.execute(
            update(ReviewItem)
            .where(
                ReviewItem.organization_id == organization_id,
                ReviewItem.resource_id == resource_id,
                ReviewItem.state == "open",
            )
            .values(base_snapshot_id=target.id, version=ReviewItem.version + 1, updated_at=utcnow())
        )
        db.flush()
        return dict(
            applied_now=True,
            historical_replay=False,
            event_id=event.id,
            revalidation_id=record.id,
            decision=decision,
            release_approved=False,
        )
