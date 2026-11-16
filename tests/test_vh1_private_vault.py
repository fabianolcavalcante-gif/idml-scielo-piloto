import hashlib
import json

import pytest

from ops.verify_vh1_private_vault import safe_name, verify


@pytest.mark.parametrize("name", ["../escape", "/absolute", "case/../../secret", "C:/file", "a\\b"])
def test_vault_path_cannot_escape(name):
    with pytest.raises(ValueError, match="unsafe_vault_name"):
        safe_name(name)


def setup_vault(folder):
    folder.mkdir()
    payload = b'{"synthetic":true}'
    (folder / "catalog.json").write_bytes(payload)
    manifest = {
        "version": "vh1-source-vault-1.0",
        "runtime_activated": False,
        "decision_sha256": "a" * 64,
        "files": {
            "catalog.json": {"bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}
        },
    }
    raw = json.dumps(manifest).encode()
    (folder / "manifest.json").write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def test_verifier_accepts_only_exact_inventory(tmp_path):
    folder = tmp_path / "vault"
    digest = setup_vault(folder)
    assert verify(folder, digest)["files"] == 1
    (folder / "extra.json").write_text("{}")
    with pytest.raises(ValueError, match="vault_file_set_mismatch"):
        verify(folder, digest)


def test_verifier_rejects_modified_content(tmp_path):
    folder = tmp_path / "vault"
    digest = setup_vault(folder)
    path = folder / "catalog.json"
    path.write_bytes(b"x" * path.stat().st_size)
    with pytest.raises(ValueError, match="vault_hash_mismatch"):
        verify(folder, digest)


def test_verifier_rejects_wrong_manifest_hash(tmp_path):
    folder = tmp_path / "vault"
    setup_vault(folder)
    with pytest.raises(ValueError, match="vault_manifest_mismatch"):
        verify(folder, "0" * 64)
