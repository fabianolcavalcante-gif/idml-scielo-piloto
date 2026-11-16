"""Deterministic edit preflight. Never dispatches a provider or advances the draft."""

from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from idml_foundation.ai.autocorrection_contracts import (
    POLICY_VERSION,
    AutomationContext,
    AutomationScope,
)
from idml_foundation.ai.autocorrection_policy import policy_digest
from idml_foundation.domain.common import content_digest
from idml_foundation.models import Artifact, Job, utcnow
from idml_foundation.pipeline.profile import load_profile
from idml_foundation.pipeline.validation import OfflineJatsValidator
from idml_foundation.schemas import EditPreflightPayload
from idml_foundation.services.autocorrection_authorization import (
    NoEligibleFields,
    load_batch_authorization,
    provision_field_grants,
)
from idml_foundation.services.autocorrection_executor import stage_autocorrection
from idml_foundation.services.autocorrection_sources import SourceResolutionError
from idml_foundation.services.canonical_heads import current_canonical_snapshot, lock_resource
from idml_foundation.settings import Settings


def run_edit_preflight(
    db: Session, job: Job, settings: Settings, *, request: EditPreflightPayload | None = None
) -> dict[str, Any]:
    request = request or EditPreflightPayload.model_validate(job.payload)
    resource_id = str(request.resource_id)
    try:
        resource = lock_resource(db, job.organization_id, resource_id)
    except LookupError:
        raise ValueError("automation_resource_not_found") from None
    snapshot = current_canonical_snapshot(
        db, organization_id=job.organization_id, resource_id=resource_id
    )
    if (
        snapshot is None
        or snapshot.id != str(request.canonical_snapshot_id)
        or resource.version != request.review_version
    ):
        raise ValueError("automation_stale_snapshot_or_revision")
    source = db.get(Artifact, snapshot.source_artifact_id)
    if source is None or source.organization_id != job.organization_id:
        raise ValueError("snapshot_source_mismatch")
    scope = AutomationScope.model_validate(
        dict(
            organization_id=job.organization_id,
            resource_id=resource_id,
            snapshot_id=snapshot.id,
            snapshot_sha256=snapshot.content_sha256,
            source_idml_sha256=source.sha256,
            article_id=snapshot.payload["article_id"],
            profile_id=snapshot.payload["journal_profile_id"],
            review_version=resource.version,
        )
    )
    summary = dict(
        version="edit-preflight-1.0",
        scope=scope.model_dump(mode="json"),
        provider_calls=0,
        active_snapshot_changed=False,
        release_approved=False,
    )
    profile = load_profile(settings.journal_profile_path)
    now = utcnow()
    try:
        batch = provision_field_grants(
            db,
            organization_id=job.organization_id,
            scope=scope,
            authorization_id=request.authorization_id,
            profile=profile,
            settings=settings,
            now=now,
            require_revision_decision=True,
        )
    except NoEligibleFields as exc:
        return dict(
            **summary,
            state="abstained",
            reason="no_eligible_field",
            catalog_sha256=exc.catalog_sha256,
        )
    except SourceResolutionError as exc:
        return dict(**summary, state="refused", reason=str(exc))
    context = AutomationContext(
        scope=scope,
        enabled=True,
        policy_version=POLICY_VERSION,
        policy_sha256=policy_digest(),
        cycle=1,
        started_at=now,
        consumed_tokens=0,
        consumed_cost_usd=0,
        other_active_executions=0,
        findings=batch.findings,
    )
    attempt = stage_autocorrection(
        db,
        organization_id=job.organization_id,
        intent=batch.intent,
        context=context,
        profile=profile,
        settings=settings,
        validator=OfflineJatsValidator(
            Path(__file__).resolve().parents[3] / "vendor" / "jats" / "1.3"
        ),
        now=utcnow(),
    )
    # The decision is outside the database lock; check it again at completion,
    # including retries that reused an existing attempt.
    assert request.authorization_id is not None
    parent = load_batch_authorization(
        settings,
        authorization_id=request.authorization_id,
        scope=scope,
        catalog_sha256=batch.catalog_sha256,
        now=utcnow(),
    )
    if content_digest(parent) != batch.parent_sha256:
        raise ValueError("parent_authorization_changed")
    report = (attempt.validation or {}).get("report") or {}
    return dict(
        **summary,
        state=attempt.receipt["state"],
        reason=attempt.receipt["reason"],
        attempt_id=attempt.id,
        catalog_sha256=batch.catalog_sha256,
        xml_sha256=attempt.receipt["xml_sha256"],
        offline_valid=report.get("valid"),
        operation_count=len(attempt.receipt["operations"]),
    )
