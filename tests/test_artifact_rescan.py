import hashlib

import pytest
from sqlalchemy import select

from idml_foundation.dependencies import get_content_scanner
from idml_foundation.ingest.scanner import ScannerUnavailableError, ScanResult
from idml_foundation.models import Artifact, AuditEvent, Organization
from idml_foundation.rbac import Role
from tests.test_phase7_v10_workflow import _headers, _user


@pytest.mark.parametrize(
    "result,code",
    [
        ("clamav_clean", 200),
        ("malware_detected", 422),
        ("scan_unavailable", 503),
        ("integrity_failure", 409),
    ],
)
def test_rescan_is_tenant_scoped_and_records_exact_stored_input(db, client, settings, result, code):
    org = Organization(slug="scan", name="Scan")
    other = Organization(slug="other", name="Other")
    db.add_all([org, other])
    db.flush()

    def headers(o, role):
        user = _user(db, o, f"{role.value}-{o.slug}@example.test", role)
        return _headers(db, user, o, settings)

    operator = headers(org, Role.OPERATOR)
    reader = headers(org, Role.REVIEWER)
    outsider = headers(other, Role.OPERATOR)
    raw = b"%PDF-1.5\nscan"

    def upload():
        return client.post(
            "/v1/artifacts/assets", headers=operator, files={"upload": ("a.pdf", raw)}
        )

    first = upload().json()
    assert first["scanner_status"] == "policy_only"
    path = "/v1/artifacts/" + first["id"]
    calls = []

    class Scanner:
        def scan(self, data):
            calls.append(data)
            if result == "scan_unavailable":
                raise ScannerUnavailableError("private failure")
            return ScanResult(result == "clamav_clean", result)

    client.app.dependency_overrides[get_content_scanner] = Scanner
    assert client.post(path + "/rescan", headers=outsider).status_code == 404
    assert client.post(path + "/rescan", headers=reader).status_code == 403
    assert not calls
    if result == "integrity_failure":
        artifact = db.get(Artifact, first["id"])
        (settings.artifact_root / artifact.storage_key).write_bytes(raw + b"!")
    response = client.post(path + "/rescan", headers=operator)
    assert response.status_code == code and "private failure" not in response.text
    assert calls == ([] if result == "integrity_failure" else [raw])
    artifact = db.get(Artifact, first["id"], populate_existing=True)
    assert artifact.scanner_status == result
    audit = db.scalar(select(AuditEvent).where(AuditEvent.action == "artifact.rescan"))
    assert audit.outcome == result and audit.details == dict(
        sha256=hashlib.sha256(raw).hexdigest(), previous="policy_only"
    )
    if result == "malware_detected":
        assert client.get(path + "/download", headers=operator).status_code == 409
        assert client.post(path + "/rescan", headers=operator).status_code == 409


def test_duplicate_verified_upload_upgrades_only_the_verified_bytes(db, client, settings):
    org = Organization(slug="duplicate", name="Scan")
    db.add(org)
    db.flush()
    operator = _headers(db, _user(db, org, "u@example.test", Role.OPERATOR), org, settings)

    def upload():
        return client.post(
            "/v1/artifacts/assets",
            headers=operator,
            files={"upload": ("x.jpg", b"\xff\xd8\xffduplicate")},
        )

    first = upload().json()

    class Scanner:
        def scan(self, data):
            return ScanResult(True, "clamav_clean")

    client.app.dependency_overrides[get_content_scanner] = Scanner
    second = upload().json()
    assert second["id"] == first["id"] and second["scanner_status"] == "clamav_clean"

    class Reject:
        def scan(self, data):
            return ScanResult(False, "malware_detected")

    client.app.dependency_overrides[get_content_scanner] = Reject
    assert upload().status_code == 422
    assert (
        db.get(Artifact, first["id"], populate_existing=True).scanner_status == "malware_detected"
    )
