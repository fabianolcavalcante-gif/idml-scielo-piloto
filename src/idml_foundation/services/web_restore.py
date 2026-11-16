"""Operator undo/recovery for the last admitted automatic correction of an article."""

from pathlib import Path
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from idml_foundation.models import Artifact, CanonicalHeadEvent, Job
from idml_foundation.pipeline.profile import load_profile
from idml_foundation.pipeline.validation import OfflineJatsValidator
from idml_foundation.schemas import EditRestorePayload
from idml_foundation.services.autocorrection_history import read_revalidation
from idml_foundation.services.canonical_heads import _event, _verified, lock_resource
from idml_foundation.services.restored_package_validation import restore_and_revalidate_package
from idml_foundation.settings import Settings

Action = Literal["undo", "recover"]


def restore_choice(db: Session, org: str, article: str) -> tuple[Action, CanonicalHeadEvent] | None:
    current = _event(db, org, article)
    if current is None or current.receipt["action"] not in {"restore", "autocorrection-promotion"}:
        return None
    # A fresh snapshot or human change ends the preceding automatic edit sequence.
    origin = db.scalar(
        select(CanonicalHeadEvent)
        .where(
            CanonicalHeadEvent.organization_id == org,
            CanonicalHeadEvent.resource_id == article,
            CanonicalHeadEvent.receipt["action"].as_string() != "restore",
        )
        .order_by(CanonicalHeadEvent.sequence.desc())
        .limit(1)
    )
    if origin is None:
        return None
    origin = _verified(origin)
    if (
        origin.receipt["action"] != "autocorrection-promotion"
        or not origin.receipt["draft_admission"]["eligible"]
    ):
        return None
    if current.snapshot_id == origin.snapshot_id:
        return "undo", origin
    if current.snapshot_id == origin.previous_snapshot_id:
        return "recover", origin
    return None


class _ValidationUnavailable(Exception):
    pass


def restore_from_web(db: Session, job: Job, settings: Settings) -> dict[str, object]:
    request = EditRestorePayload.model_validate(job.payload)
    rid, org = str(request.resource_id), job.organization_id
    article = lock_resource(db, org, rid)
    current = _event(db, org, rid)
    choice = restore_choice(db, org, rid)
    if (
        not choice
        or not current
        or article.version != request.review_version
        or current.snapshot_id != str(request.canonical_snapshot_id)
        or choice[0] != request.action
    ):
        return dict(state="refused", reason="revision_changed", active_snapshot_changed=False)
    action, origin = choice
    target = origin.previous_snapshot_id if action == "undo" else origin.snapshot_id
    evidence = read_revalidation(
        db, organization_id=org, record_id=origin.receipt["revalidation_id"], settings=settings
    )
    if (
        not target
        or evidence.resource_id != rid
        or evidence.receipt_sha256 != origin.receipt["revalidation_receipt_sha256"]
    ):
        raise ValueError("restore_promotion_integrity_failure")
    pdf_hash = evidence.receipt["pdf_sha256"]
    pdf = db.scalar(
        select(Artifact.id).where(
            Artifact.organization_id == org,
            Artifact.sha256 == pdf_hash,
            Artifact.id == evidence.receipt["pdf_artifact_id"],
            Artifact.media_type == "application/pdf",
            Artifact.scanner_status == "clamav_clean",
        )
    )
    if pdf is None:
        raise ValueError("restore_pdf_missing")
    try:
        with db.begin_nested():
            record = restore_and_revalidate_package(
                db,
                organization_id=org,
                resource_id=rid,
                target_snapshot_id=target,
                expected_snapshot_id=current.snapshot_id,
                expected_resource_version=request.review_version,
                request_id=UUID(job.id),
                pdf_artifact_id=pdf,
                pdf_sha256=pdf_hash,
                profile=load_profile(settings.journal_profile_path),
                settings=settings,
                validator=OfflineJatsValidator(
                    Path(__file__).resolve().parents[3] / "vendor/jats/1.3"
                ),
            )
            formal = record.reports["formal"]
            runs = formal.get("external_runs", [])
            if {r["name"] for r in runs if r["status"] == "completed"} != {
                "packtools",
                "spsvalidator",
            } or (formal.get("xpm") or {}).get("status") != "completed":
                raise _ValidationUnavailable
            return dict(
                state=record.receipt["state"],
                active_snapshot_changed=True,
                restore_id=record.id,
                snapshot_id=target,
                provider_calls=0,
                release_approved=False,
            )
    except _ValidationUnavailable:
        return dict(
            state="refused",
            reason="restore_validation_unavailable",
            active_snapshot_changed=False,
            provider_calls=0,
            release_approved=False,
        )
