import json
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from idml_foundation.database import get_db
from idml_foundation.main import create_app
from idml_foundation.models import Artifact, DomainSnapshot, Job, Membership, Organization
from idml_foundation.rbac import Role
from idml_foundation.settings import get_settings
from idml_foundation.worker import process_job
from ops.qualify_edit_cycle import config, prepare
from tests.autocorrection_helpers import SyntheticCleanScanner
from tests.test_phase7_v10_workflow import _headers, _RedisWakeup, _user


def test_operator_revision_decision_from_web_queue(tmp_path, monkeypatch):
    prepare(tmp_path, SyntheticCleanScanner())
    cfg = config(tmp_path)
    engine = create_engine(cfg.database_url)
    factory = sessionmaker(engine, expire_on_commit=False)
    app = create_app()

    def database():
        with factory() as db:
            yield db
            db.commit()

    app.dependency_overrides.update({get_settings: lambda: cfg, get_db: database})
    monkeypatch.setattr(
        "idml_foundation.routers.jobs.Redis.from_url", lambda *a, **k: _RedisWakeup()
    )
    case = json.loads((tmp_path / "case.json").read_bytes())
    with factory() as db, TestClient(app) as client:
        j = db.get(Job, case["job_id"])
        org = db.get(Organization, j.organization_id)
        operator = _user(db, org, "operator-web@example.test", Role.OPERATOR)
        op = _headers(db, operator, org, cfg)
        reader = _headers(db, _user(db, org, "reader-web@example.test", Role.REVIEWER), org, cfg)
        body = {k: v for k, v in j.payload.items() if k != "authorization_id"}

        def send(headers, payload):
            return client.post(
                "/v1/jobs",
                headers=headers,
                json=dict(
                    kind="autocorrection.authorize", idempotency_key=uuid4().hex, payload=payload
                ),
            )

        def finish(response):
            assert response.status_code == 202
            jid = response.json()["id"]
            process_job(jid, factory, settings=cfg)
            row = client.get("/v1/jobs/" + jid, headers=op).json()
            assert row["state"] == "succeeded", row
            return row["result"]

        assert send(reader, body).status_code == 403
        assert send(op, body | {"allowed_literal_sha256": "a" * 64}).status_code == 422
        assert finish(send(op, body))["reason"] == "provider_window_closed"
        cfg.feature_web_edit_provider = True
        assert (
            finish(send(op, body | {"review_version": body["review_version"] + 1}))["reason"]
            == "revision_changed"
        )
        assert finish(send(op, body))["reason"] == "revision_package_required"
        pdf = db.get(Artifact, case["pdf_id"])
        source = db.get(DomainSnapshot, body["canonical_snapshot_id"]).source_artifact_id
        pkg = Job(
            organization_id=org.id,
            kind="scielo.package",
            state="succeeded",
            idempotency_key=uuid4().hex,
            payload={
                "resource_id": body["resource_id"],
                "canonical_snapshot_id": body["canonical_snapshot_id"],
                "pdf_artifact_id": pdf.id,
                "idml_artifact_id": source,
            },
            result={"manifest": {"files": [{"role": "pdf", "sha256": "0" * 64}]}},
        )
        db.add(pkg)
        db.commit()
        assert finish(send(op, body))["reason"] == "restore_pdf_missing"
        pkg.result = {"manifest": {"files": [{"role": "pdf", "sha256": pdf.sha256}]}}
        db.commit()
        result = finish(send(op, body))
        assert result["reason"] == "formal_validation_unavailable" and result["provider_calls"] == 0
        assert result["web_authorization"]["package_job_id"] == pkg.id
        queued = send(op, body)
        membership = (
            db.query(Membership).filter_by(user_id=operator.id, organization_id=org.id).one()
        )
        membership.is_active = False
        db.commit()
        jid = queued.json()["id"]
        process_job(jid, factory, settings=cfg)
        assert (
            client.get("/v1/jobs/" + jid, headers=reader).json()["result"]["reason"]
            == "operator_authorization_required"
        )
    engine.dispose()
