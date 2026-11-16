"""Transactional promotion with synthetic executors, not real-article approval."""

from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from idml_foundation.autocorrection_models import AutomationRevalidation
from idml_foundation.models import CanonicalHeadEvent, DomainSnapshot, Resource, ReviewItem
from idml_foundation.release.validation_engine import UnifiedIssue
from idml_foundation.services.autocorrection_executor import (
    discard_candidate,
    revoke_extraction_grant,
)
from idml_foundation.services.autocorrection_promotion import promote_revalidated_candidate
from idml_foundation.services.canonical_heads import (
    current_canonical_snapshot,
    restore_working_head,
)
from tests.test_autocorrection_package import PassingOffline
from tests.test_autocorrection_package import data as data
from tests.test_package_formal_validation import completed
from tests.test_xpm_execution import execution


def arguments(data):
    return dict(
        organization_id=str(data["context"].scope.organization_id),
        attempt_id=data["attempt"].id,
        intent=data["intent"],
        context=data["context"],
        pdf_artifact_id=data["pdf"].id,
        pdf_sha256=data["pdf"].sha256,
        profile=data["profile"],
        settings=data["settings"].model_copy(
            update={
                "validator_registry_path": Path(__file__).parents[1]
                / "config/validator-registry-vh1-composed.json"
            }
        ),
        validator=PassingOffline(),
        executor=completed,
        xpm_executor=execution,
        clock=lambda: data["now"],
    )


def promote(db, data, request_id=None, **overrides):
    return promote_revalidated_candidate(
        db, request_id=request_id or uuid4(), **(arguments(data) | overrides)
    )


def head(db, data):
    return current_canonical_snapshot(
        db,
        organization_id=str(data["context"].scope.organization_id),
        resource_id=str(data["context"].scope.resource_id),
    )


def test_promotes_fresh_working_draft_and_replay_never_moves_restored_head(db, data):
    request = uuid4()
    result = promote(db, data, request)
    assert result["applied_now"] and not result["release_approved"]
    db.commit()
    target = head(db, data)
    assert target.id != data["snapshot"].id and target.payload == data["attempt"].candidate
    event = db.get(CanonicalHeadEvent, result["event_id"])
    assert event.receipt["action"] == "autocorrection-promotion"
    assert event.receipt["requires_revalidation"] and not event.receipt["release_approved"]
    record = db.get(AutomationRevalidation, result["revalidation_id"])
    assert record.receipt["historical_evidence_only"] and not record.receipt["promotion_authorized"]
    resource = db.get(Resource, str(data["context"].scope.resource_id))
    restore_working_head(
        db,
        organization_id=resource.organization_id,
        resource_id=resource.id,
        request_id=uuid4(),
        target_snapshot_id=data["snapshot"].id,
        expected_snapshot_id=target.id,
        expected_resource_version=resource.version,
    )
    db.commit()
    calls = []
    replay = promote(db, data, request, executor=lambda *a: calls.append(a))
    assert replay["historical_replay"] and not replay["applied_now"] and not calls
    assert head(db, data).id == data["snapshot"].id
    assert db.scalar(select(func.count()).select_from(AutomationRevalidation)) == 1


def test_outer_rollback_removes_promotion_and_revalidation_and_allows_retry(db, data):
    request = uuid4()
    first = promote(db, data, request)
    db.rollback()
    assert head(db, data).id == data["snapshot"].id
    assert db.scalar(select(func.count()).select_from(AutomationRevalidation)) == 0
    assert db.scalar(select(func.count()).select_from(DomainSnapshot)) == 1
    second = promote(db, data, request)
    assert second["applied_now"] and second["event_id"] != first["event_id"]


@pytest.mark.parametrize(
    "change", ["missing_modern", "missing_xpm", "xpm_error", "queries", "offline", "modern_error"]
)
def test_validation_failure_keeps_head_and_saves_private_evidence(db, data, change):
    overrides = {
        "missing_modern": dict(executor=None),
        "missing_xpm": dict(xpm_executor=None),
        "xpm_error": dict(xpm_executor=lambda p, s: execution(p, s, errors=1)),
        "queries": dict(xpm_executor=lambda p, s: execution(p, s, queries=False)),
        "offline": dict(validator=data["validator"]),
        "modern_error": dict(
            executor=lambda p, s: completed(p, s).model_copy(
                update={
                    "issues": (
                        UnifiedIssue(
                            validator=s.name,
                            category="deterministic",
                            severity="error",
                            code="real-error",
                            message="private",
                        ),
                    )
                }
            )
        ),
    }[change]
    result = promote(db, data, **overrides)
    db.commit()
    assert not result["applied_now"] and not result["decision"]["eligible"]
    assert head(db, data).id == data["snapshot"].id
    assert db.get(AutomationRevalidation, result["revalidation_id"])


def test_warnings_remain_pending_without_publication_or_automatic_acceptance(db, data):
    def warned(p, s):
        return completed(p, s).model_copy(
            update={
                "issues": (
                    UnifiedIssue(
                        validator=s.name,
                        category="semantic",
                        severity="warning",
                        code="review",
                        message="review",
                    ),
                )
            }
        )

    result = promote(
        db, data, executor=warned, xpm_executor=lambda p, s: execution(p, s, warnings=1)
    )
    assert result["applied_now"] and len(result["decision"]["pending_review"]) == 3
    assert not result["decision"]["warnings_accepted"]
    record = db.get(AutomationRevalidation, result["revalidation_id"])
    assert record.reports["formal"]["state"] == "blocked"
    assert not record.reports["formal"]["ready_for_scielo"]


def test_cross_tenant_request_and_request_reuse_with_different_pdf_rejected(db, data):
    with pytest.raises(PermissionError):
        promote(db, data, organization_id=str(uuid4()))
    request = uuid4()
    promote(db, data, request)
    with pytest.raises(ValueError, match="request_conflict"):
        promote(db, data, request, pdf_sha256="f" * 64)


@pytest.mark.parametrize("change", ["expired", "revoked", "discarded", "stale", "disabled"])
def test_source_authority_and_version_rechecked(db, data, change):
    extra = {}
    if change == "expired":
        extra["clock"] = lambda: data["now"] + timedelta(days=40)
    elif change == "disabled":
        extra["context"] = data["context"].model_copy(update={"enabled": False})
    elif change == "revoked":
        revoke_extraction_grant(
            db,
            organization_id=str(data["context"].scope.organization_id),
            authorization_id=str(data["grants"][0].authorization_id),
            decision_sha256="f" * 64,
        )
    elif change == "discarded":
        discard_candidate(
            db,
            organization_id=str(data["context"].scope.organization_id),
            attempt_id=data["attempt"].id,
            now=data["now"],
        )
    else:
        db.get(Resource, str(data["context"].scope.resource_id)).version += 1
    with pytest.raises((ValueError, RuntimeError)):
        promote(db, data, **extra)
    assert head(db, data).id == data["snapshot"].id


def test_human_claim_even_outside_candidate_paths_blocks_promotion(db, data):
    item = ReviewItem(
        organization_id=str(data["context"].scope.organization_id),
        resource_id=str(data["context"].scope.resource_id),
        base_snapshot_id=data["snapshot"].id,
        state="claimed",
        field_path="/front/title",
        category="semantic",
        rule_code="human",
        message="human",
    )
    db.add(item)
    db.flush()
    with pytest.raises(ValueError, match="human_work_protected"):
        promote(db, data)


def test_revocation_during_native_execution_rolls_back_transition(db, data):
    def execute(p, s):
        revoke_extraction_grant(
            db,
            organization_id=str(data["context"].scope.organization_id),
            authorization_id=str(data["grants"][0].authorization_id),
            decision_sha256="f" * 64,
        )
        return completed(p, s)

    with pytest.raises(ValueError):
        promote(db, data, executor=execute)
    assert head(db, data).id == data["snapshot"].id


def test_open_review_moves_to_new_draft_and_stale_ui_version_is_invalid(db, settings):
    from tests.autocorrection_helpers import persisted_data
    from tests.test_autocorrection_package import with_package_inputs

    data = persisted_data(db, settings)
    item = ReviewItem(
        organization_id=str(data["context"].scope.organization_id),
        resource_id=str(data["context"].scope.resource_id),
        base_snapshot_id=data["snapshot"].id,
        state="open",
        field_path="/front/title",
        category="semantic",
        rule_code="title",
        message="review title",
    )
    db.add(item)
    db.commit()
    data = with_package_inputs(db, data)
    version = item.version
    result = promote(db, data)
    assert result["applied_now"]
    db.refresh(item)
    assert item.base_snapshot_id == head(db, data).id and item.version == version + 1
    assert item.state == "open" and item.assigned_user_id is None


def test_second_distinct_request_cannot_promote_same_stale_attempt(db, data):
    promote(db, data)
    db.commit()
    with pytest.raises(ValueError, match="stale_snapshot_or_revision"):
        promote(db, data)
    assert db.scalar(select(func.count()).select_from(AutomationRevalidation)) == 1


def test_fresh_validation_is_required_after_a_blocked_attempt(db, data):
    request = uuid4()
    first = promote(db, data, request, executor=None)
    db.commit()
    assert not first["applied_now"]
    seen = []

    def fresh(p, s):
        seen.append(s.name)
        return completed(p, s)

    second = promote(db, data, request, executor=fresh)
    assert second["applied_now"] and second["revalidation_id"] != first["revalidation_id"]
    assert seen == ["packtools", "spsvalidator"]


def test_expiry_between_revalidation_and_head_transition_refuses_promotion(db, data):
    ticks = iter([data["now"], data["now"], data["now"] + timedelta(seconds=61)])
    with pytest.raises(ValueError, match="revalidation_expired"):
        promote(db, data, clock=lambda: next(ticks))
    assert head(db, data).id == data["snapshot"].id
    assert db.scalar(select(func.count()).select_from(AutomationRevalidation)) == 0
