"""Verify immutable Linux images and native contraprobes before staging a registry."""

import copy
import hashlib
import json
import subprocess
from pathlib import Path

from idml_foundation.release.validator_registry import ValidatorArtifact
from ops.prepare_vh1_history_images import FILES
from ops.vh1_baseline import remote_runtime

ROOT = Path(__file__).resolve().parents[1]
IMAGES = {
    "packtools": "sha256:4d5aadab7d75822c778890e1704e0533d9fc0578aed87034b128f20ec6da2eca",
    "spsvalidator": "sha256:61b90cc8ecca8de508c6cd19701551860de32f053a4899fd056835c8f05ab048",
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, indent=2)


def main():
    original = json.loads((ROOT / "config/validator-registry-vh1-scoped.json").read_bytes())
    baseline = json.loads(
        (ROOT / "benchmarks/qualification/reports/vh1-scoped-images-v1.json").read_bytes()
    )
    registry = copy.deepcopy(original)
    ssh = [
        "ssh",
        "-i",
        str(Path.home() / ".ssh/mapalead_vps_ed25519"),
        "-p",
        "22022",
        "-o",
        "BatchMode=yes",
        "root@143.95.214.8",
    ]
    reports = {}
    for name, image in IMAGES.items():
        active = next(
            v for v in registry["validators"] if v["name"] == name and v["channel"] == "active"
        )
        parent = copy.deepcopy(active)
        active.update(image_id=image, dockerfile="deploy/Dockerfile.validator-history-compat")
        result = remote_runtime(ssh, ValidatorArtifact.model_validate(active))
        if (
            result["runtime"]["package_trees"]
            != baseline["validators"][name]["runtime"]["package_trees"]
        ):
            raise ValueError("history_native_library_changed")
        for target, source in FILES.items():
            if target == "Dockerfile":
                continue
            target = name + "_validate.py" if target == "history_validator_adapter.py" else target
            if result["runtime"]["wrappers_sha256"][target] != sha((ROOT / source).read_bytes()):
                raise ValueError("history_adapter_mismatch")
        command = (
            "docker run --rm -i --pull never --network none --read-only --user 10001:10001 "
            "--memory 192m --memory-swap 192m --cpus 0.25 --pids-limit 64 --cap-drop ALL "
            "--security-opt no-new-privileges -e PYTHONPATH=/validator --entrypoint python "
            + image
            + " -"
        )
        run = subprocess.run(  # noqa: S603 - pinned image and fixed code-only stdin
            [*ssh, command],
            input=(ROOT / "ops/probe_vh1_history.py").read_bytes(),
            capture_output=True,
            timeout=60,
            check=True,
        )
        probe = json.loads(run.stdout)
        if not probe["passed"]:
            raise ValueError("history_native_probe_failed")
        result.update(native_probe=probe, parent_image_id=parent["image_id"])
        reports[name] = result
        print(
            json.dumps({"name": name, "native_checks": len(probe["checks"]), "passed": True}),
            flush=True,
        )
        for v in registry["validators"]:
            if v["name"] == name and v["channel"] == "rollback":
                v.clear()
                v.update(parent, channel="rollback")
    report = {
        "version": "vh1-history-images-1.0",
        "validators": reports,
        "native_libraries_unchanged": True,
        "wrapper_sources_verified": True,
        "active_application_changed": False,
        "source_sha256": {
            p: sha((ROOT / p).read_bytes())
            for p in (
                *FILES.values(),
                "ops/probe_vh1_history.py",
                "ops/qualify_vh1_history_images.py",
            )
        },
    }
    write(ROOT / "config/validator-registry-vh1-history.json", registry)
    write(ROOT / "benchmarks/qualification/reports/vh1-history-images-v1.json", report)


if __name__ == "__main__":
    main()
