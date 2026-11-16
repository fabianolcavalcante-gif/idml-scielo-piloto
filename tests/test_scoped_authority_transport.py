import hashlib
import io
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile

import pytest

from idml_foundation.services.validation_scope import scope_digest, validate_scope
from ops.scoped_authority_transport import mount_selection, read_selection, stage_selection
from ops.scoped_validator_broker import select_spec

NOW = datetime.now(UTC)
ROOT = Path("/private/authorities")


def encoded(value):
    return json.dumps(value, sort_keys=True).encode()


def sha(value):
    return hashlib.sha256(value).hexdigest()


def fixture():
    xml = b"<article/>"
    stream = io.BytesIO()
    with ZipFile(stream, "w") as archive:
        archive.writestr("test.xml", xml)
    package = stream.getvalue()
    scope = {
        "organization_id": str(uuid4()),
        "resource_id": str(uuid4()),
        "source_idml_sha256": "1" * 64,
        "journal_profile_id": "esa-aop-1.1.0",
        "xml_sha256": sha(xml),
        "package_sha256": sha(package),
    }
    source = {
        "status": "available",
        "retrieved_at": NOW.isoformat(),
        "url": "https://example.test",
        "sha256": sha(b"{}"),
    }
    files = {
        "crossref.json": b"{}",
        "journal.json": b"{}",
        "doi-manifest.json": encoded(
            {
                "candidate_sha256": sha(xml),
                "package_sha256": sha(package),
                "snapshot_sha256": sha(b"{}"),
                "retrieved_at": NOW.isoformat(),
                "authority": "https://api.crossref.org/works/",
            }
        ),
        "editorial-manifest.json": encoded(
            {
                "candidate_sha256": sha(xml),
                "profile_id": scope["journal_profile_id"],
                "sources": {"journal": source},
            }
        ),
    }
    auth_id = str(uuid4())
    manifest = {
        "version": "validation-authority-bundle-1.0",
        "authorization_id": auth_id,
        "scope": scope,
        "files": {k: sha(v) for k, v in files.items()},
    }
    grant = {
        "version": "validation-authority-grant-1.0",
        "authorization_id": auth_id,
        "scope": scope,
        "bundle_sha256": sha(encoded(manifest)),
        "status": "active",
        "destination": "vps",
        "decision_id": str(uuid4()),
        "decision_sha256": "2" * 64,
        "issued_at": NOW.isoformat(),
        "expires_at": (NOW + timedelta(days=2)).isoformat(),
    }
    return scope, manifest, grant, files, xml, package


def reader_for(scope, manifest, grant, files):
    data = {
        ROOT / "authorizations" / (grant["authorization_id"] + ".json"): encoded(grant),
        ROOT / "bundles" / scope_digest(scope) / "manifest.json": encoded(manifest),
    }
    data.update({ROOT / "bundles" / scope_digest(scope) / k: v for k, v in files.items()})
    return lambda path, limit: data[path]


def test_scope_and_minimal_readonly_mounts(tmp_path):
    scope, manifest, grant, files, xml, _ = fixture()
    candidate = tmp_path / "candidate.xml"
    candidate.write_bytes(xml)
    folder, binding = stage_selection(
        ROOT,
        scope,
        candidate,
        "packtools",
        reader=reader_for(scope, manifest, grant, files),
        now=NOW,
    )
    assert binding["scope_sha256"] == scope_digest(scope)
    args = mount_selection(["docker", "--entrypoint=python", "image"], folder)
    assert len(list(folder.iterdir())) == 5
    assert not any("authorizations" in a for a in args)
    assert all(a.endswith("readonly") for a in args if a.startswith("type=bind"))


@pytest.mark.parametrize(
    "field",
    ["organization_id", "resource_id", "source_idml_sha256", "xml_sha256", "package_sha256"],
)
def test_other_scope_never_selects_authority(field):
    scope, manifest, grant, files, _, _ = fixture()
    changed = dict(scope)
    changed[field] = str(uuid4()) if field.endswith("_id") else "f" * 64
    with pytest.raises((KeyError, ValueError)):
        read_selection(ROOT, changed, reader=reader_for(scope, manifest, grant, files), now=NOW)


@pytest.mark.parametrize(
    "change",
    ["revoked", "expired", "future", "long", "destination", "scope", "bundle", "extra", "decision"],
)
def test_invalid_authorization_fails_closed(change):
    scope, manifest, grant, files, _, _ = fixture()
    if change == "revoked":
        grant["status"] = "revoked"
    elif change in {"expired", "long"}:
        grant["expires_at"] = (NOW + timedelta(days=-1 if change == "expired" else 31)).isoformat()
    elif change == "future":
        grant["issued_at"] = (NOW + timedelta(days=1)).isoformat()
    elif change == "destination":
        grant["destination"] = "local"
    elif change == "scope":
        grant["scope"] = {**scope, "resource_id": str(uuid4())}
    elif change == "bundle":
        grant["bundle_sha256"] = "f" * 64
    elif change == "decision":
        grant["decision_sha256"] = "invalid"
    else:
        grant["allow_anything"] = True
    with pytest.raises(ValueError):
        read_selection(ROOT, scope, reader=reader_for(scope, manifest, grant, files), now=NOW)


@pytest.mark.parametrize("change", ["snapshot", "expired_snapshot", "xml", "package", "traversal"])
def test_source_and_candidate_tampering(tmp_path, change):
    scope, manifest, grant, files, xml, package = fixture()
    if change == "snapshot":
        files["journal.json"] = b"tampered"
    elif change == "expired_snapshot":
        doi = json.loads(files["doi-manifest.json"])
        doi["retrieved_at"] = (NOW - timedelta(days=8)).isoformat()
        files["doi-manifest.json"] = encoded(doi)
        manifest["files"]["doi-manifest.json"] = sha(files["doi-manifest.json"])
        grant["bundle_sha256"] = sha(encoded(manifest))
    elif change == "traversal":
        manifest["files"]["../secret"] = "f" * 64
        grant["bundle_sha256"] = sha(encoded(manifest))
    candidate = tmp_path / ("candidate.zip" if change == "package" else "candidate.xml")
    candidate.write_bytes(
        package + b"changed" if change == "package" else b"changed" if change == "xml" else xml
    )
    with pytest.raises(ValueError):
        stage_selection(
            ROOT,
            scope,
            candidate,
            "spsvalidator" if change == "package" else "packtools",
            reader=reader_for(scope, manifest, grant, files),
            now=NOW,
        )


def test_broker_v1_cannot_downgrade_and_client_cannot_choose_paths():
    from tests.test_validator_transport import request

    registry, req = request()
    with pytest.raises(ValueError):
        select_spec(registry, req)
    scope, *_ = fixture()
    req.update(version="local-validator-1.1", scope=scope, candidate_sha256=scope["xml_sha256"])
    registry["authority_root"] = str(ROOT)
    spec = select_spec(registry, req)
    assert spec["_scope"] == scope
    req["authority_root"] = "/user/chosen"
    with pytest.raises(ValueError):
        select_spec(registry, req)


def test_scope_shape_rejects_extra_paths_and_unqualified_profile():
    scope, *_ = fixture()
    with pytest.raises(ValueError):
        validate_scope({**scope, "path": "/private"})
    with pytest.raises(ValueError):
        validate_scope({**scope, "journal_profile_id": "esa-aop-1.0.0"})


def test_revocation_during_execution_discards_output(tmp_path, monkeypatch):
    from ops import scoped_validator_broker as broker

    scope, *_ = fixture()
    binding = {
        "scope_sha256": scope_digest(scope),
        "bundle_sha256": "a" * 64,
        "grant_sha256": "b" * 64,
    }
    monkeypatch.setattr(broker, "stage_selection", lambda *args: (tmp_path, binding))
    monkeypatch.setattr(
        broker,
        "LEGACY_EXECUTE",
        lambda *args: encoded({"result": {"authority_evidence": {"binding": binding}}}),
    )

    def revoked(*args):
        raise ValueError("scoped_authority_grant_invalid")

    monkeypatch.setattr(broker, "load_selection", revoked)
    original = broker.legacy.create_arguments
    with pytest.raises(ValueError, match="grant_invalid"):
        broker.execute(
            {"_authority_root": str(ROOT), "_scope": scope, "name": "packtools"},
            tmp_path / "candidate.xml",
            tmp_path,
        )
    assert broker.legacy.create_arguments is original
