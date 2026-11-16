"""Issue a revision-scoped decision from an authenticated operator's web job."""

from datetime import UTC, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from uuid import UUID, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from idml_foundation.ai.edit_cycle import MODEL
from idml_foundation.domain.canonical import CanonicalArticle
from idml_foundation.domain.common import content_digest
from idml_foundation.models import Artifact, Job, JobEvent, Membership, Organization, User, utcnow
from idml_foundation.pipeline.autocorrection_evidence import qualify_fields
from idml_foundation.pipeline.profile import load_profile
from idml_foundation.schemas import EditEvaluationPayload
from idml_foundation.services.artifacts import read_artifact_bytes
from idml_foundation.services.autocorrection_authorization import RevisionEditAuthorization
from idml_foundation.services.autocorrection_promotion import _no_human_work
from idml_foundation.services.canonical_heads import current_canonical_snapshot, lock_resource
from idml_foundation.services.web_edit_cycle import WebEditDecision, evaluate_revision
from idml_foundation.services.web_restore import restore_choice
from idml_foundation.settings import Settings


def _operator_active(db: Session, org: str, user: str) -> bool:
    return (
        db.scalar(
            select(Membership.id)
            .join(User, User.id == Membership.user_id)
            .join(Organization, Organization.id == Membership.organization_id)
            .where(
                Membership.organization_id == org,
                Membership.user_id == user,
                Membership.is_active.is_(True),
                Membership.role.in_(("operator", "org_admin")),
                User.is_active.is_(True),
                Organization.is_active.is_(True),
            )
        )
        is not None
    )


def _stop(reason: str, state: str = "refused") -> dict[str, Any]:
    return dict(
        state=state,
        reason=reason,
        provider_calls=0,
        active_snapshot_changed=False,
        release_approved=False,
    )


def authorize_revision(db: Session, job: Job, settings: Settings) -> dict[str, Any]:
    """The enqueue event supplies the actor. All document bindings come from stored inputs."""
    request = EditEvaluationPayload.model_validate(job.payload)
    org, rid = job.organization_id, str(request.resource_id)
    issuer = db.scalar(
        select(JobEvent).where(
            JobEvent.job_id == job.id,
            JobEvent.organization_id == org,
            JobEvent.sequence == 1,
            JobEvent.actor_type == "user",
            JobEvent.to_state == "queued",
        )
    )
    if job.kind != "autocorrection.authorize" or not issuer or not issuer.actor_id:
        return _stop("operator_authorization_required")
    actor = issuer.actor_id
    if not _operator_active(db, org, actor):
        return _stop("operator_authorization_required")
    if not settings.feature_web_edit_provider:
        return _stop("provider_window_closed")
    resource = lock_resource(db, org, rid)
    snap = current_canonical_snapshot(db, organization_id=org, resource_id=rid)
    if (
        not snap
        or snap.id != str(request.canonical_snapshot_id)
        or resource.version != request.review_version
    ):
        return _stop("revision_changed")
    choice = restore_choice(db, org, rid)
    if choice and choice[0] == "recover":
        return _stop("already_corrected_use_recovery")
    _no_human_work(db, org, rid)
    source = db.get(Artifact, snap.source_artifact_id) if snap.source_artifact_id else None
    if (
        not source
        or source.organization_id != org
        or source.scanner_status != "clamav_clean"
        or source.media_type != "application/vnd.adobe.indesign-idml-package"
        or content_digest(snap.payload) != snap.content_sha256
    ):
        return _stop("source_unverified")
    profile = load_profile(settings.journal_profile_path)
    article = CanonicalArticle.model_validate(snap.payload)
    if (
        article.journal_profile_id != "esa-aop-1.1.0"
        or profile.profile_id != article.journal_profile_id
    ):
        return _stop("operation_outside_web_scope")
    qualified = qualify_fields(
        article, idml=read_artifact_bytes(source, settings), profile=profile, settings=settings
    )
    if not qualified.catalog.bindings:
        return _stop("no_eligible_field", "abstained")
    if content_digest(qualified.article) != snap.content_sha256:
        return _stop("snapshot_requires_field_evidence_preparation")
    if (
        len(qualified.catalog.bindings) != 1
        or qualified.catalog.bindings[0].operation != "affiliation-original-literal"
    ):
        return _stop("operation_outside_web_scope", "abstained")
    binding = qualified.catalog.bindings[0]
    evidence = next(e for e in article.evidence if e.id == binding.evidence_id)
    if not evidence.content_sha256:
        return _stop("source_unverified")
    package = db.scalar(
        select(Job)
        .where(
            Job.organization_id == org,
            Job.kind == "scielo.package",
            Job.state == "succeeded",
            Job.payload["resource_id"].as_string() == rid,
            Job.payload["canonical_snapshot_id"].as_string() == snap.id,
            Job.payload["idml_artifact_id"].as_string() == source.id,
        )
        .order_by(Job.created_at.desc(), Job.id.desc())
        .limit(1)
    )
    if not package:
        return _stop("revision_package_required")
    pdf = db.get(Artifact, package.payload["pdf_artifact_id"])
    manifest = (package.result or {}).get("manifest", {})
    pdf_hashes = [f["sha256"] for f in manifest.get("files", []) if f["role"] == "pdf"]
    if (
        not pdf
        or pdf.organization_id != org
        or pdf.scanner_status != "clamav_clean"
        or pdf.media_type != "application/pdf"
        or pdf_hashes != [pdf.sha256]
    ):
        return _stop("restore_pdf_missing")
    authorization_id = uuid5(UUID(snap.id), f"web-affiliation:{org}:{rid}:{resource.version}")
    if (settings.artifact_root / ".web-edit-runs" / org / str(authorization_id)).exists():
        return _stop("decision_already_used")
    issued = (
        issuer.created_at.replace(tzinfo=UTC)
        if issuer.created_at.tzinfo is None
        else issuer.created_at
    )
    expires = issued + timedelta(hours=2)
    if not issued <= utcnow() < expires:
        return _stop("authorization_expired")
    if settings.enrichment_location not in {"vps", "local"}:
        return _stop("edit_decision_store_unavailable")
    parent = RevisionEditAuthorization(
        organization_id=UUID(org),
        resource_id=request.resource_id,
        snapshot_id=request.canonical_snapshot_id,
        authorization_id=authorization_id,
        review_version=request.review_version,
        canonical_sha256=snap.content_sha256,
        source_idml_sha256=source.sha256,
        catalog_sha256=content_digest(qualified.catalog),
        status="active",
        destination=settings.enrichment_location,
        collected_at=issued,
        issued_at=issued,
        expires_at=expires,
        decision_sha256=content_digest(
            dict(
                actor=actor,
                job=job.id,
                package=package.id,
                literal=evidence.content_sha256,
                pdf=pdf.sha256,
                scope=request.model_dump(mode="json"),
            )
        ),
    )
    permit = WebEditDecision(
        purpose="review-and-promote-affiliation-v1",
        model=MODEL,
        scope=request,
        organization_id=UUID(org),
        authorization_id=authorization_id,
        allowed_literal_sha256=evidence.content_sha256,
        pdf_artifact_id=UUID(pdf.id),
        pdf_sha256=pdf.sha256,
    )
    # The existing extractor verifies its parent again before each call and promotion.
    # Use a private directory for this job so the shared administrative store stays read-only.
    with TemporaryDirectory(prefix="idml-revision-") as folder:
        root = Path(folder)
        parent_path = root / "autocorrection-authorizations" / f"{authorization_id}.json"
        permit_path = root / "web-edit-decisions" / org / rid / snap.id / f"{resource.version}.json"
        for path, document in ((parent_path, parent), (permit_path, permit)):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(document.model_dump_json(), encoding="utf8")
        result = evaluate_revision(
            db,
            job,
            settings.model_copy(update={"automation_authorization_root": root}),
            operator_active=lambda: _operator_active(db, org, actor),
        )
    return dict(
        result,
        web_authorization=dict(
            actor_id=actor,
            authorization_id=str(authorization_id),
            decision_sha256=parent.decision_sha256,
            package_job_id=package.id,
            expires_at=expires.isoformat(),
        ),
    )
