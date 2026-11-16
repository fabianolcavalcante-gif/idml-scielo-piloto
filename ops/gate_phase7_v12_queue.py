"""Qualify the small real-queue probe, never the full V-12 capacity phase."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).parents[1]


def evaluate(report):
    probe = report.get("probe") or {}
    scenarios = probe.get("scenarios", [])
    samples = report.get("samples", [])
    states = report.get("container_states", {})
    version = report.get("version")
    new_profile = version == "phase7-v12-real-queue-observation-1.1"
    app_memory = 320 if new_profile else 224
    checks = {
        "version": (
            version == "phase7-v12-real-queue-observation-1.0"
            or (new_profile and bool(report.get("release")))
        )
        and probe.get("version") == "phase7-v12-real-queue-1.0",
        "watchdog": report.get("approved") is True
        and not report.get("failures")
        and report.get("cleanup_errors") == [],
        "existing_services": report.get("existing_services_unchanged") is True
        and report.get("existing_service_count", 0) > 0,
        "host_reserves": len(samples) >= 5
        and all(
            s.get("memory_available_bytes", 0) >= 512 * 1024**2
            and s.get("disk_free_bytes", 0) >= 5 * 1024**3
            and s.get("disk_used_percent", 100) < 90
            and s.get("ready") is True
            and s.get("ready_ms", 501) <= 500
            for s in samples
        ),
        "isolation": report.get("limits")
        == {
            "total_memory_mib": app_memory + 96 + 16,
            "application_memory_mib": app_memory,
            "internal_network": True,
            "published_ports": 0,
        },
        "no_oom": len(states) == 3 and all(s.get("oom_killed") is False for s in states.values()),
        "probe_approved": probe.get("approved") is True,
        "scenario_matrix": len(scenarios) == 4
        and {s.get("mode") for s in scenarios} == {"normal", "duplicate", "lost", "outage"},
        "conversions": bool(scenarios)
        and all(
            s.get("approved") is True
            and s.get("jobs") == 6
            and s.get("effects") == 6
            and s.get("events") == 18
            and s.get("delayed_job_respected") is True
            and s.get("delayed_observed_waiting") is True
            and len(s.get("samples", [])) == 6
            and len(s.get("xml_sha256", [])) == 1
            for s in scenarios
        ),
        "deterministic_across_scenarios": len(
            {h for s in scenarios for h in s.get("xml_sha256", [])}
        )
        == 1,
        "no_provider": probe.get("provider_calls") == 0,
        "privacy": all(r.get("restricted_content_emitted") is False for r in (report, probe)),
    }
    return {
        "version": "phase7-v12-real-queue-gate-1.1",
        "approved": all(checks.values()),
        "checks": checks,
        "v12_2_complete": False,
        "v12_complete": False,
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
    expected = report.get("source_sha256", {})
    paths = ("src/idml_foundation/worker.py", "src/idml_foundation/routers/jobs.py")
    matches = all(
        expected.get(p) == hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths
    )
    result["checks"]["candidate_overlays"] = matches
    result["approved"] = result["approved"] and matches
    result["evidence_sha256"] = hashlib.sha256(raw).hexdigest()
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if result["approved"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
