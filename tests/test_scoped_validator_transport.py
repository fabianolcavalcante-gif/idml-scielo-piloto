import copy
import hashlib
import json
import socket
import struct
from pathlib import Path
from types import SimpleNamespace

import pytest

from idml_foundation.release.validation_engine import ValidationEngine, ValidatorStatus
from idml_foundation.services.scoped_validator_transport import (
    ScopedValidatorExecutor,
    check_evidence,
)
from idml_foundation.services.validation_scope import scope_digest
from idml_foundation.settings import Settings
from tests.test_scoped_authority_transport import fixture
from tests.test_validator_transport import FakeSocket, spec


def evidence(scope):
    return {
        "version": "scoped-authority-evidence-1.0",
        "binding": {
            "scope_sha256": scope_digest(scope),
            "bundle_sha256": "a" * 64,
            "grant_sha256": "b" * 64,
        },
        "checks": {
            "doi": [True],
            "issue": [True],
            "section": [True],
            "orcid": [],
            "orcid_reasons": [],
        },
        "expected": {"doi": 1, "issue": 1, "section": 1, "orcid": 0},
    }


def test_client_checks_scope_and_preserves_evidence(monkeypatch):
    scope, _, _, _, xml, _ = fixture()
    specification = spec()
    envelope = json.dumps(
        {
            "adapter_contract": "1.1.0",
            "validator_name": "packtools",
            "validator_version": specification.version,
            "profile_id": specification.profile_id,
            "candidate_sha256": hashlib.sha256(xml).hexdigest(),
            "result": {"findings": [], "authority_evidence": evidence(scope)},
        }
    ).encode()
    fake = FakeSocket(struct.pack("!I", len(envelope)) + envelope)
    monkeypatch.setattr(socket, "SO_PEERCRED", 17, raising=False)
    monkeypatch.setattr(socket, "AF_UNIX", 1, raising=False)
    monkeypatch.setattr(socket, "socket", lambda *args: fake)
    executor = ScopedValidatorExecutor(Path("/private/broker.sock"), scope=scope)
    run = executor(xml, specification)
    assert run.status == ValidatorStatus.COMPLETED
    assert executor.evidence["packtools"]["binding"]["scope_sha256"] == scope_digest(scope)
    length = struct.unpack("!I", fake.sent[:4])[0]
    sent = json.loads(fake.sent[4 : 4 + length])
    assert sent["version"] == "local-validator-1.1" and sent["scope"] == scope
    with pytest.raises(ValueError):
        executor(b"wrong", specification)
    assert executor.evidence == {}


@pytest.mark.parametrize("kind", ["missing", "scope", "grant", "counts", "bool", "reason", "extra"])
def test_missing_or_forged_evidence_never_passes(kind):
    scope, *_ = fixture()
    value = evidence(scope)
    if kind == "missing":
        value = {}
    elif kind in {"scope", "grant"}:
        value["binding"][kind + "_sha256"] = "wrong"
    elif kind == "counts":
        value["checks"]["doi"] = []
    elif kind == "bool":
        value["checks"]["doi"] = [1]
    elif kind == "reason":
        value["checks"]["orcid_reasons"] = ["private text"]
    else:
        value["private"] = "anything"
    with pytest.raises(ValueError):
        check_evidence(value, scope)


def test_scoped_mode_requires_explicit_configuration():
    with pytest.raises(ValueError):
        Settings(validator_scoped_authorities=True, _env_file=None)
    assert not Settings(_env_file=None).validator_scoped_authorities


def test_worker_scope_is_derived_from_tenant_records_and_result_bytes(
    client, db, session_factory, settings, monkeypatch
):
    from tests.test_phase7_v10_workflow import (
        test_v10_full_operational_flow_is_idempotent_auditable_and_ai_optional as workflow,
    )

    root = Path(__file__).resolve().parents[1]
    settings.validator_scoped_authorities = True
    settings.validator_socket = Path("/qualified-test.sock")
    settings.validator_registry_path = root / "config/validator-registry-vh1.json"
    settings.journal_profile_path = root / "profiles/esa-aop-1.1.json"
    seen = []

    def unavailable(self, candidate, specification):
        seen.append(
            (copy.deepcopy(self.scope), specification.name, hashlib.sha256(candidate).hexdigest())
        )
        return ValidationEngine().unavailable(
            specification.name,
            specification.version,
            candidate,
            "test-no-network",
            tool_sha256=specification.tool_sha256,
        )

    monkeypatch.setattr(ScopedValidatorExecutor, "__call__", unavailable)
    workflow(client, db, session_factory, settings, monkeypatch)
    assert len(seen) == 2
    assert seen[0][0] == seen[1][0]
    assert seen[0][0]["journal_profile_id"] == "esa-aop-1.1.0"
    assert seen[0][2] == seen[0][0]["xml_sha256"]
    assert seen[1][2] == seen[1][0]["package_sha256"]


@pytest.mark.parametrize("kind", ["source", "profile"])
def test_worker_rejects_snapshot_from_other_source_or_profile(settings, monkeypatch, kind):
    from idml_foundation import worker
    from idml_foundation.domain.canonical import CanonicalArticle

    scope, *_ = fixture()
    job = SimpleNamespace(
        organization_id=scope["organization_id"],
        payload={
            "resource_id": scope["resource_id"],
            "canonical_snapshot_id": scope["resource_id"],
        },
    )
    resource = SimpleNamespace(id=scope["resource_id"])
    source = SimpleNamespace(id="source", media_type="application/vnd.adobe.indesign-idml-package")
    pdf = SimpleNamespace(id="pdf", media_type="application/pdf")
    snapshot = SimpleNamespace(source_artifact_id="wrong" if kind == "source" else source.id)
    db = SimpleNamespace(scalar=lambda query: snapshot)
    monkeypatch.setattr(worker, "_tenant_resource", lambda *args: resource)
    monkeypatch.setattr(
        worker,
        "_tenant_artifact",
        lambda db, job, name: source if name == "idml_artifact_id" else pdf,
    )
    monkeypatch.setattr(
        worker,
        "load_snapshot",
        lambda snapshot: CanonicalArticle.model_construct(journal_profile_id="other-profile"),
    )
    with pytest.raises(worker.PermanentJobError, match="snapshot"):
        worker._build_package_job(db, job, settings)
