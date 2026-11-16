import copy
import hashlib
import json
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update

from idml_foundation.autocorrection_models import (
    AutomationAttempt,
    AutomationDiscard,
    AutomationGrantRecord,
    AutomationGrantRevocation,
)
from idml_foundation.domain.canonical import CanonicalArticle
from idml_foundation.models import (
    Artifact,
    DomainSnapshot,
    Resource,
    ReviewDecision,
    ReviewItem,
    User,
)
from idml_foundation.services.autocorrection_executor import (
    discard_candidate,
    register_extraction_grant,
    revoke_extraction_grant,
    stage_autocorrection,
)
from idml_foundation.services.snapshots import store_snapshot
from tests.autocorrection_helpers import persisted_data, stage_kwargs


@pytest.fixture
def data(db, settings):
    return persisted_data(db, settings)


def stage(db, data, **overrides):
    return stage_autocorrection(db, **(stage_kwargs(data) | overrides))


@pytest.mark.parametrize("index", [0, 1, 2, None])
def test_staging_changes_only_closed_paths_without_changing_head(db, data, index):
    before = copy.deepcopy(data["snapshot"].payload)
    if index is not None:
        data["intent"] = data["intent"].model_copy(
            update={"operations": (data["intent"].operations[index],)}
        )
    attempt = stage(db, data)
    assert attempt.receipt["state"] == "staged"
    assert not attempt.receipt["release_approved"] and attempt.receipt["requires_revalidation"]
    assert not attempt.receipt["active_snapshot_changed"]
    assert attempt.receipt["xml_sha256"] == hashlib.sha256(attempt.xml_content.encode()).hexdigest()
    assert attempt.validation["report"]["xml_sha256"] == attempt.receipt["xml_sha256"]
    restored = copy.deepcopy(attempt.candidate)
    for operation in attempt.receipt["operations"]:
        left, right = before, restored
        parts = operation["path"].split("/")[1:]
        for part in parts[:-1]:
            left = left[int(part)] if isinstance(left, list) else left[part]
            right = right[int(part)] if isinstance(right, list) else right[part]
        right[parts[-1]] = left[parts[-1]]
    assert restored == before
    db.commit()
    db.expire_all()
    assert db.get(DomainSnapshot, data["snapshot"].id).payload == before
    assert db.scalar(select(func.count()).select_from(DomainSnapshot)) == 1
    assert "Example University" not in json.dumps(attempt.receipt)
    assert "Brazil" not in json.dumps(attempt.receipt)


def test_idempotency_ignores_model_id_and_order_and_does_not_reexecute(db, data, monkeypatch):
    attempt = stage(db, data)
    db.commit()
    monkeypatch.setattr(
        data["validator"], "validate", lambda *a, **k: pytest.fail("must not rebuild")
    )
    intent = data["intent"].model_copy(
        update={"proposal_id": uuid4(), "operations": tuple(reversed(data["intent"].operations))}
    )
    assert stage(db, data, intent=intent).id == attempt.id
    assert db.scalar(select(func.count()).select_from(AutomationAttempt)) == 1


@pytest.mark.parametrize("variant", ["revoked", "missing", "ambiguous", "expired", "grant_hash"])
def test_grants_are_reloaded_and_all_or_nothing(db, data, variant):
    grant = data["grants"][-1]
    org = str(grant.scope.organization_id)
    if variant == "revoked":
        revoke_extraction_grant(
            db,
            organization_id=org,
            authorization_id=str(grant.authorization_id),
            decision_sha256="a" * 64,
        )
    elif variant == "ambiguous":
        register_extraction_grant(
            db, organization_id=org, grant=grant.model_copy(update={"authorization_id": uuid4()})
        )
    elif variant == "missing":
        data["intent"] = data["intent"].model_copy(
            update={
                "operations": (
                    data["intent"].operations[-1].model_copy(update={"evidence_id": "not-granted"}),
                )
            }
        )
    elif variant == "expired":
        data["now"] = grant.expires_at
    else:
        db.execute(
            update(AutomationGrantRecord)
            .where(AutomationGrantRecord.id == str(grant.authorization_id))
            .values(payload_sha256="f" * 64)
        )
    attempt = stage(db, data)
    assert attempt.receipt["state"] == "refused"
    assert not attempt.receipt["operations"]
    assert attempt.candidate is None and attempt.xml_content is None and attempt.validation is None


@pytest.mark.parametrize("variant", ["bytes", "missing", "scanner", "storage_key", "cross_tenant"])
def test_artifact_tampering_refused(db, data, variant):
    artifact = db.scalar(
        select(Artifact).where(Artifact.sha256 == data["context"].scope.source_idml_sha256)
    )
    path = data["settings"].artifact_root / artifact.storage_key
    if variant == "bytes":
        path.write_bytes(b"x" * artifact.size_bytes)
    elif variant == "missing":
        path.unlink()
    elif variant == "scanner":
        artifact.scanner_status = "policy_only"
    elif variant == "storage_key":
        artifact.storage_key = "other/" + artifact.sha256
    else:
        artifact.organization_id = str(uuid4())
    db.flush()
    attempt = stage(db, data)
    assert attempt.receipt["state"] == "refused" and attempt.candidate is None


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/front",
        "/front/affiliations/0/country_code",
        "/body/0/blocks/1",
        "/front/affiliations/0/original_text/value",
    ],
)
def test_current_human_review_blocks_entire_batch(db, data, path):
    scope = data["context"].scope
    db.add(
        ReviewItem(
            organization_id=str(scope.organization_id),
            resource_id=str(scope.resource_id),
            base_snapshot_id=str(scope.snapshot_id),
            category="editorial",
            rule_code="human",
            field_path=path,
            message="Private review",
            state="open",
        )
    )
    db.flush()
    attempt = stage(db, data)
    assert attempt.receipt["reason"] == "human_path_protected"
    assert attempt.candidate is None


@pytest.mark.parametrize("variant", ["tenant", "version", "snapshot", "snapshot_bytes"])
def test_stale_and_cross_tenant_requests_rejected_before_staging(db, data, variant):
    kwargs = {}
    if variant == "tenant":
        kwargs["organization_id"] = str(uuid4())
    elif variant == "version":
        resource = db.get(Resource, str(data["context"].scope.resource_id))
        resource.version += 1
    elif variant == "snapshot":
        snapshot = data["snapshot"]
        payload = copy.deepcopy(snapshot.payload)
        payload["front"]["titles"][0]["text"]["value"] = "New current draft"
        store_snapshot(
            db,
            organization_id=snapshot.organization_id,
            resource_id=snapshot.resource_id,
            document=CanonicalArticle.model_validate(payload),
            revision=2,
            source_artifact_id=snapshot.source_artifact_id,
            parent_snapshot_id=snapshot.id,
        )
    else:
        db.execute(
            update(DomainSnapshot)
            .where(DomainSnapshot.id == data["snapshot"].id)
            .values(content_sha256="f" * 64)
        )
    db.flush()
    with pytest.raises((PermissionError, ValueError)):
        stage(db, data, **kwargs)
    assert db.scalar(select(func.count()).select_from(AutomationAttempt)) == 0


@pytest.mark.parametrize("failure", ["exception", "wrong_hash", "invalid_xml"])
def test_offline_validation_cannot_promote_any_candidate(db, data, monkeypatch, failure):
    original = data["validator"].validate

    def fail(xml, **kwargs):
        if failure == "exception":
            raise RuntimeError("SECRET PRIVATE XML")
        report = original(xml if failure == "wrong_hash" else b"<broken", **kwargs)
        return report.model_copy(
            update={
                "xml_sha256": "f" * 64
                if failure == "wrong_hash"
                else hashlib.sha256(xml).hexdigest()
            }
        )

    monkeypatch.setattr(data["validator"], "validate", fail)
    attempt = stage(db, data)
    assert attempt.receipt["state"] == "staged" and attempt.receipt["requires_revalidation"]
    assert not attempt.receipt["release_approved"]
    assert "SECRET" not in json.dumps(attempt.validation)
    if failure != "invalid_xml":
        assert attempt.validation["state"] == "unavailable"
    else:
        assert not attempt.validation["report"]["valid"]


def test_builder_crash_rolls_back_and_retry_can_succeed(db, data, monkeypatch):
    from idml_foundation.services import autocorrection_executor as executor

    original = executor.JatsBuilder.build

    def crash(*args, **kwargs):
        raise RuntimeError("simulated interruption")

    monkeypatch.setattr(executor.JatsBuilder, "build", crash)
    with pytest.raises(RuntimeError, match="simulated interruption"):
        stage(db, data)
    assert db.scalar(select(func.count()).select_from(AutomationAttempt)) == 0
    monkeypatch.setattr(executor.JatsBuilder, "build", original)
    assert stage(db, data).receipt["state"] == "staged"


def test_caller_rollback_does_not_leave_staged_copy(db, data):
    stage(db, data)
    db.rollback()
    assert db.scalar(select(func.count()).select_from(AutomationAttempt)) == 0
    assert stage(db, data).receipt["state"] == "staged"


def test_discard_is_append_only_idempotent_and_never_reactivates(db, data):
    attempt = stage(db, data)
    db.commit()
    kwargs = dict(organization_id=attempt.organization_id, attempt_id=attempt.id, now=data["now"])
    discard = discard_candidate(db, **kwargs)
    db.commit()
    assert discard_candidate(db, **kwargs).receipt_sha256 == discard.receipt_sha256
    assert stage(db, data).id == attempt.id  # historical attempt, no new execution
    assert db.scalar(select(func.count()).select_from(AutomationDiscard)) == 1
    assert db.get(AutomationAttempt, attempt.id).candidate is not None
    assert discard.receipt["previous_receipt_sha256"] == attempt.receipt_sha256
    with pytest.raises(LookupError):
        discard_candidate(db, **(kwargs | {"organization_id": str(uuid4())}))


@pytest.mark.parametrize(
    "model",
    [AutomationGrantRecord, AutomationGrantRevocation, AutomationAttempt, AutomationDiscard],
)
@pytest.mark.parametrize("action", ["update", "delete"])
def test_orm_history_cannot_be_rewritten(db, data, model, action):
    attempt = stage(db, data)
    discard_candidate(
        db, organization_id=attempt.organization_id, attempt_id=attempt.id, now=data["now"]
    )
    revoke_extraction_grant(
        db,
        organization_id=attempt.organization_id,
        authorization_id=str(data["grants"][0].authorization_id),
        decision_sha256="c" * 64,
    )
    db.commit()
    row = db.scalars(select(model)).first()
    if action == "update":
        row.created_at += timedelta(seconds=1)
    else:
        db.delete(row)
    with pytest.raises(ValueError, match="autocorrection_history_is_append_only"):
        db.flush()
    db.rollback()


def test_grant_revocation_is_idempotent_and_tenant_scoped(db, data):
    kwargs = dict(
        organization_id=str(data["context"].scope.organization_id),
        authorization_id=str(data["grants"][0].authorization_id),
        decision_sha256="c" * 64,
    )
    first = revoke_extraction_grant(db, **kwargs)
    assert revoke_extraction_grant(db, **kwargs).grant_id == first.grant_id
    with pytest.raises(LookupError):
        revoke_extraction_grant(db, **(kwargs | {"organization_id": str(uuid4())}))


def test_persisted_retry_content_is_verified(db, data):
    attempt = stage(db, data)
    db.commit()
    db.execute(
        update(AutomationAttempt)
        .where(AutomationAttempt.id == attempt.id)
        .values(xml_content="<tampered/>")
    )
    with pytest.raises(ValueError, match="attempt_integrity_failure"):
        stage(db, data)


@pytest.mark.parametrize(
    "override,reason",
    [
        ({"enabled": False}, "automation_disabled"),
        ({"cycle": 3}, "cycle_limit"),
        ({"consumed_tokens": 50000}, "token_limit"),
    ],
)
def test_policy_is_rechecked_by_executor(db, data, override, reason):
    attempt = stage(db, data, context=data["context"].model_copy(update=override))
    assert attempt.receipt["reason"] == reason and attempt.candidate is None


def test_historical_decision_path_remains_protected(db, data):
    scope = data["context"].scope
    actor = User(email="synthetic@example.test", password_hash="unused-test-hash")
    db.add(actor)
    item = ReviewItem(
        organization_id=str(scope.organization_id),
        resource_id=str(scope.resource_id),
        base_snapshot_id=str(scope.snapshot_id),
        category="editorial",
        rule_code="historical",
        field_path="/back",
        message="Historical human decision",
        state="resolved",
    )
    db.add(item)
    db.flush()
    db.add(
        ReviewDecision(
            organization_id=str(scope.organization_id),
            review_item_id=item.id,
            actor_user_id=actor.id,
            base_snapshot_id=str(scope.snapshot_id),
            action="apply_patch",
            patch=[{"op": "replace", "path": "/front/affiliations/0/original_text", "value": None}],
            justification="Human kept the field empty",
            expected_version=1,
            patch_sha256="a" * 64,
        )
    )
    db.flush()
    assert stage(db, data).receipt["reason"] == "human_path_protected"


@pytest.mark.parametrize("change", ["review", "revision", "revoke"])
def test_state_changes_during_build_roll_back_entire_attempt(db, data, monkeypatch, change):
    original = data["validator"].validate
    scope = data["context"].scope

    def changed(xml, **kwargs):
        if change == "review":
            db.add(
                ReviewItem(
                    organization_id=str(scope.organization_id),
                    resource_id=str(scope.resource_id),
                    base_snapshot_id=str(scope.snapshot_id),
                    category="editorial",
                    rule_code="new-review",
                    field_path="/front",
                    message="Human intervention",
                    state="open",
                )
            )
        elif change == "revision":
            db.get(Resource, str(scope.resource_id)).version += 1
        else:
            revoke_extraction_grant(
                db,
                organization_id=str(scope.organization_id),
                authorization_id=str(data["grants"][0].authorization_id),
                decision_sha256="e" * 64,
            )
        db.flush()
        return original(xml, **kwargs)

    monkeypatch.setattr(data["validator"], "validate", changed)
    with pytest.raises(ValueError, match="automation_concurrent_state_change"):
        stage(db, data)
    assert db.scalar(select(func.count()).select_from(AutomationAttempt)) == 0


@pytest.mark.parametrize("change", ["schema", "scope"])
def test_invalid_stored_grant_is_not_trusted_even_with_matching_record_hash(db, data, change):
    from idml_foundation.domain.common import content_digest

    record = db.get(AutomationGrantRecord, str(data["grants"][0].authorization_id))
    payload = copy.deepcopy(record.payload)
    if change == "schema":
        payload["extra_model_authority"] = True
    else:
        payload["scope"]["resource_id"] = str(uuid4())
    db.execute(
        update(AutomationGrantRecord)
        .where(AutomationGrantRecord.id == record.id)
        .values(
            payload=payload,
            payload_sha256=content_digest(payload),
        )
    )
    attempt = stage(db, data)
    assert attempt.receipt["reason"] == (
        "invalid_stored_source_grant" if change == "schema" else "grant_scope_mismatch"
    )


def test_refused_attempt_cannot_be_discarded_as_a_candidate(db, data):
    attempt = stage(db, data, context=data["context"].model_copy(update={"enabled": False}))
    with pytest.raises(ValueError, match="automation_attempt_has_no_candidate"):
        discard_candidate(
            db, organization_id=attempt.organization_id, attempt_id=attempt.id, now=data["now"]
        )
