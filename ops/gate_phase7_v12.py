"""Qualify V-12's initial bounded capacity experiment, not production throughput."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).parents[1]
REPORTS = ROOT / "benchmarks/qualification/reports"


def evaluate(vps: dict, corpus: dict, costs: dict) -> dict:
    checks = {}
    checks["versions"] = (
        vps.get("version") == "phase7-v12-vps-observation-1.0"
        and corpus.get("version") == "phase7-v12-local-corpus-1.0"
        and costs.get("version") == "phase7-v12-historical-cost-1.0"
    )
    checks["vps_approved"] = vps.get("approved") is True and not vps.get("failures")
    checks["existing_services"] = vps.get("existing_services_unchanged") is True
    checks["cleanup"] = vps.get("container_removed") is True
    limits = vps.get("limits", {})
    checks["isolation"] = limits.get("network") == "none" and limits.get("read_only") is True
    checks["resource_budget"] = limits.get("memory_mib") == 256 and limits.get("cpus") == 0.25
    samples = vps.get("samples", [])
    checks["host_samples"] = len(samples) >= 100 and all(
        s.get("ready") is True
        and s.get("ready_ms", 501) <= 500
        and s.get("memory_available_bytes", 0) >= 512 * 1024**2
        and s.get("disk_used_percent", 100) < 90
        for s in samples
    )
    bench = vps.get("benchmark") or {}
    checks["benchmark_approved"] = bench.get("approved") is True
    rows = bench.get("rows", [])
    checks["case_matrix"] = len(rows) == 6 and {
        (r.get("case"), r.get("concurrency")) for r in rows
    } == {(name, concurrency) for name in ("small", "typical", "large") for concurrency in (1, 2)}
    checks["deterministic_conversions"] = bool(rows) and all(
        r.get("all_valid") is True
        and r.get("deterministic") is True
        and len(r.get("samples", [])) >= 3
        and len({s.get("xml_sha256") for s in r["samples"]}) == 1
        and all(s.get("status") == "valid" and s.get("xml_sha256") for s in r["samples"])
        for r in rows
    )
    checks["pathological_rejected"] = (
        bench.get("pathological", {}).get("status") == "rejected:compression_ratio"
    )
    soak = bench.get("soak", {})
    checks["bounded_soak"] = (
        soak.get("requested_seconds", 0) >= 300
        and soak.get("elapsed_seconds", 0) >= 300
        and soak.get("conversions", 0) >= 10
        and isinstance(soak.get("rss_growth_bytes"), int)
        and soak["rss_growth_bytes"] <= 32 * 1024**2
    )
    checks["no_new_provider"] = (
        bench.get("provider_calls") == 0 and costs.get("new_provider_calls") == 0
    )
    articles = corpus.get("articles", [])
    checks["real_corpus"] = (
        corpus.get("approved") is True
        and len(articles) == 2
        and {r.get("corpus_id") for r in articles} == {"esa-e20240086", "esa-e20240135"}
        and all(
            r.get("all_valid") is True and r.get("candidate_matches_qualification") is True
            for r in articles
        )
    )
    runs = costs.get("runs", [])
    amounts = [
        r.get(key)
        for r in [costs, *runs]
        for key in ("recorded_cost_microusd", "failed_role_cost_microusd")
    ]
    known_costs = all(
        type(value) in (int, float) and math.isfinite(value) and value >= 0 and value == int(value)
        for value in amounts
    )
    checks["historical_cost_accounting"] = (
        bool(runs)
        and known_costs
        and (
            costs.get("recorded_cost_microusd")
            == sum(r.get("recorded_cost_microusd", 0) for r in runs)
            and costs.get("failed_role_cost_microusd")
            == sum(r.get("failed_role_cost_microusd", 0) for r in runs)
            and len(costs.get("assistive_domains", [])) == 6
        )
    )
    checks["privacy"] = all(
        r.get("restricted_content_emitted") is False for r in (vps, corpus, costs)
    )
    return {
        "version": "phase7-v12-initial-capacity-gate-1.0",
        "stage": "V-12.1",
        "approved": all(checks.values()),
        "checks": checks,
        "v12_complete": False,
        "production_throughput_qualified": False,
        "release_ready": False,
        "remaining": [
            "durable API/Redis/job queue capacity",
            "upload/storage/backups budgets",
            "long-duration and integrated AI capacity qualification",
        ],
        "restricted_content_emitted": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    paths = [
        REPORTS / name
        for name in (
            "v12-vps-observation-v1.json",
            "v12-local-corpus-v1.json",
            "v12-historical-cost-v1.json",
        )
    ]
    try:
        report = evaluate(*(json.loads(path.read_text(encoding="utf-8")) for path in paths))
        report["evidence_sha256"] = {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths
        }
    except Exception as exc:
        report = {
            "approved": False,
            "error": type(exc).__name__,
            "v12_complete": False,
            "release_ready": False,
            "restricted_content_emitted": False,
        }
    output = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 0 if report["approved"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
