"""Verify PostgreSQL/cross-process storage evidence without approving production."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
from ops.gate_phase7_v12_queue import evaluate as queue_gate  # noqa: E402
from ops.observe_phase7_v12_queue import OVERLAYS  # noqa: E402

REQUIRED = {
    "cross_process_busy",
    "rollback_orphan_preserved",
    "orphan_charged_to_quota",
    "orphan_recovered",
    "committed_deduplicated",
}


def evaluate(report):
    storage = report.get("probe", {}).get("storage", {})
    checks = storage.get("checks", {})
    approved = (
        queue_gate(report)["approved"]
        and storage.get("approved") is True
        and set(checks) == REQUIRED
        and all(value is True for value in checks.values())
        and storage.get("provider_calls") == 0
    )
    return {
        "version": "phase7-v12-storage-gate-1.0",
        "approved": approved,
        "v12_2_complete": False,
        "production_capacity_qualified": False,
        "release_ready": False,
        "restricted_content_emitted": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw = args.report.read_bytes()
    report = json.loads(raw)
    result = evaluate(report)
    sources = (
        *OVERLAYS,
        "ops/probe_phase7_v12_storage.py",
        "ops/lab_phase7_v12_queue.py",
        "ops/observe_phase7_v12_queue.py",
        "ops/benchmark_phase7_v12.py",
        "tests/phase3_helpers.py",
    )
    result["sources_match"] = all(
        report.get("source_sha256", {}).get(p)
        == hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
        for p in sources
    )
    result["approved"] = result["approved"] and result["sources_match"]
    result["evidence_sha256"] = hashlib.sha256(raw).hexdigest()
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if result["approved"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
