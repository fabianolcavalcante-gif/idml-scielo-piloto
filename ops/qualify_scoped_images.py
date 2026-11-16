"""Read-only inspection proves wrapper contents and unchanged pinned native package trees."""

import hashlib
import json
from pathlib import Path

from idml_foundation.release.validator_registry import ValidatorChannel, load_validator_registry
from ops.prepare_vh1_scoped_images import FILES
from ops.vh1_baseline import remote_runtime

ROOT = Path(__file__).resolve().parents[1]


def main():
    registry = load_validator_registry(ROOT / "config/validator-registry-vh1-scoped.json")
    baseline = json.loads(
        (ROOT / "benchmarks/qualification/reports/vh1-lot2-baseline-v1.json").read_bytes()
    )
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
    for name in ("packtools", "spsvalidator"):
        artifact = registry.select(name, ValidatorChannel.ACTIVE)
        result = remote_runtime(ssh, artifact)
        if (
            result["runtime"]["package_trees"]
            != baseline["validators"][name]["runtime"]["package_trees"]
        ):
            raise ValueError("native_library_changed")
        for target, source in FILES.items():
            if target == "Dockerfile":
                continue
            key = name + "_validate.py" if target == "scoped_validator_adapter.py" else target
            if (
                result["runtime"]["wrappers_sha256"][key]
                != hashlib.sha256((ROOT / source).read_bytes()).hexdigest()
            ):
                raise ValueError("adapter_source_differs")
        reports[name] = result
    output = {
        "version": "vh1-scoped-images-1.0",
        "native_libraries_unchanged": True,
        "wrapper_sources_verified": True,
        "validators": reports,
        "active_application_changed": False,
        "source_sha256": {
            source: hashlib.sha256((ROOT / source).read_bytes()).hexdigest()
            for source in FILES.values()
        },
    }
    target = ROOT / "benchmarks/qualification/reports/vh1-scoped-images-v1.json"
    with target.open("x", encoding="utf-8") as stream:
        json.dump(output, stream, indent=2)
    print(json.dumps({"native_libraries_unchanged": True, "wrapper_sources_verified": True}))


if __name__ == "__main__":
    main()
