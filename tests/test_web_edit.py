import json
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from idml_foundation.database import get_db
from idml_foundation.main import create_app
from idml_foundation.models import Artifact, Job, Organization
from idml_foundation.rbac import Role
from idml_foundation.schemas import EditEvaluationPayload, JobCreate
from idml_foundation.services.web_edit_cycle import WebEditDecision
from idml_foundation.settings import get_settings
from idml_foundation.worker import process_job
from ops.qualify_edit_cycle import config, prepare
from tests.autocorrection_helpers import SyntheticCleanScanner
from tests.test_phase7_v10_workflow import _headers, _RedisWakeup, _user


def test_authenticated_edit_workspace(tmp_path, monkeypatch):
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
        "idml_foundation.routers.jobs.Redis.from_url", lambda *a, **kw: _RedisWakeup()
    )
    case = json.loads((tmp_path / "case.json").read_bytes())
    try:
        with factory() as db, TestClient(app) as client:
            j = db.get(Job, case["job_id"])
            org = db.get(Organization, j.organization_id)
            read = _headers(db, _user(db, org, "specialist@example.test", Role.REVIEWER), org, cfg)
            op = _headers(db, _user(db, org, "operator@example.test", Role.OPERATOR), org, cfg)
            other = Organization(slug="other", name="Other")
            db.add(other)
            db.flush()
            outside = _headers(
                db, _user(db, other, "outside@example.test", Role.OPERATOR), other, cfg
            )
            payload = {k: v for k, v in j.payload.items() if k != "authorization_id"}
            route = "/v1/resources/" + payload["resource_id"] + "/edit-revisions"
            detail = route + "/" + payload["canonical_snapshot_id"]
            assert client.get(route).status_code == 401
            assert client.get(detail, headers=outside).status_code == 404
            assert not client.get(route, headers=read).json()["can_start"]
            assert (
                client.get(route, headers=op).json()["current"] == payload["canonical_snapshot_id"]
            )
            h = client.get(detail, headers=read).json()
            assert "Example University" in h["candidates"][0]["diff"][0]["after"]
            assert 'content-type="original"' not in h["candidates"][0]["diff"][0]["before"]

            def launch(headers):
                return client.post(
                    "/v1/jobs",
                    headers=headers,
                    json=dict(
                        kind="autocorrection.evaluate", idempotency_key=uuid4().hex, payload=payload
                    ),
                )

            assert launch(read).status_code == 403

            def execute():
                response = launch(op)
                assert response.status_code == 202
                jid = response.json()["id"]
                process_job(jid, factory, settings=cfg)
                row = client.get("/v1/jobs/" + jid, headers=op).json()
                assert row["state"] == "succeeded", row["error_code"]
                return row["result"]

            assert execute()["state"] == "refused"
            selector = WebEditDecision.model_validate(
                dict(
                    scope=payload,
                    organization_id=org.id,
                    authorization_id=j.payload["authorization_id"],
                    purpose="review-and-promote-affiliation-v1",
                    model="openai/gpt-5.4-mini",
                    allowed_literal_sha256="a" * 64,
                    pdf_artifact_id=case["pdf_id"],
                    pdf_sha256=db.get(Artifact, case["pdf_id"]).sha256,
                )
            )
            path = (
                tmp_path
                / "decisions"
                / "web-edit-decisions"
                / org.id
                / payload["resource_id"]
                / payload["canonical_snapshot_id"]
                / f"{payload['review_version']}.json"
            )
            path.parent.mkdir(parents=True)
            path.write_text(selector.model_dump_json())
            assert execute()["reason"] == "provider_window_closed"
            cfg.feature_web_edit_provider = True
            cfg.validator_socket = cfg.xpm_socket = Path("/unused")
            cfg.validator_scoped_authorities = True
            assert execute()["reason"] == "literal_not_authorized"
            h = client.get(detail, headers=op).json()
            assert h["jobs"][0]["provider_calls"] == 0
    finally:
        engine.dispose()


def test_browser_cannot_supply_pdf_grant_or_provider_flag():
    payload = dict(resource_id=uuid4(), canonical_snapshot_id=uuid4(), review_version=1)
    EditEvaluationPayload.model_validate(payload)
    with pytest.raises(ValidationError):
        JobCreate(
            kind="autocorrection.evaluate",
            payload=dict(payload, authorization_id=uuid4()),
            idempotency_key="invalid-input",
        )
