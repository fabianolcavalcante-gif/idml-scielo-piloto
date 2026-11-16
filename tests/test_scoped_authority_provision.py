import json
from pathlib import Path

import pytest

from ops import provision_scoped_authorities as installer
from ops import scoped_authority_transport as transport
from tests.test_scoped_authority_transport import encoded, fixture, sha


def prepare(tmp_path, monkeypatch):
    _scope, manifest, grant, files, xml, package = fixture()
    root, bundle = tmp_path / "root", tmp_path / "incoming"
    (root / "authorizations").mkdir(parents=True)
    bundle.mkdir()
    (bundle / "manifest.json").write_bytes(encoded(manifest))
    for name, data in files.items():
        (bundle / name).write_bytes(data)
    grant_path = root / "authorizations" / (grant["authorization_id"] + ".json")
    grant_path.write_bytes(encoded(grant))
    xml_path, zip_path = tmp_path / "input.xml", tmp_path / "input.zip"
    xml_path.write_bytes(xml)
    zip_path.write_bytes(package)

    def reader(path, limit):
        data = Path(path).read_bytes()
        if not 0 < len(data) <= limit:
            raise ValueError("budget")
        return data

    read_original, stage_original = transport.read_selection, installer.stage_selection
    monkeypatch.setattr(installer, "trusted_read", reader)
    monkeypatch.setattr(
        transport,
        "read_selection",
        lambda root, scope, **kwargs: read_original(
            root, scope, reader=reader, now=kwargs.get("now")
        ),
    )
    monkeypatch.setattr(
        installer, "stage_selection", lambda *args: stage_original(*args, reader=reader)
    )
    return root, bundle, xml_path, zip_path, grant_path, manifest


def test_installer_requires_grant_and_is_atomic_and_non_overwriting(tmp_path, monkeypatch):
    root, bundle, xml, package, grant, manifest = prepare(tmp_path, monkeypatch)
    result = installer.provision(root, bundle, xml, package)
    target = root / "bundles" / result["scope_sha256"]
    assert json.loads((target / "manifest.json").read_bytes()) == manifest
    original = grant.read_bytes()
    with pytest.raises(ValueError, match="already_exists"):
        installer.provision(root, bundle, xml, package)
    assert grant.read_bytes() == original
    assert not list(root.glob("provision-*"))
    assert not (root / ".provision.lock").exists()


@pytest.mark.parametrize("kind", ["missing_grant", "revoked", "tampered", "escape", "locked"])
def test_installer_never_publishes_partial_or_unauthorized_bundle(tmp_path, monkeypatch, kind):
    root, bundle, xml, package, grant, manifest = prepare(tmp_path, monkeypatch)
    if kind == "missing_grant":
        grant.unlink()
    elif kind == "revoked":
        value = json.loads(grant.read_bytes())
        value["status"] = "revoked"
        grant.write_bytes(encoded(value))
    elif kind == "tampered":
        (bundle / "journal.json").write_bytes(b"changed")
    elif kind == "escape":
        manifest["files"]["../secret"] = "0" * 64
        (bundle / "manifest.json").write_bytes(encoded(manifest))
        value = json.loads(grant.read_bytes())
        value["bundle_sha256"] = sha(encoded(manifest))
        grant.write_bytes(encoded(value))
    else:
        (root / ".provision.lock").write_bytes(b"existing admin transaction")
    with pytest.raises((ValueError, OSError)):
        installer.provision(root, bundle, xml, package)
    assert not list((root / "bundles").glob("*/manifest.json"))
    assert not list(root.glob("provision-*"))
