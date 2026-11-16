import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from idml_foundation.models import Membership, Resource
from idml_foundation.rbac import Role
from idml_foundation.schemas import JobCreate
from idml_foundation.services import article_source_access as access
from idml_foundation.services import web_restore, web_source_policy
from idml_foundation.services.canonical_heads import restore_working_head
from tests.autocorrection_helpers import persisted_data
from tests.test_article_source_access import seed
from tests.test_autocorrection_package import with_package_inputs
from tests.test_autocorrection_promotion import head, promote
from tests.test_phase5_review_ui import _headers, _token, _user


def test_owner_permit_and_operator_scope(
    client, db, session_factory, settings, tmp_path, monkeypatch
):
    org, admin, _, request, scope = seed(db, session_factory, settings)
    root = tmp_path / "permissions"
    root.mkdir()
    monkeypatch.setattr(web_source_policy, "ROOT", root)
    row = access.decide(db, **request)
    now = datetime.now(UTC)
    permit = dict(
        decision_id=str(uuid4()),
        supersedes_decision_id=row.id,
        source_sha256=scope["source_idml_sha256"],
        issued_at=now.isoformat(),
        expires_at=(now + timedelta(days=2)).isoformat(),
    )
    owner = dict(
        version="web-public-sources-1",
        organization_id=org.id,
        profile=scope["journal_profile_id"],
        delegate_operators=True,
        articles={scope["resource_id"]: permit},
    )
    (root / (org.id + ".json")).write_text(json.dumps(owner))
    admin.is_active = False
    op = _user(db, org, "pilot-op@example.test", Role.OPERATOR)
    reader = _user(db, org, "pilot-reader@example.test", Role.REVIEWER)
    headers = _headers(_token(db, op, settings), org)
    view = _headers(_token(db, reader, settings), org)
    db.commit()
    url = f"/v1/resources/{scope['resource_id']}/public-sources"
    assert access.resolve(db, scope)["decision_id"] == permit["decision_id"]
    with pytest.raises(ValueError):
        access.resolve(db, scope | {"source_idml_sha256": "f" * 64})
    assert client.get(url, headers=view).json()["status"] == "active"
    assert not client.get(url, headers=view).json()["can_manage"]
    policy_path = root / (org.id + ".json")
    for field, value in [
        ("expires_at", (now - timedelta(seconds=1)).isoformat()),
        ("issued_at", (now + timedelta(hours=1)).isoformat()),
        ("source_sha256", "0" * 64),
        ("supersedes_decision_id", str(uuid4())),
    ]:
        owner["articles"][scope["resource_id"]] = permit | {field: value}
        policy_path.write_text(json.dumps(owner))
        with pytest.raises(ValueError):
            access.resolve(db, scope)
    owner["articles"][scope["resource_id"]] = permit
    owner["delegate_operators"] = False
    policy_path.write_text(json.dumps(owner))
    assert not client.get(url, headers=headers).json()["can_manage"]
    owner["delegate_operators"] = True
    policy_path.write_text(json.dumps(owner))
    for field in ["organization_id", "resource_id"]:
        with pytest.raises((ValueError, LookupError)):
            access.resolve(db, scope | {field: str(uuid4())})
    body = dict(request_id=str(uuid4()), expected_sequence=1, action="revoke", days=1)
    assert client.post(url, headers=view, json=body).status_code == 403
    assert client.post(url, headers=headers, json=body).status_code == 200
    with pytest.raises(ValueError):
        access.resolve(db, scope)
    assert (
        client.post(
            url,
            headers=headers,
            json=body | dict(action="grant", expected_sequence=2, request_id=str(uuid4())),
        ).status_code
        == 200
    )
    assert access.resolve(db, scope)["decision_id"] != permit["decision_id"]
    db.query(Membership).filter_by(user_id=op.id, organization_id=org.id).one().is_active = False
    db.commit()
    with pytest.raises(ValueError):
        access.resolve(db, scope)


def test_web_restore_uses_prior_pdf_and_rejects_incomplete_validation(db, settings):
    data = with_package_inputs(db, persisted_data(db, settings))
    from pathlib import Path

    settings.journal_profile_path = Path("profiles/esa-aop-1.1.json")
    promote(db, data)
    db.commit()
    snap = head(db, data)
    org, rid = snap.organization_id, snap.resource_id
    version = db.get(Resource, rid).version
    action, origin = web_restore.restore_choice(db, org, rid)
    assert action == "undo" and origin.snapshot_id == snap.id
    body = dict(
        resource_id=rid, canonical_snapshot_id=snap.id, review_version=version, action=action
    )
    with pytest.raises(ValidationError):
        JobCreate(
            kind="autocorrection.restore",
            idempotency_key="restore-guard",
            payload=body | {"pdf_artifact_id": str(uuid4())},
        )

    def job(payload):
        return SimpleNamespace(organization_id=org, id=str(uuid4()), payload=payload)

    for invalid in [body | {"review_version": version + 1}, body | {"action": "recover"}]:
        assert (
            web_restore.restore_from_web(db, job(invalid), settings)["reason"] == "revision_changed"
        )
    with pytest.raises(ValueError, match="exact_asset_mapping"):
        web_restore.restore_from_web(db, job(body), settings)
    assert head(db, data).id == snap.id
    # The synthetic original lacks a figure binding. Recovering the admitted copy
    # does reach the native checks, which are unavailable in this isolated test.
    restore_working_head(
        db,
        organization_id=org,
        resource_id=rid,
        target_snapshot_id=origin.previous_snapshot_id,
        expected_snapshot_id=snap.id,
        expected_resource_version=version,
        request_id=uuid4(),
    )
    previous = head(db, data)
    current_version = db.get(Resource, rid).version
    result = web_restore.restore_from_web(
        db,
        job(
            body
            | dict(
                action="recover", canonical_snapshot_id=previous.id, review_version=current_version
            )
        ),
        settings,
    )
    assert (
        result["reason"] == "restore_validation_unavailable"
        and not result["active_snapshot_changed"]
    )
    assert head(db, data).id == previous.id and db.get(Resource, rid).version == current_version
