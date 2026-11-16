from pathlib import Path

import pytest
from pydantic import ValidationError

from idml_foundation.schemas import JobCreate
from ops.qualify_edit_preflight import qualify
from tests.autocorrection_helpers import SyntheticCleanScanner
from tests.phase3_helpers import synthetic_idml


def test_worker_edit_decisions_and_abstention(tmp_path, settings):
    source = tmp_path / "ESA_2024099_AOP.idml"
    source.write_bytes(synthetic_idml())
    settings = settings.model_copy(
        update=dict(
            automation_authorization_root=tmp_path / "decisions",
            enrichment_location="local",
            journal_profile_path=Path("profiles/esa-aop-1.1.json"),
        )
    )
    report = qualify(tmp_path, [source], settings, SyntheticCleanScanner())
    assert [case["state"] for case in report["cases"]] == ["abstained", "staged"]


def test_client_cannot_supply_edit_evidence_or_enable_provider():
    from uuid import uuid4

    with pytest.raises(ValidationError):
        JobCreate(
            kind="autocorrection.preflight",
            idempotency_key="negative-case",
            payload=dict(
                resource_id=str(uuid4()),
                canonical_snapshot_id=str(uuid4()),
                review_version=1,
                enabled=True,
                operations=[],
            ),
        )


def test_job_rejects_foreign_resource_without_retry(
    client, db, session_factory, settings, monkeypatch
):
    from uuid import uuid4

    from idml_foundation.models import Organization, Resource
    from idml_foundation.rbac import Role
    from idml_foundation.worker import process_job
    from tests.test_phase7_v10_workflow import _headers, _RedisWakeup, _user

    monkeypatch.setattr(
        "idml_foundation.routers.jobs.Redis.from_url", lambda *a, **kw: _RedisWakeup()
    )
    owner, other = (Organization(slug=s, name=s) for s in ("owner", "other"))
    db.add_all([owner, other])
    db.flush()
    article = Resource(organization_id=owner.id, title="Private")
    db.add(article)
    db.flush()
    headers = _headers(db, _user(db, other, "other@example.test", Role.OPERATOR), other, settings)
    request = dict(
        kind="autocorrection.preflight",
        idempotency_key="foreign-version",
        payload=dict(resource_id=article.id, canonical_snapshot_id=str(uuid4()), review_version=1),
    )
    response = client.post("/v1/jobs", headers=headers, json=request)
    assert response.status_code == 202
    row = response.json()["id"]
    process_job(row, session_factory, settings=settings)
    status = client.get("/v1/jobs/" + row, headers=headers).json()
    assert status["state"] == "failed_permanent" and not status["result"]
