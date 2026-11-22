from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from idml_foundation.models import Organization
from idml_foundation.rbac import Role
from idml_foundation.services.job_errors import operator_error_detail
from idml_foundation.settings import Settings
from idml_foundation.worker import PermanentJobError, process_job
from tests.phase3_helpers import synthetic_idml
from tests.test_phase7_v10_workflow import _headers, _RedisWakeup, _upload, _user


def test_missing_linked_asset_is_named_in_job_result(
    client: TestClient,
    db: Session,
    session_factory: sessionmaker[Session],
    settings: Settings,
    monkeypatch: object,
) -> None:
    monkeypatch.setattr(  # type: ignore[attr-defined]
        "idml_foundation.routers.jobs.Redis.from_url", lambda _url, **_kwargs: _RedisWakeup()
    )
    org = Organization(slug="error-detail", name="Error detail")
    db.add(org)
    db.flush()
    headers = _headers(db, _user(db, org, "op-detail@example.test", Role.OPERATOR), org, settings)
    resource = client.post("/v1/resources", headers=headers, json={"title": "Detail"}).json()
    idml = _upload(client, headers, "/v1/artifacts/idml", "ESA_2024001_AOP.idml", synthetic_idml())
    pdf = _upload(client, headers, "/v1/artifacts/assets", "article.pdf", b"%PDF-1.4\n% x\n")
    converted = client.post(
        "/v1/jobs",
        headers=headers,
        json={
            "kind": "idml.process",
            "idempotency_key": "detail-process-0001",
            "payload": {"resource_id": resource["id"], "idml_artifact_id": idml["id"]},
        },
    ).json()
    process_job(converted["id"], session_factory, settings=settings)
    snapshot = client.get(f"/v1/jobs/{converted['id']}", headers=headers).json()["result"][
        "canonical_snapshot_id"
    ]

    package = client.post(
        "/v1/jobs",
        headers=headers,
        json={
            "kind": "scielo.package",
            "idempotency_key": "detail-package-0001",
            "payload": {
                "resource_id": resource["id"],
                "canonical_snapshot_id": snapshot,
                "idml_artifact_id": idml["id"],
                "pdf_artifact_id": pdf["id"],
                "asset_artifact_ids": [],
            },
        },
    ).json()
    process_job(package["id"], session_factory, settings=settings)
    failed = client.get(f"/v1/jobs/{package['id']}", headers=headers).json()

    assert failed["state"] == "failed_permanent"
    assert failed["error_code"] == "invalid_job_input"
    assert failed["result"] == {
        "error_detail": {"reason": "missing_package_asset", "subject": "Figure 1.jpg"}
    }


def test_error_detail_never_exposes_unknown_messages_or_paths() -> None:
    assert operator_error_detail(FileNotFoundError("/srv/private/artifacts/x")) == {
        "reason": "input_file_unavailable"
    }
    assert operator_error_detail(ValueError("lxml: Opening and ending tag mismatch")) == {
        "reason": "unclassified"
    }
    assert operator_error_detail(ValueError("missing package asset: ../etc/passwd")) == {
        "reason": "unclassified"
    }
    assert operator_error_detail(PermanentJobError("pdf_artifact_id is not a PDF artifact")) == {
        "reason": "not_a_pdf"
    }


def test_diagnosis_of_rejected_job_names_the_input_instead_of_missing_validation() -> None:
    from idml_foundation.services.validation_diagnosis import describe_validation

    diagnosis = describe_validation(
        {"error_detail": {"reason": "missing_package_asset", "subject": "Eqs.pdf"}}
    )
    assert [item["code"] for item in diagnosis["items"]] == ["job-input-rejected"]
    assert "Eqs.pdf" in diagnosis["items"][0]["detail"]
    assert diagnosis["items"][0]["reason"] == "missing_package_asset"
    assert diagnosis["approval_granted"] is False
