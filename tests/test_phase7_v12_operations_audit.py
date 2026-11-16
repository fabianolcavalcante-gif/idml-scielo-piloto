import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import event

from idml_foundation.models import Organization
from idml_foundation.services.artifacts import store_generated_artifact
from ops.audit_storage import audit_storage, valid_key
from ops.plan_backup_retention import REQUIRED, inventory


@pytest.fixture
def recorded(db, settings, monkeypatch):
    monkeypatch.setattr(
        "ops.audit_storage.shutil.disk_usage", lambda _: SimpleNamespace(free=10**12)
    )
    org = Organization(slug="audit", name="Not emitted")
    db.add(org)
    db.flush()
    artifact = store_generated_artifact(
        db,
        organization_id=org.id,
        original_name="private-article-name.xml",
        data=b"<private/>",
        media_type="application/xml",
        settings=settings,
    )
    db.commit()
    return artifact


def test_reconciliation_is_read_only_and_content_safe(db, settings, recorded):
    path = settings.artifact_root / recorded.storage_key
    before = (path.read_bytes(), path.stat().st_mtime_ns)
    statements = []

    def capture(_conn, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    event.listen(db.get_bind(), "before_cursor_execute", capture)
    try:
        report = audit_storage(db, settings)
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", capture)
    assert report["severity"] == "ok"
    assert report["complete"] and report["consistency"] == "best_effort"
    assert report["hashes_verified"] is False
    assert all(s.lstrip().upper().startswith("SELECT") for s in statements)
    assert before == (path.read_bytes(), path.stat().st_mtime_ns)
    output = json.dumps(report)
    assert recorded.organization_id not in output
    assert "private" not in output


@pytest.mark.parametrize("kind", ["missing", "size", "orphan", "full", "near", "unsafe"])
def test_audit_finds_storage_problems_without_repair(db, settings, recorded, kind):
    path = settings.artifact_root / recorded.storage_key
    if kind == "missing":
        path.unlink()
        field, severity = "missing", "critical"
    elif kind == "size":
        path.write_bytes(b"damaged")
        field, severity = "size_mismatch", "critical"
    elif kind == "orphan":
        (path.parent / ".upload-abandoned").write_bytes(b"orphan")
        field, severity = "orphan_candidates", "warning"
    elif kind == "full":
        settings.artifact_tenant_max_files = 1
        field, severity = "tenants_full", "critical"
    elif kind == "near":
        settings.artifact_tenant_quota_bytes = 12
        field, severity = "tenants_warning", "warning"
    else:
        (settings.artifact_root / "unexpected").mkdir()
        field, severity = "unsafe_entries", "critical"
    report = audit_storage(db, settings)
    assert report["counts"][field] == 1
    assert report["severity"] == severity


@pytest.mark.parametrize("offset,severity", [(-1, "critical"), (0, "warning"), (209715200, "ok")])
def test_disk_alert_thresholds(db, settings, recorded, monkeypatch, offset, severity):
    monkeypatch.setattr(
        "ops.audit_storage.shutil.disk_usage",
        lambda _: SimpleNamespace(free=settings.artifact_disk_reserve_bytes + offset),
    )
    assert audit_storage(db, settings)["severity"] == severity


def test_incomplete_scan_never_claims_missing_or_healthy(db, settings, recorded):
    report = audit_storage(db, settings, max_entries=1)
    assert not report["complete"]
    assert report["severity"] == "unknown"
    assert report["counts"]["missing"] == 0
    assert report["counts"]["orphan_candidates"] == 0


def test_missing_root_does_not_create_it(db, settings, tmp_path):
    settings.artifact_root = tmp_path / "absent"
    report = audit_storage(db, settings)
    assert report["severity"] == "unknown"
    assert not settings.artifact_root.exists()


@pytest.mark.parametrize("budget", [0, 100001])
def test_invalid_scan_budget_rejected(db, settings, budget):
    with pytest.raises(ValueError):
        audit_storage(db, settings, max_entries=budget)


def make_backup(root, stamp):
    directory = root / stamp.strftime("%Y%m%dT%H%M%SZ")
    directory.mkdir()
    for name in REQUIRED:
        (directory / name).write_bytes(b"synthetic backup, not verified")
    return directory


def test_retention_keeps_recent_and_latest_and_never_deletes(tmp_path):
    now = datetime(2026, 9, 25, tzinfo=UTC)
    directories = [make_backup(tmp_path, now - timedelta(days=i * 10)) for i in range(10)]
    result = inventory(tmp_path, now=now)
    assert result["protected"] == 7
    assert len(result["manual_review_candidates"]) == 3
    assert result["delete_authorized"] is False
    assert result["checksums_verified"] is result["restore_verified"] is False
    assert all((d / name).exists() for d in directories for name in REQUIRED)


def test_incomplete_and_unknown_backups_are_never_candidates(tmp_path):
    now = datetime(2026, 9, 25, tzinfo=UTC)
    directory = make_backup(tmp_path, now - timedelta(days=100))
    (directory / "SHA256SUMS").unlink()
    (tmp_path / "legacy-kept").mkdir()
    result = inventory(tmp_path, now=now, keep_latest=1)
    assert result["unrecognized_or_incomplete"] == 2
    assert result["classification"]["missing_or_empty_payload"] == 1
    assert result["classification"]["noncanonical_name"] == 1
    assert result["missing_or_empty_by_file"]["SHA256SUMS"] == 1
    assert result["manual_review_candidates"] == []


def test_retention_budget_never_returns_partial_candidates(tmp_path):
    now = datetime(2026, 9, 25, tzinfo=UTC)
    for i in range(3):
        make_backup(tmp_path, now - timedelta(days=60 + i))
    result = inventory(tmp_path, now=now, max_entries=1)
    assert not result["complete"]
    assert not result["manual_review_candidates"]


def test_retention_missing_root_is_unknown_without_creation(tmp_path):
    root = tmp_path / "absent"
    assert not inventory(root)["complete"]
    assert not root.exists()


def test_noncanonical_tenant_key_rejected():
    tenant = "-" * 36
    digest = "a" * 64
    assert not valid_key(f"{tenant}/aa/{digest}", tenant, digest)


def test_internal_entry_wrong_type_is_unsafe(db, settings, recorded):
    (settings.artifact_root / ".upload-admission").write_bytes(b"unexpected")
    report = audit_storage(db, settings)
    assert report["counts"]["unsafe_entries"] == 1
    assert report["severity"] == "critical"
