import hashlib
import json
from io import BytesIO
from zipfile import ZipFile

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from idml_foundation.models import (
    AgentProposal,
    AgentRun,
    Artifact,
    AuditEvent,
    DomainSnapshot,
    Job,
    JobEffect,
    Membership,
    Organization,
    User,
    utcnow,
)
from idml_foundation.rbac import Role
from idml_foundation.security import hash_password, issue_session
from idml_foundation.services.jobs import create_job, transition_job
from idml_foundation.settings import Settings
from idml_foundation.worker import process_job
from tests.phase3_helpers import synthetic_idml

PASSWORD = "a sufficiently long phase ten password"


class _RedisWakeup:
    def lpush(self, queue: str, job_id: str) -> int:
        assert queue == "idml:jobs"
        assert job_id
        return 1


def _user(db: Session, org: Organization, email: str, role: Role, *, mfa: bool = False) -> User:
    user = User(
        email=email,
        password_hash=hash_password(PASSWORD),
        mfa_enabled_at=utcnow() if mfa else None,
    )
    db.add(user)
    db.flush()
    db.add(Membership(user_id=user.id, organization_id=org.id, role=role.value))
    db.flush()
    return user


def _headers(db: Session, user: User, org: Organization, settings: Settings) -> dict[str, str]:
    token = issue_session(db, user, settings, mfa_verified=user.mfa_enabled_at is not None)
    db.commit()
    return {"Authorization": f"Bearer {token.raw_token}", "X-Organization-ID": org.id}


def _upload(
    client: TestClient,
    headers: dict[str, str],
    endpoint: str,
    name: str,
    data: bytes,
) -> dict[str, object]:
    response = client.post(endpoint, headers=headers, files={"upload": (name, data)})
    assert response.status_code == 201, response.text
    return response.json()


def test_v10_full_operational_flow_is_idempotent_auditable_and_ai_optional(
    client: TestClient,
    db: Session,
    session_factory: sessionmaker[Session],
    settings: Settings,
    monkeypatch: object,
) -> None:
    monkeypatch.setattr(  # type: ignore[attr-defined]
        "idml_foundation.routers.jobs.Redis.from_url", lambda _url, **_kwargs: _RedisWakeup()
    )
    org = Organization(slug="v10-flow", name="V10 Operational Flow")
    db.add(org)
    db.flush()
    operator = _user(db, org, "operator-v10@example.test", Role.OPERATOR)
    reviewer = _user(db, org, "reviewer-v10@example.test", Role.REVIEWER)
    requester = _user(db, org, "requester-v10@example.test", Role.ORG_ADMIN, mfa=True)
    approver_one = _user(db, org, "approver-one-v10@example.test", Role.RELEASE_MANAGER, mfa=True)
    approver_two = _user(db, org, "approver-two-v10@example.test", Role.RELEASE_MANAGER, mfa=True)
    operator_headers = _headers(db, operator, org, settings)
    reviewer_headers = _headers(db, reviewer, org, settings)
    requester_headers = _headers(db, requester, org, settings)
    approver_one_headers = _headers(db, approver_one, org, settings)
    approver_two_headers = _headers(db, approver_two, org, settings)

    resource_response = client.post(
        "/v1/resources", headers=operator_headers, json={"title": "V10 end-to-end article"}
    )
    assert resource_response.status_code == 201
    resource_id = resource_response.json()["id"]
    idml = _upload(
        client,
        operator_headers,
        "/v1/artifacts/idml",
        "ESA_2024001_AOP.idml",
        synthetic_idml(include_graphic_mention=True),
    )
    pdf = _upload(
        client,
        operator_headers,
        "/v1/artifacts/assets",
        "article.pdf",
        b"%PDF-1.4\n% deterministic V10 fixture\n",
    )
    figure = _upload(
        client,
        operator_headers,
        "/v1/artifacts/assets",
        "1809-4457-esa-30-e20240001-gf01.jpg",
        b"\xff\xd8\xff\xe0 deterministic V10 fixture",
    )

    process_payload = {
        "kind": "idml.process",
        "idempotency_key": "v10-process-article-0001",
        "payload": {"resource_id": resource_id, "idml_artifact_id": idml["id"]},
    }
    queued = client.post("/v1/jobs", headers=operator_headers, json=process_payload)
    assert queued.status_code == 202, queued.text
    process_job(queued.json()["id"], session_factory, settings=settings)
    completed = client.get(f"/v1/jobs/{queued.json()['id']}", headers=operator_headers)
    assert completed.status_code == 200
    process_result = completed.json()["result"]
    assert completed.json()["state"] == "succeeded"
    assert process_result["validation"]["valid"] is True

    xml_download = client.get(
        f"/v1/artifacts/{process_result['xml_artifact_id']}/download", headers=operator_headers
    )
    assert xml_download.status_code == 200
    assert hashlib.sha256(xml_download.content).hexdigest() == process_result["xml_sha256"]

    before = {
        "jobs": db.scalar(select(func.count(Job.id))),
        "effects": db.scalar(select(func.count(JobEffect.id))),
        "artifacts": db.scalar(select(func.count(Artifact.id))),
        "snapshots": db.scalar(select(func.count(DomainSnapshot.id))),
        "job_audits": db.scalar(
            select(func.count(AuditEvent.id)).where(AuditEvent.action == "job.create")
        ),
    }
    repeated = client.post("/v1/jobs", headers=operator_headers, json=process_payload)
    assert repeated.status_code == 202
    assert repeated.json()["id"] == queued.json()["id"]
    process_job(repeated.json()["id"], session_factory, settings=settings)
    after = {
        "jobs": db.scalar(select(func.count(Job.id))),
        "effects": db.scalar(select(func.count(JobEffect.id))),
        "artifacts": db.scalar(select(func.count(Artifact.id))),
        "snapshots": db.scalar(select(func.count(DomainSnapshot.id))),
        "job_audits": db.scalar(
            select(func.count(AuditEvent.id)).where(AuditEvent.action == "job.create")
        ),
    }
    assert after == before
    conflict = client.post(
        "/v1/jobs",
        headers=operator_headers,
        json={
            **process_payload,
            "payload": {"resource_id": resource_id, "idml_artifact_id": pdf["id"]},
        },
    )
    assert conflict.status_code == 409

    review = client.post(
        "/v1/reviews",
        headers=operator_headers,
        json={
            "resource_id": resource_id,
            "base_snapshot_id": process_result["canonical_snapshot_id"],
            "job_id": queued.json()["id"],
            "category": "semantic",
            "rule_code": "V10_TITLE_CONFIRMATION",
            "field_path": "/front/titles/0/text/value",
            "message": "Confirm title against IDML and source PDF",
            "evidence": [{"source": "IDML", "locator": "Stories/Story_u1.xml"}],
            "alternatives": ["Deterministic conversion", "V10 confirmed title"],
        },
    )
    assert review.status_code == 201, review.text
    claimed = client.post(
        f"/v1/reviews/{review.json()['id']}/claim",
        headers=reviewer_headers,
        json={"expected_version": 1},
    )
    assert claimed.status_code == 200
    decision = client.post(
        f"/v1/reviews/{review.json()['id']}/decisions",
        headers=reviewer_headers,
        json={
            "expected_version": 2,
            "action": "apply_patch",
            "patch": [
                {
                    "op": "replace",
                    "path": "/front/titles/0/text/value",
                    "value": "V10 confirmed title",
                }
            ],
            "justification": "The title was confirmed against the supplied source evidence.",
        },
    )
    assert decision.status_code == 200, decision.text
    assert decision.json()["state"] == "resolved"
    assert decision.json()["validation_valid"] is True

    package_payload = {
        "kind": "scielo.package",
        "idempotency_key": "v10-package-article-0001",
        "payload": {
            "resource_id": resource_id,
            "canonical_snapshot_id": decision.json()["result_snapshot_id"],
            "idml_artifact_id": idml["id"],
            "pdf_artifact_id": pdf["id"],
            "asset_artifact_ids": [figure["id"]],
        },
    }
    package_job = client.post("/v1/jobs", headers=operator_headers, json=package_payload)
    assert package_job.status_code == 202, package_job.text
    process_job(package_job.json()["id"], session_factory, settings=settings)
    package_status = client.get(
        f"/v1/jobs/{package_job.json()['id']}", headers=operator_headers
    ).json()
    assert package_status["state"] == "succeeded"
    package_result = package_status["result"]
    formal = package_result["formal_validation"]
    assert formal["state"] == "validation-unavailable"
    assert formal["package_sha256"] == package_result["package_sha256"]
    assert not formal["ready_for_scielo"]
    package_download = client.get(
        f"/v1/artifacts/{package_result['package_artifact_id']}/download",
        headers=operator_headers,
    )
    assert package_download.status_code == 200
    assert hashlib.sha256(package_download.content).hexdigest() == package_result["package_sha256"]
    with ZipFile(BytesIO(package_download.content)) as archive:
        manifest = json.loads(archive.read("conversion-manifest.json"))
        assert manifest == package_result["manifest"]
        for entry in manifest["files"]:
            data = archive.read(entry["name"])
            assert len(data) == entry["size_bytes"]
            assert hashlib.sha256(data).hexdigest() == entry["sha256"]
    assert manifest["candidate_set_sha256"] == package_result["candidate_set_sha256"]

    release = client.post(
        "/v1/releases",
        headers=requester_headers,
        json={
            "resource_id": resource_id,
            "snapshot_id": decision.json()["result_snapshot_id"],
            "package_sha256": package_result["package_sha256"],
        },
    )
    assert release.status_code == 201, release.text
    first_approval = client.post(
        f"/v1/releases/{release.json()['id']}/approvals",
        headers=approver_one_headers,
        json={
            "expected_version": 1,
            "justification": "First independent editorial approval for the V10 package.",
            "evidence_sha256": package_result["package_sha256"],
        },
    )
    assert first_approval.status_code == 200, first_approval.text
    second_approval = client.post(
        f"/v1/releases/{release.json()['id']}/approvals",
        headers=approver_two_headers,
        json={
            "expected_version": 2,
            "justification": "Second independent editorial approval for the V10 package.",
            "evidence_sha256": package_result["package_sha256"],
        },
    )
    assert second_approval.status_code == 200, second_approval.text
    assert second_approval.json()["request_state"] == "editorially_approved"
    assert (
        client.get(f"/v1/jobs/{package_job.json()['id']}", headers=operator_headers).json()[
            "result"
        ]["formal_validation"]
        == formal
    )

    capabilities = client.get("/v1/ai/capabilities", headers=operator_headers)
    assert capabilities.status_code == 200
    assert capabilities.json()["enabled"] is False
    assert capabilities.json()["swarm_enabled"] is False
    assert db.scalar(select(func.count(AgentRun.id))) == 0
    assert db.scalar(select(func.count(AgentProposal.id))) == 0
    audit_actions = set(db.scalars(select(AuditEvent.action)))
    assert {
        "artifact.upload",
        "artifact.download",
        "job.create",
        "job.complete",
        "review.create",
        "review.claim",
        "review.decide",
        "release.request",
        "release.approve",
    }.issubset(audit_actions)


def test_v10_job_cancel_manual_retry_and_transient_resume(
    client: TestClient,
    db: Session,
    session_factory: sessionmaker[Session],
    settings: Settings,
    monkeypatch: object,
) -> None:
    monkeypatch.setattr(  # type: ignore[attr-defined]
        "idml_foundation.routers.jobs.Redis.from_url", lambda _url, **_kwargs: _RedisWakeup()
    )
    org = Organization(slug="v10-control", name="V10 Job Control")
    db.add(org)
    db.flush()
    operator = _user(db, org, "control-v10@example.test", Role.OPERATOR)
    headers = _headers(db, operator, org, settings)

    queued = client.post(
        "/v1/jobs",
        headers=headers,
        json={"kind": "foundation.noop", "idempotency_key": "v10-cancel-0001", "payload": {}},
    ).json()
    cancelled = client.post(
        f"/v1/jobs/{queued['id']}/cancel",
        headers=headers,
        json={"expected_version": queued["version"]},
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["state"] == "cancelled"
    assert cancelled.json()["cancelled_at"] is not None
    stale_cancel = client.post(
        f"/v1/jobs/{queued['id']}/cancel",
        headers=headers,
        json={"expected_version": queued["version"]},
    )
    assert stale_cancel.status_code == 409

    retryable, _ = create_job(
        db,
        organization_id=org.id,
        kind="foundation.noop",
        idempotency_key="v10-manual-retry-0001",
        payload={},
        correlation_id="v10-create",
        actor_id=operator.id,
    )
    transition_job(
        db,
        retryable,
        to_state="running",
        correlation_id="v10-run",
        actor_type="worker",
    )
    transition_job(
        db,
        retryable,
        to_state="failed_retryable",
        correlation_id="v10-failure",
        actor_type="worker",
        error_code="temporary",
    )
    retryable_id = retryable.id
    retryable_version = retryable.version
    db.commit()
    retried = client.post(
        f"/v1/jobs/{retryable_id}/retry",
        headers=headers,
        json={"expected_version": retryable_version},
    )
    assert retried.status_code == 200
    assert retried.json()["state"] == "queued"
    process_job(retryable_id, session_factory, settings=settings)
    assert client.get(f"/v1/jobs/{retryable_id}", headers=headers).json()["state"] == "succeeded"

    transient, _ = create_job(
        db,
        organization_id=org.id,
        kind="idml.process",
        idempotency_key="v10-transient-resume-0001",
        payload={"resource_id": "unused", "idml_artifact_id": "unused"},
        correlation_id="v10-transient-create",
        actor_id=operator.id,
    )
    transient_id = transient.id
    db.commit()
    calls = 0

    def flaky(_db: Session, _job: Job, _settings: Settings) -> dict[str, object]:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("simulated transient dependency failure")
        return {"resumed": True}

    monkeypatch.setattr("idml_foundation.worker._process_idml_job", flaky)  # type: ignore[attr-defined]
    process_job(transient_id, session_factory, settings=settings)
    with session_factory() as check:
        pending = check.get(Job, transient_id)
        assert pending is not None
        assert pending.state == "queued"
        assert pending.attempt_count == 1
        pending.available_at = utcnow()
        check.commit()
    process_job(transient_id, session_factory, settings=settings)
    resumed = client.get(f"/v1/jobs/{transient_id}", headers=headers).json()
    assert resumed["state"] == "succeeded"
    assert resumed["attempt_count"] == 2
    assert resumed["result"] == {"resumed": True}
    events = client.get(f"/v1/jobs/{transient_id}/events", headers=headers).json()
    assert [event["to_state"] for event in events] == [
        "queued",
        "running",
        "failed_retryable",
        "queued",
        "running",
        "succeeded",
    ]


def test_v10_interface_exposes_operational_states_and_controls(client: TestClient) -> None:
    page = client.get("/app")
    script = client.get("/app/assets/app.js")
    assert page.status_code == 200
    assert script.status_code == 200
    for label in (
        "Criar artigo",
        "Converter IDML",
        "Revisão e pacote SciELO",
        "Imagens do artigo",
    ):
        assert label in page.text
    for contract in (
        "/v1/jobs/${button.dataset.cancelJob||button.dataset.retryJob}/${action}",
        "failed_retryable",
        "error_code",
        "JSON.stringify(j.result",
    ):
        assert contract in script.text
