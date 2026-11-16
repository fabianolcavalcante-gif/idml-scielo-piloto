"""Freeze/check a content-free VH1 laboratory baseline; not a deployment approval."""

import argparse
import hashlib
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from idml_foundation.domain.corpus import load_manifest
from idml_foundation.pipeline.profile import load_profile
from idml_foundation.pipeline.service import DeterministicPipeline
from idml_foundation.release.package_builder import AssetPayload, PackageBuilder
from idml_foundation.release.validator_registry import ValidatorChannel, load_validator_registry
from idml_foundation.services.enrichment import KINDS
from ops.build_h1_real_packages import figure_paths
from ops.gate_phase7_7c06 import _single_artifact
from ops.inventory_homologation import inventory
from ops.vh1_runtime_inventory import digest, runtime_inventory

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = "config/validator-registry-vh1.json"
PROFILE = "profiles/esa-aop-1.1.json"
EXTRA_TREES = ("ops", "vendor/jats/1.3", "deploy")


def source_inventory(root):
    files = inventory(root)["sha256"]
    paths = [root / REGISTRY, root / "requirements-dev.lock"]
    for name in EXTRA_TREES:
        paths.extend(
            p
            for p in (root / name).rglob("*")
            if p.is_file()
            and "__pycache__" not in p.parts
            and (
                p.suffix in {".py", ".dtd", ".ent", ".mod", ".xsd", ".yml", ".sh"}
                or p.name.startswith("Dockerfile")
            )
        )
    for path in paths:
        if any(p.is_symlink() or p.is_junction() for p in (path, *path.parents)):
            raise ValueError("unsafe_baseline_source")
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("unsafe_baseline_source")
        files[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"sha256": dict(sorted(files.items())), "fingerprint": digest(files)}


def same_runtime(expected, actual):
    # Tool/image, Python, dependencies, native rules and wrappers all participate.
    if expected != actual:
        raise ValueError("vh1_runtime_mismatch")


def remote_runtime(ssh_prefix, artifact):
    image = artifact.image_id
    if not image or not re.fullmatch(r"sha256:[0-9a-f]{64}", image):
        raise ValueError("pinned_image_required")
    inspect = subprocess.run(  # noqa: S603 - fixed command, validated immutable image ID
        [*ssh_prefix, f"docker image inspect {image} --format '{{{{.Id}}}}'"],
        capture_output=True,
        timeout=30,
        check=True,
    )
    if inspect.stdout.decode().strip() != image:
        raise ValueError("image_identity_mismatch")
    command = (
        "docker run --rm -i --network none --read-only --user 10001:10001 "
        "--memory 192m --memory-swap 192m --cpus 0.25 --pids-limit 64 --cap-drop ALL "
        f"--security-opt no-new-privileges --entrypoint python {image} -"
    )
    result = subprocess.run(  # noqa: S603 - fixed sandbox with allowlisted stdin program
        [*ssh_prefix, command],
        input=(ROOT / "ops/vh1_runtime_inventory.py").read_bytes(),
        capture_output=True,
        timeout=60,
        check=True,
    )
    return {"image_id": image, "runtime": json.loads(result.stdout)}


def real_conversion_evidence(root):
    # Local authorized development corpus; no gold, network, copying or package modification.
    cases = (
        ("esa-e20240086", "tmp/sample/ESA_2024086_AOP.idml"),
        ("esa-e20240135", "tmp/ARQUIVOS TESTE/ESA_2024135_AOP.idml"),
    )
    profile = load_profile(root / PROFILE)
    rows = []
    for case, name in cases:
        source = root / name
        data = source.read_bytes()
        folder = root / "benchmarks/private/output/h1-country-codes-v1" / case
        catalogs, hashes = {}, {}
        for kind, contract in KINDS.items():
            path = folder / f"{kind}.json"
            if path.exists():
                raw = path.read_bytes()
                catalogs[kind] = contract.model_validate_json(raw)
                hashes[kind] = hashlib.sha256(raw).hexdigest()
        if not catalogs:
            raise ValueError("qualified_catalogs_missing")
        results = [
            DeterministicPipeline(profile=profile, **catalogs).run(data, logical_name=source.name)
            for _ in range(2)
        ]
        if results[0].xml != results[1].xml or results[0].validation != results[1].validation:
            raise ValueError("non_deterministic_conversion")
        manifest = load_manifest(root / f"corpus/manifests/{case}.json")
        builder = PackageBuilder()
        files = builder.scielo_files(
            package_stem=profile.package_stem(results[0].canonical.article_id),
            xml=results[0].xml,
            pdf=_single_artifact(source.parent, manifest, "approved_pdf_reference").read_bytes(),
            assets=tuple(
                AssetPayload(source_name=p.name, data=p.read_bytes())
                for p in figure_paths(source.parent, manifest)
            ),
        )
        # Compare the same stage: the packager normalizes asset names in the final XML.
        final_xml = files[0].data
        if final_xml != (folder / "candidate.xml").read_bytes():
            raise ValueError("historical_xml_changed")
        package_args = dict(
            article_id=results[0].canonical.article_id,
            profile_id=profile.profile_id,
            source_idml_sha256=hashlib.sha256(data).hexdigest(),
            files=files,
            validator_versions={},
        )
        package = builder.build(**package_args)
        if (
            package.archive != builder.build(**package_args).archive
            or package.archive != (folder / "candidate.zip").read_bytes()
        ):
            raise ValueError("historical_package_changed")
        rows.append(
            {
                "case": case,
                "source_sha256": hashlib.sha256(data).hexdigest(),
                "catalog_sha256": hashes,
                "xml_sha256": hashlib.sha256(final_xml).hexdigest(),
                "package_sha256": package.package_sha256,
                "same_package_twice": True,
                "same_xml_and_offline_rules_twice": True,
                "offline_valid": results[0].validation.valid,
                "external_validation_repeated": False,
            }
        )
    return rows


def build(ssh_prefix):
    registry = load_validator_registry(ROOT / REGISTRY)
    profile = load_profile(ROOT / PROFILE)
    validators = {
        name: remote_runtime(ssh_prefix, registry.select(name, ValidatorChannel.ACTIVE))
        for name in ("packtools", "spsvalidator")
    }
    return {
        "version": "vh1-lot1-baseline-1.0",
        "created_at": datetime.now(UTC).isoformat(),
        "scope": "laboratory-baseline-not-release",
        "source": source_inventory(ROOT),
        "profile": {
            "path": PROFILE,
            "id": profile.profile_id,
            "sha256": hashlib.sha256((ROOT / PROFILE).read_bytes()).hexdigest(),
        },
        "registry": {
            "path": REGISTRY,
            "sha256": hashlib.sha256((ROOT / REGISTRY).read_bytes()).hexdigest(),
        },
        "validators": validators,
        "conversion_runtime": runtime_inventory(),
        "conversion_evidence": real_conversion_evidence(ROOT),
        "native_packtools_versions_equal": (
            validators["packtools"]["runtime"]["package_trees"]["packtools"]
            == validators["spsvalidator"]["runtime"]["package_trees"]["packtools"]
        ),
        "xpm": {"status": "blocked", "policy_waived": False},
        "application_image": None,
        "deployed": False,
        "ready_for_expert": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ssh-key", type=Path, required=True)
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, default=22022)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-zA-Z0-9_.@-]+", args.host) or args.host.startswith("-"):
        raise ValueError("invalid_host")
    prefix = [
        "ssh",
        "-i",
        str(args.ssh_key),
        "-p",
        str(args.port),
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=15",
        args.host,
    ]
    try:
        result = build(prefix)
    except Exception as error:
        # Catalog/pipeline diagnostics may contain private text; emit only a safe failure type.
        print(json.dumps({"baseline_verified": False, "failure_type": type(error).__name__}))
        return 1
    if args.check:
        expected = json.loads(args.output.read_text(encoding="utf-8"))
        for key in (
            "source",
            "profile",
            "registry",
            "validators",
            "conversion_runtime",
            "conversion_evidence",
        ):
            same_runtime(expected[key], result[key])
    else:
        # Evidence snapshots must never overwrite an earlier qualification.
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "baseline_verified": True,
                "cases": len(result["conversion_evidence"]),
                "source_fingerprint": result["source"]["fingerprint"],
                "deployed": False,
                "ready_for_expert": False,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
