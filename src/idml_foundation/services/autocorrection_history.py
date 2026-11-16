"""Persist fresh revalidation atomically. Historical replay never authorizes promotion."""

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from idml_foundation.ai.autocorrection_contracts import (
    AutomationContext,
    AutomationIntent,
    intent_digest,
)
from idml_foundation.autocorrection_models import AutomationAttempt, AutomationRevalidation
from idml_foundation.database import ensure_write_transaction as _ensure_transaction
from idml_foundation.domain.common import content_digest
from idml_foundation.models import Artifact, Resource
from idml_foundation.pipeline.profile import JournalProfile
from idml_foundation.pipeline.validation import OfflineJatsValidator
from idml_foundation.services.artifacts import read_artifact_bytes, store_generated_artifact
from idml_foundation.services.autocorrection_executor import _verified_attempt
from idml_foundation.services.autocorrection_package import revalidate_candidate_package
from idml_foundation.services.package_validation import Executor
from idml_foundation.services.xpm_execution import XpmExecutor
from idml_foundation.settings import Settings


def read_revalidation(
    db: Session, *, organization_id: str, record_id: str, settings: Settings
) -> AutomationRevalidation:
    """Private tenant-scoped historical evidence, even if later revoked/discarded."""
    record = db.scalar(
        select(AutomationRevalidation)
        .where(
            AutomationRevalidation.id == record_id,
            AutomationRevalidation.organization_id == organization_id,
        )
        .execution_options(populate_existing=True)
    )
    if record is None:
        raise LookupError("automation_revalidation_not_found")
    attempt = db.scalar(
        select(AutomationAttempt)
        .where(
            AutomationAttempt.id == record.attempt_id,
            AutomationAttempt.resource_id == record.resource_id,
            AutomationAttempt.organization_id == organization_id,
        )
        .execution_options(populate_existing=True)
    )
    if attempt is None:
        raise ValueError("automation_revalidation_integrity_failure")
    _verified_attempt(attempt)
    receipt = record.receipt
    try:
        valid = (
            content_digest(receipt) == record.receipt_sha256
            and receipt["attempt_id"] == record.attempt_id
            and receipt["scope"] == attempt.receipt["scope"]
            and receipt["scope"]["resource_id"] == record.resource_id
            and receipt["scope"]["organization_id"] == organization_id
            and receipt["previous_receipt_sha256"] == attempt.receipt_sha256
            and receipt["request_id"] == record.request_id
            and receipt["request_sha256"] == record.request_sha256
            and receipt["reports_sha256"] == content_digest(record.reports)
            and receipt["manifest_sha256"] == content_digest(record.reports["manifest"])
            and receipt["formal_assessment_sha256"] == content_digest(record.reports["formal"])
            and receipt["offline_report_sha256"]
            == (content_digest(record.reports["offline"]) if record.reports["offline"] else None)
            and receipt["historical_evidence_only"] is True
            and receipt["promotion_authorized"] is False
            and receipt["release_approved"] is False
        )
    except (KeyError, TypeError):
        valid = False
    if not valid:
        raise ValueError("automation_revalidation_integrity_failure")
    for kind, artifact_id, media_type in (
        ("xml", record.xml_artifact_id, "application/xml"),
        ("package", record.package_artifact_id, "application/zip"),
    ):
        artifact = db.scalar(
            select(Artifact)
            .where(Artifact.id == artifact_id, Artifact.organization_id == organization_id)
            .execution_options(populate_existing=True)
        )
        digest = receipt[f"{kind}_sha256"]
        if (
            artifact is None
            or artifact.sha256 != digest
            or artifact.media_type != media_type
            or artifact.storage_key != f"{organization_id}/{digest[:2]}/{digest}"
            or receipt[f"{kind}_artifact_id"] != artifact_id
            or artifact.scanner_status not in {"generated", "clamav_clean"}
        ):
            raise ValueError("automation_revalidation_artifact_invalid")
        try:
            read_artifact_bytes(artifact, settings)
        except (OSError, ValueError):
            raise ValueError("automation_revalidation_artifact_invalid") from None
    return record


def revalidate_and_store(
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
) -> AutomationRevalidation:
    """Caller commits; same request replays history, new request revalidates afresh.

    No external report/bytes accepted from clients. Files written before a rollback
    may remain as immutable quota-accounted CAS orphans, never as approved records.
    """
    request_id = UUID(str(request_id))
    if str(context.scope.organization_id) != organization_id or intent.scope != context.scope:
        raise PermissionError("automation_scope_mismatch")
    request_sha = content_digest(
        {
            "attempt_id": attempt_id,
            "intent_sha256": intent_digest(intent),
            "scope": context.scope.model_dump(mode="json"),
            "pdf_artifact_id": pdf_artifact_id,
            "pdf_sha256": pdf_sha256,
            "profile_sha256": content_digest(profile),
        }
    )
    _ensure_transaction(db)

    def previous() -> AutomationRevalidation | None:
        row = db.scalar(
            select(AutomationRevalidation)
            .where(
                AutomationRevalidation.organization_id == organization_id,
                AutomationRevalidation.request_id == str(request_id),
            )
            .execution_options(populate_existing=True)
        )
        if row is None:
            return None
        if row.request_sha256 != request_sha:
            raise ValueError("automation_revalidation_request_conflict")
        return read_revalidation(
            db, organization_id=organization_id, record_id=row.id, settings=settings
        )

    try:
        with db.begin_nested():
            resource = db.scalar(
                select(Resource)
                .where(
                    Resource.id == str(context.scope.resource_id),
                    Resource.organization_id == organization_id,
                )
                .with_for_update()
            )
            if resource is None:
                raise LookupError("automation_resource_not_found")
            existing = previous()
            if existing is not None:
                return existing
            result = revalidate_candidate_package(
                db,
                organization_id=organization_id,
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
            xml_artifact = store_generated_artifact(
                db,
                organization_id=organization_id,
                settings=settings,
                original_name=f"evaluation-{attempt_id}.xml",
                data=result.xml,
                media_type="application/xml",
            )
            package_artifact = store_generated_artifact(
                db,
                organization_id=organization_id,
                settings=settings,
                original_name=f"evaluation-{attempt_id}.zip",
                data=result.package.archive,
                media_type="application/zip",
            )
            reports = {
                "offline": result.offline.model_dump(mode="json") if result.offline else None,
                "formal": result.formal,
                "manifest": result.package.manifest.model_dump(mode="json"),
            }
            receipt = result.receipt | {
                "version": "autocorrection-revalidation-history-1.0",
                "request_id": str(request_id),
                "request_sha256": request_sha,
                "xml_artifact_id": xml_artifact.id,
                "package_artifact_id": package_artifact.id,
                "reports_sha256": content_digest(reports),
                "historical_evidence_only": True,
            }
            record = AutomationRevalidation(
                organization_id=organization_id,
                resource_id=resource.id,
                attempt_id=attempt_id,
                request_id=str(request_id),
                request_sha256=request_sha,
                xml_artifact_id=xml_artifact.id,
                package_artifact_id=package_artifact.id,
                receipt=receipt,
                receipt_sha256=content_digest(receipt),
                reports=reports,
            )
            db.add(record)
            db.flush()
            return read_revalidation(
                db, organization_id=organization_id, record_id=record.id, settings=settings
            )
    except IntegrityError:
        existing = previous()
        if existing is None:
            raise
        return existing
