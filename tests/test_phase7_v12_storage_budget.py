import hashlib
import subprocess
import sys
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from idml_foundation import worker
from idml_foundation.models import Artifact, AuditEvent, Job, Organization
from idml_foundation.rbac import Role
from idml_foundation.services import artifacts
from idml_foundation.services import storage_budget as budget
from idml_foundation.services.jobs import create_job
from tests.test_phase7_v10_workflow import _headers, _user


@pytest.fixture
def tenant(db):
    organization = Organization(slug="storage-budget", name="Storage budget")
    db.add(organization)
    db.commit()
    return organization.id


def store(db, settings, tenant, data=b"<x/>", media_type="application/xml"):
    return artifacts.store_generated_artifact(
        db,
        organization_id=tenant,
        original_name="generated.xml",
        data=data,
        media_type=media_type,
        settings=settings,
    )


def test_quota_exact_boundary_dedup_and_tenant_isolation(db, settings, tenant):
    settings.artifact_tenant_quota_bytes = 4
    first = store(db, settings, tenant)
    assert store(db, settings, tenant).id == first.id
    with pytest.raises(budget.ArtifactStorageError, match="artifact_quota_exceeded"):
        store(db, settings, tenant, b"z")
    other = Organization(slug="other-budget", name="Other")
    db.add(other)
    db.flush()
    second = store(db, settings, other.id)
    assert second.storage_key != first.storage_key
    assert db.scalar(select(func.count(Artifact.id))) == 2


def test_file_count_includes_generated_packages(db, settings, tenant):
    settings.artifact_tenant_max_files = 1
    store(db, settings, tenant, b"ZIP", "application/zip")
    with pytest.raises(budget.ArtifactStorageError, match="artifact_quota_exceeded"):
        store(db, settings, tenant)


def test_rollback_orphan_remains_charged_and_is_recovered(db, settings, tenant):
    settings.artifact_tenant_quota_bytes = 4
    original = store(db, settings, tenant)
    path = settings.artifact_root / original.storage_key
    db.rollback()
    assert path.read_bytes() == b"<x/>"
    assert db.scalar(select(func.count(Artifact.id))) == 0
    with pytest.raises(budget.ArtifactStorageError, match="artifact_quota_exceeded"):
        store(db, settings, tenant, b"y")
    recovered = store(db, settings, tenant)
    assert recovered.storage_key == original.storage_key
    assert budget.tenant_usage(settings.artifact_root / tenant, settings) == (4, 1)


@pytest.mark.parametrize("corruption", ["missing", "same_size", "size"])
def test_registered_dedup_never_accepts_corrupt_file(db, settings, tenant, corruption):
    original = store(db, settings, tenant)
    path = settings.artifact_root / original.storage_key
    if corruption == "missing":
        path.unlink()
    else:
        path.write_bytes(b"xxxx" if corruption == "same_size" else b"x")
    with pytest.raises(budget.ArtifactStorageError, match="artifact_storage_integrity"):
        store(db, settings, tenant)


def test_unregistered_corrupt_file_is_not_adopted(db, settings, tenant):
    digest = hashlib.sha256(b"<x/>").hexdigest()
    path = settings.artifact_root / tenant / digest[:2] / digest
    path.parent.mkdir(parents=True)
    path.write_bytes(b"evil")
    with pytest.raises(budget.ArtifactStorageError, match="artifact_storage_integrity"):
        store(db, settings, tenant)
    assert path.read_bytes() == b"evil"


@pytest.mark.parametrize("offset", [-1, 0])
def test_disk_reserve_boundary(db, settings, tenant, monkeypatch, offset):
    settings.artifact_disk_reserve_bytes = 10000
    monkeypatch.setattr(budget.shutil, "disk_usage", lambda _: SimpleNamespace(free=14096 + offset))
    if offset < 0:
        with pytest.raises(budget.ArtifactStorageError, match="artifact_disk_reserve"):
            store(db, settings, tenant)
        assert not (settings.artifact_root / tenant).exists()
    else:
        assert store(db, settings, tenant).size_bytes == 4


def test_failed_atomic_publish_removes_temporary(db, settings, tenant, monkeypatch):
    def fail(*_):
        raise OSError("synthetic disk failure")

    monkeypatch.setattr(artifacts.os, "replace", fail)
    with pytest.raises(budget.ArtifactStorageError, match="artifact_storage_unavailable"):
        store(db, settings, tenant)
    assert list(settings.artifact_root.rglob(".upload-*")) == []
    assert db.scalar(select(func.count(Artifact.id))) == 0


@pytest.mark.parametrize("end", ["commit", "rollback", "close"])
def test_lock_survives_savepoint_but_not_outer_transaction(db, settings, tenant, end):
    with Session(db.get_bind()) as other:
        budget.lock_storage(db, settings)
        with db.begin_nested():
            pass
        with pytest.raises(budget.ArtifactStorageError, match="artifact_storage_busy"):
            budget.lock_storage(other, settings)
        getattr(db, end)()
        assert budget.lock_storage(other, settings) == settings.artifact_root.resolve()


def test_another_process_cannot_write_until_transaction_ends(db, settings, tenant):
    script = """
import sys
from sqlalchemy.orm import Session
from idml_foundation.settings import Settings
from idml_foundation.services.storage_budget import lock_storage, ArtifactStorageError
with Session() as session:
    try:
        lock_storage(session, Settings(artifact_root=sys.argv[1]))
        print('admitted')
    except ArtifactStorageError as exc:
        print(exc.code)
"""

    def child():
        return subprocess.run(  # noqa: S603 -- fixed local test script
            [sys.executable, "-c", script, str(settings.artifact_root)],
            capture_output=True,
            text=True,
            timeout=20,
            check=True,
        ).stdout.strip()

    store(db, settings, tenant)
    assert child() == "artifact_storage_busy"
    db.commit()
    assert child() == "admitted"


def test_unknown_partial_file_is_counted(db, settings, tenant):
    folder = settings.artifact_root / tenant / "ab"
    folder.mkdir(parents=True)
    (folder / ".upload-abandoned").write_bytes(b"x" * 4)
    settings.artifact_tenant_quota_bytes = 4
    with pytest.raises(budget.ArtifactStorageError, match="artifact_quota_exceeded"):
        store(db, settings, tenant)


@pytest.mark.parametrize("tenant_id", ["../escape", "invalid", "00000000000000000000000000000000"])
def test_invalid_tenant_storage_path_rejected(db, settings, tenant_id):
    with pytest.raises(budget.ArtifactStorageError, match="artifact_storage_integrity"):
        store(db, settings, tenant_id)


def test_http_upload_quota_returns_safe_error(client, db, settings, tenant):
    org = db.get(Organization, tenant)
    user = _user(db, org, "budget@example.test", Role.OPERATOR)
    headers = _headers(db, user, org, settings)
    settings.artifact_tenant_quota_bytes = 4
    response = client.post(
        "/v1/artifacts/assets", headers=headers, files={"upload": ("x.pdf", b"%PDF-x")}
    )
    assert response.status_code == 409
    assert response.json()["code"] == "artifact_quota_exceeded"
    assert str(settings.artifact_root) not in response.text


@pytest.mark.parametrize("retryable", [True, False])
def test_worker_storage_failure_has_specific_state_and_code(
    db, session_factory, settings, tenant, monkeypatch, retryable
):
    job, _ = create_job(
        db,
        organization_id=tenant,
        kind="idml.process",
        idempotency_key="storage-failure",
        payload={},
        correlation_id="storage-test",
        actor_id="synthetic",
    )
    job_id = job.id
    db.commit()
    code = "artifact_disk_reserve" if retryable else "artifact_storage_integrity"

    def fail(*_):
        raise budget.ArtifactStorageError(code, retryable=retryable)

    monkeypatch.setattr(worker, "_process_idml_job", fail)
    worker.process_job(job_id, session_factory, settings=settings)
    db.expire_all()
    job = db.get(Job, job_id)
    assert job.state == ("queued" if retryable else "failed_permanent")
    if not retryable:
        assert job.error_code == code
    event = db.scalar(
        select(AuditEvent)
        .where(AuditEvent.resource_id == job_id)
        .order_by(AuditEvent.created_at.desc())
    )
    assert event.details["error_code"] == code
