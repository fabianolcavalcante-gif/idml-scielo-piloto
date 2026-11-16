"""Admin-only local install. Grants must already exist; never creates consent or contacts VPS."""

import argparse
import json
import tempfile
from pathlib import Path

from idml_foundation.services.enrichment import (
    KINDS,
    CatalogBundle,
    _read,
    bundle_path,
    select_enrichment,
)
from idml_foundation.settings import Settings


def provision(settings: Settings, incoming: Path) -> dict:
    root = settings.enrichment_root
    if root is None or not root.is_dir():
        raise ValueError("enrichment_provision_invalid")
    try:
        # The caller supplies an operator-controlled directory, not a path from a job.
        if any(p.is_symlink() or p.is_junction() for p in (incoming, *incoming.absolute().parents)):
            raise ValueError("unsafe incoming path")
        if any(p.is_symlink() or p.is_junction() for p in (root, *root.absolute().parents)):
            raise ValueError("unsafe target path")
        raw = _read(incoming, Path("manifest.json"), 16 * 1024)
        manifest = CatalogBundle.model_validate_json(raw)
        scope = bundle_path(
            manifest.organization_id, manifest.resource_id, manifest.source_idml_sha256
        )
        target = root / scope
        if target.exists() or target.is_symlink():
            raise ValueError("existing bundle must not be overwritten")
        authorization_path = Path("authorizations") / f"{manifest.authorization_id}.json"
        grant = _read(root, authorization_path, 16 * 1024)
        with tempfile.TemporaryDirectory(prefix=".provision-", dir=root) as temporary:
            stage = Path(temporary)
            folder = stage / scope
            folder.mkdir()
            (stage / "authorizations").mkdir()
            (stage / authorization_path).write_bytes(grant)
            (folder / "manifest.json").write_bytes(raw)
            # Only known catalog filenames; select_enrichment checks kinds and full contracts.
            if not set(manifest.catalogs) <= KINDS.keys():
                raise ValueError("unsupported catalog")
            for kind in manifest.catalogs:
                (folder / f"{kind}.json").write_bytes(
                    _read(incoming, Path(f"{kind}.json"), 8 * 1024**2)
                )
            selected = select_enrichment(
                settings.model_copy(update={"enrichment_root": stage}),
                organization_id=manifest.organization_id,
                resource_id=manifest.resource_id,
                source_sha256=manifest.source_idml_sha256,
                profile_id=manifest.profile_id,
            )
            # Recheck revocation/change immediately before atomic same-filesystem promotion.
            if _read(root, authorization_path, 16 * 1024) != grant:
                raise ValueError("authorization changed")
            folder.rename(target)
            return {**selected.provenance, "status": "provisioned"}
    except (OSError, ValueError):
        raise ValueError("enrichment_provision_invalid") from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--incoming", type=Path, required=True)
    parser.add_argument("--location", choices=("local", "vps"), required=True)
    args = parser.parse_args()
    try:
        result = provision(
            Settings(enrichment_root=args.root, enrichment_location=args.location), args.incoming
        )
    except ValueError:
        print(json.dumps({"status": "rejected", "code": "enrichment_provision_invalid"}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
