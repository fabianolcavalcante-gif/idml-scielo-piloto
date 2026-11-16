"""Revalidate exact v7 XML/ZIP with a documented candidate policy, without reconversion."""

import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from ops.gate_vh1_metadata import main as metadata_gate

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "benchmarks/private/output/vh1-metadata-20261006T223858Z"
SPEC = ROOT / "benchmarks/private/output/vh1-history-spec-20261007T114702Z"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    if metadata_gate():
        raise ValueError("metadata_baseline_no_longer_current")
    previous = json.loads(
        (ROOT / "benchmarks/qualification/reports/vh1-metadata-linux-v7.json").read_bytes()
    )
    raw = (BASE / "plan.json").read_bytes()
    plan = json.loads(raw)
    if sha(raw) != previous["plan_sha256"] or plan != previous["qualification"]:
        raise ValueError("history_baseline_plan_mismatch")
    folder = (
        ROOT
        / "benchmarks/private/output"
        / datetime.now(UTC).strftime("vh1-history-%Y%m%dT%H%M%SZ")
    )
    folder.mkdir(exist_ok=False)
    for name, digest in plan["code_sha256"].items():
        if sha((BASE / name).read_bytes()) != digest:
            raise ValueError("history_baseline_code_changed")
        shutil.copyfile(BASE / name, folder / name)
    for case, details in plan["cases"].items():
        for name, digest in details["files"].items():
            source = BASE / case / name
            if sha(source.read_bytes()) != digest:
                raise ValueError("history_baseline_file_changed")
            target = folder / case / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    runner = "run_vh1_history_linux.py"
    shutil.copyfile(ROOT / "ops" / runner, folder / runner)
    plan["code_sha256"][runner] = sha((folder / runner).read_bytes())
    registry = ROOT / "config/validator-registry-vh1-history.json"
    shutil.copyfile(registry, folder / "registry.json")
    plan["registry_sha256"] = sha(registry.read_bytes())
    plan["history_baseline_plan_sha256"] = sha(raw)
    plan["history_specification"] = json.loads((SPEC / "manifest.json").read_bytes())
    for filename, key in (("sps-specification.txt", "sha256"), ("history.txt", "history_sha256")):
        if sha((SPEC / filename).read_bytes()) != plan["history_specification"][key]:
            raise ValueError("history_specification_changed")
        shutil.copyfile(SPEC / filename, folder / filename)
    plan["history_reconversion_performed"] = False
    plan["history_source_sha256"] = {
        p: sha((ROOT / p).read_bytes())
        for p in (
            "ops/history_compat.py",
            "ops/history_validator_adapter.py",
            "ops/probe_vh1_history.py",
            "ops/prepare_vh1_history_qualification.py",
            "ops/run_vh1_history_linux.py",
            "ops/collect_vh1_history_spec.py",
            "deploy/Dockerfile.validator-history-compat",
        )
    }
    with (folder / "plan.json").open("x", encoding="utf-8") as stream:
        json.dump(plan, stream, sort_keys=True, indent=2)
    print(
        json.dumps(
            {"directory": str(folder), "plan_sha256": sha((folder / "plan.json").read_bytes())}
        )
    )


if __name__ == "__main__":
    main()
