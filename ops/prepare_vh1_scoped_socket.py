"""Build a private lab-only bundle. UUIDs are synthetic, not production tenant grants."""

import hashlib
import json
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from idml_foundation.release.validator_registry import load_validator_registry
from idml_foundation.services.validation_scope import scope_digest

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    "validator_broker.py": "ops/validator_broker.py",
    "scoped_validator_broker.py": "ops/scoped_validator_broker.py",
    "scoped_authority_transport.py": "ops/scoped_authority_transport.py",
    "doi_authority_transport.py": "ops/doi_authority_transport.py",
    "doi_package_binding.py": "ops/doi_package_binding.py",
    "validation_scope.py": "src/idml_foundation/services/validation_scope.py",
    "validator_transport.py": "src/idml_foundation/services/validator_transport.py",
    "scoped_validator_transport.py": "src/idml_foundation/services/scoped_validator_transport.py",
    "package_validation.py": "src/idml_foundation/services/package_validation.py",
    "validation_engine.py": "src/idml_foundation/release/validation_engine.py",
    "validator_registry.py": "src/idml_foundation/release/validator_registry.py",
    "provision_scoped_authorities.py": "ops/provision_scoped_authorities.py",
    "probe_scoped_socket.py": "ops/probe_scoped_socket.py",
    "run_vh1_scoped_socket.py": "ops/run_vh1_scoped_socket.py",
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")


def main():
    now = datetime.now(UTC)
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    output = ROOT / "benchmarks/private/output" / ("vh1-scoped-socket-" + run_id)
    output.mkdir(exist_ok=False)
    report = {
        "synthetic_scopes_only": True,
        "created_at": now.isoformat(),
        "cases": {},
        "code_sha256": {name: digest((ROOT / path).read_bytes()) for name, path in SOURCES.items()},
    }
    for name, source in SOURCES.items():
        shutil.copyfile(ROOT / source, output / name)
    registry = ROOT / "config/validator-registry-vh1-scoped.json"
    load_validator_registry(registry)
    shutil.copyfile(registry, output / "registry.json")
    report["registry_sha256"] = digest(registry.read_bytes())
    vault = (
        ROOT
        / "benchmarks/private/output"
        / "incoming-25ca4293d4e180ad32b7751b50fd30cd0f66ace056ff7226cddf01640b69b1e8"
    )
    for case, source_sha in (
        ("esa-e20240086", "8ce185f5dd03f5403a36ca7b60d9d708b95e2b334e731327dd0b568b0cd44d2c"),
        ("esa-e20240135", "48c5c693d0e1a3f5fa597811fc861fccf21b987956340966552bbefec0175574"),
    ):
        folder = output / case
        folder.mkdir()
        source = vault / case
        editorial = ROOT / "benchmarks/private/output/vh1-editorial/20261001T214623Z" / case
        scope = {
            "organization_id": str(uuid5(NAMESPACE_URL, "idml:vh1:socket:LAB_ONLY")),
            "resource_id": str(uuid5(NAMESPACE_URL, "idml:vh1:socket:LAB_ONLY:" + case)),
            "source_idml_sha256": source_sha,
            "journal_profile_id": "esa-aop-1.1.0",
            "xml_sha256": digest((source / "candidate.xml").read_bytes()),
            "package_sha256": digest((source / "candidate.zip").read_bytes()),
        }
        write_json(folder / "scope.json", scope)
        incoming = folder / "incoming"
        incoming.mkdir()
        shutil.copyfile(source / "authority/crossref.json", incoming / "crossref.json")
        shutil.copyfile(source / "authority/manifest.json", incoming / "doi-manifest.json")
        for item in editorial.iterdir():
            if item.suffix == ".json":
                shutil.copyfile(
                    item,
                    incoming
                    / ("editorial-manifest.json" if item.name == "manifest.json" else item.name),
                )
        grant_id = str(uuid5(NAMESPACE_URL, "idml:vh1:lab-grant:" + case + run_id))
        manifest = {
            "version": "validation-authority-bundle-1.0",
            "authorization_id": grant_id,
            "scope": scope,
            "files": {p.name: digest(p.read_bytes()) for p in incoming.iterdir()},
        }
        write_json(incoming / "manifest.json", manifest)
        grant = {
            "version": "validation-authority-grant-1.0",
            "authorization_id": grant_id,
            "scope": scope,
            "bundle_sha256": digest((incoming / "manifest.json").read_bytes()),
            "status": "active",
            "destination": "vps",
            "decision_id": str(uuid5(NAMESPACE_URL, "idml:vh1:owner-storage-decision:20261001")),
            "decision_sha256": digest(
                (ROOT / "docs/authorizations/VH1_VPS_DATA_20261001.md").read_bytes()
            ),
            "issued_at": now.isoformat(),
            "expires_at": (now + timedelta(days=1)).isoformat(),
        }
        write_json(folder / "grant.json", grant)
        report["cases"][case] = {
            "scope_sha256": scope_digest(scope),
            "files": {
                p.relative_to(folder).as_posix(): digest(p.read_bytes())
                for p in folder.rglob("*.json")
            },
        }
    write_json(output / "plan.json", report)
    print(
        json.dumps(
            {"output": str(output), "plan_sha256": digest((output / "plan.json").read_bytes())}
        )
    )


if __name__ == "__main__":
    main()
