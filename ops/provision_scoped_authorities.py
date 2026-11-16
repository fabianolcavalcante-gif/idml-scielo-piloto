"""Admin-only atomic installation. A preinstalled, active grant is mandatory."""

import argparse
import json
import os
import tempfile
from pathlib import Path
from uuid import UUID

try:
    from ops.scoped_authority_transport import scope_digest, stage_selection, trusted_read
except ModuleNotFoundError:
    from scoped_authority_transport import scope_digest, stage_selection, trusted_read


def provision(root, bundle, xml, package):
    root, bundle = Path(root), Path(bundle)
    raw = trusted_read(bundle / "manifest.json", 32 * 1024)
    manifest = json.loads(raw)
    key = scope_digest(manifest["scope"])
    if str(UUID(manifest["authorization_id"])) != manifest["authorization_id"]:
        raise ValueError("scoped_authorization_id_invalid")
    # Read the real authorization before staging; never create or renew consent here.
    grant_path = root / "authorizations" / (manifest["authorization_id"] + ".json")
    grant = trusted_read(grant_path, 16 * 1024)
    target = root / "bundles" / key
    if target.exists() or target.is_symlink():
        raise ValueError("scoped_bundle_already_exists")
    with tempfile.TemporaryDirectory(prefix="provision-", dir=root) as temporary:
        staging = Path(temporary)
        (staging / "authorizations").mkdir(mode=0o700)
        (staging / "authorizations" / grant_path.name).write_bytes(grant)
        destination = staging / "bundles" / key
        destination.mkdir(parents=True, mode=0o700)
        # Validate the names/hashes/grant before copying any source-selected file.
        (destination / "manifest.json").write_bytes(raw)
        try:
            from ops.scoped_authority_transport import read_selection
        except ModuleNotFoundError:
            from scoped_authority_transport import read_selection
        read_selection(staging, manifest["scope"])
        for name in manifest["files"]:
            (destination / name).write_bytes(trusted_read(bundle / name, 10 * 1024**2))
        for path, validator in ((Path(xml), "packtools"), (Path(package), "spsvalidator")):
            check = staging / validator
            check.mkdir(mode=0o700)
            candidate = check / path.name
            candidate.write_bytes(trusted_read(path, 100 * 1024**2))
            stage_selection(staging, manifest["scope"], candidate, validator)
        # Reject a revocation or replacement occurring during preparation.
        if trusted_read(grant_path, 16 * 1024) != grant:
            raise ValueError("scoped_grant_changed_during_provision")
        for path in destination.iterdir():
            path.chmod(0o600)
        (root / "bundles").mkdir(mode=0o700, exist_ok=True)
        # Serial admin operation, with an exclusive publication lock; no overwrite.
        descriptor = os.open(root / ".provision.lock", os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            if target.exists() or target.is_symlink():
                raise ValueError("scoped_bundle_already_exists")
            destination.rename(target)
        finally:
            os.close(descriptor)
            (root / ".provision.lock").unlink()
    return {"scope_sha256": key, "installed": True}


def main():
    parser = argparse.ArgumentParser()
    for name in ("root", "bundle", "xml", "package"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(provision(args.root, args.bundle, args.xml, args.package)))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("scoped_authority_provision_failed") from None
