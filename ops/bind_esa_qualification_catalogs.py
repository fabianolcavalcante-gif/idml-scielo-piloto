"""Install development catalogs for the two approved ESA inputs in an explicit article scope."""

import argparse
import hashlib
import json
import os
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

from idml_foundation.services.enrichment import CatalogBundle, bundle_path, select_enrichment
from idml_foundation.services.source_authorization import SourceAuthorization
from idml_foundation.settings import Settings
from ops.provision_enrichment import provision

SOURCES = {
    "esa-e20240086": "8ce185f5dd03f5403a36ca7b60d9d708b95e2b334e731327dd0b568b0cd44d2c",
    "esa-e20240135": "48c5c693d0e1a3f5fa597811fc861fccf21b987956340966552bbefec0175574",
}


def install(case, org, resource, expected_material, decision_sha):
    root = Path("/runtime")
    folder = Path("/material") / case
    material = (folder / "material.json").read_bytes()
    if hashlib.sha256(material).hexdigest() != expected_material:
        raise ValueError("material_identity_mismatch")
    m = json.loads(material)
    source = SOURCES[case]
    assert m["source_idml_sha256"] == source and m["profile_id"] == "esa-aop-1.1.0"
    scope = dict(
        organization_id=str(UUID(org)),
        resource_id=str(UUID(resource)),
        source_idml_sha256=source,
        profile_id=m["profile_id"],
    )
    settings = Settings(enrichment_root=root, enrichment_location="vps")
    hashes = {k: v["catalog_sha256"] for k, v in m["catalogs"].items()}
    target = root / bundle_path(org, resource, source)
    if target.exists():
        selected = select_enrichment(
            settings,
            organization_id=org,
            resource_id=resource,
            source_sha256=source,
            profile_id=m["profile_id"],
        )
        assert selected.provenance["catalog_sha256"] == hashes
        return selected.provenance
    now = datetime.now(UTC)
    grant = SourceAuthorization.model_validate(
        dict(
            version="source-authorization-1.0",
            authorization_id=uuid4(),
            destination="vps",
            status="active",
            decision_id=uuid4(),
            decision_sha256=decision_sha,
            issued_at=now,
            expires_at=now + timedelta(days=2),
            catalogs=m["catalogs"],
            **scope,
        )
    )
    manifest = CatalogBundle(
        version="enrichment-bundle-1.1",
        authorization_id=grant.authorization_id,
        catalogs=hashes,
        **scope,
    )
    auth = root / "authorizations" / (str(grant.authorization_id) + ".json")
    os.umask(0o027)
    # Setgid on the private directory grants read access to the worker at atomic promotion.
    assert root.stat().st_gid == 10001
    root.chmod(0o2750)
    with tempfile.TemporaryDirectory() as tmp:
        incoming = Path(tmp)
        (incoming / "manifest.json").write_text(manifest.model_dump_json())
        for kind in hashes:
            if kind not in grant.catalogs or not kind.isidentifier():
                raise ValueError("unexpected_kind")
            (incoming / (kind + ".json")).write_bytes((folder / (kind + ".json")).read_bytes())
        with auth.open("x") as stream:
            stream.write(grant.model_dump_json())
        try:
            os.chown(auth, 0, 10001)
            auth.chmod(0o640)
            return provision(settings, incoming)
        except Exception:
            auth.unlink()
            raise


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for key in ("case", "org", "resource", "material_sha", "decision_sha"):
        p.add_argument(key)
    a = p.parse_args()
    print(json.dumps(install(a.case, a.org, a.resource, a.material_sha, a.decision_sha)))
