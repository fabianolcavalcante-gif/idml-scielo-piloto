"""VPS-side verification/promotion of an SCP staging folder; stdlib, host Python 3.10."""

import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path, PurePosixPath

VAULT = Path("/opt/idml-platform/private/source-vault")


def safe_name(name):
    parts = PurePosixPath(name).parts
    if (
        not parts
        or PurePosixPath(name).is_absolute()
        or len(parts) > 4
        or any(not re.fullmatch(r"[A-Za-z0-9_-]+(?:\.(?:json|xml|zip|md))?", p) for p in parts)
        or any(p in {".", ".."} for p in parts)
        or "\\" in name
    ):
        raise ValueError("unsafe_vault_name")
    return parts


def verify(folder, digest):
    if not re.fullmatch(r"[0-9a-f]{64}", digest) or folder.is_symlink():
        raise ValueError("invalid_vault_identity")
    manifest_path = folder / "manifest.json"
    if manifest_path.is_symlink() or manifest_path.stat().st_size > 65536:
        raise ValueError("invalid_vault_manifest")
    raw = manifest_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("vault_manifest_mismatch")
    manifest = json.loads(raw)
    if (
        manifest.get("version") != "vh1-source-vault-1.0"
        or manifest.get("runtime_activated") is not False
        or not 1 <= len(manifest.get("files", {})) <= 30
    ):
        raise ValueError("invalid_vault_manifest")
    expected = {"manifest.json", *manifest["files"]}
    actual = set()
    size = 0
    for path in folder.rglob("*"):
        mode = path.lstat().st_mode
        if not stat.S_ISREG(mode) and not stat.S_ISDIR(mode):
            raise ValueError("vault_special_file")
        if path.is_file():
            actual.add(path.relative_to(folder).as_posix())
    if actual != expected:
        raise ValueError("vault_file_set_mismatch")
    for name, spec in manifest["files"].items():
        path = folder.joinpath(*safe_name(name))
        if path.stat().st_size != spec["bytes"] or not 0 < spec["bytes"] <= 100 * 1024**2:
            raise ValueError("vault_size_mismatch")
        size += spec["bytes"]
        if size > 200 * 1024**2:
            raise ValueError("vault_total_budget")
        if hashlib.sha256(path.read_bytes()).hexdigest() != spec["sha256"]:
            raise ValueError("vault_hash_mismatch")
    return {
        "files": len(manifest["files"]),
        "bytes": size,
        "decision_sha256": manifest["decision_sha256"],
        "manifest_sha256": digest,
    }


def main():
    try:
        digest = sys.argv[1]
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("invalid_vault_identity")
        for path in (VAULT, VAULT.parent):
            info = path.lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o077:
                raise ValueError("unsafe_vault_root")
        if VAULT.resolve() != VAULT:
            raise ValueError("unsafe_vault_root")
        folder = VAULT / ("incoming-" + digest)
        target = VAULT / digest
        if target.exists():
            evidence = verify(target, digest)
        else:
            evidence = verify(folder, digest)
            # Only this verified, newly staged tree is touched, never the application tree.
            for path in (folder, *folder.rglob("*")):
                if path.stat().st_uid != 0:
                    raise ValueError("unexpected_vault_owner")
                path.chmod(0o700 if path.is_dir() else 0o600)
            folder.rename(target)
        evidence.update(
            {
                "vps_path": str(target),
                "verified": True,
                "runtime_activated": False,
                "publicly_exposed": False,
            }
        )
        print(json.dumps(evidence))
        return 0
    except Exception as error:
        print(json.dumps({"verified": False, "failure_type": type(error).__name__}))
        return 1


if __name__ == "__main__":
    os.umask(0o077)
    raise SystemExit(main())
