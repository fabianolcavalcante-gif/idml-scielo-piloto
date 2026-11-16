"""Source-bound evidence gate for bounded synthetic volume profiles only."""

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).parents[1]
CASES = {"stored_16m", "stored_100m", "expanded_500m", "text_14m", "files_10000", "disk_reserve"}
MIB = 1024**2


def evaluate(report):
    rows = report.get("cases", [])
    probes = {r.get("case"): r.get("probe") or {} for r in rows}
    samples = report.get("samples", [])
    conversions = [probes.get(c, {}) for c in sorted(CASES - {"files_10000", "disk_reserve"})]
    checks = {
        "version": report.get("version") == "phase7-v12-volume-observation-1.0",
        "watchdog": report.get("approved") is True and report.get("failures") == [],
        "matrix": len(rows) == 6 and set(probes) == CASES,
        "cases": bool(rows)
        and all(
            r.get("exit_code") == 0
            and r.get("oom_killed") is False
            and (r.get("probe") or {}).get("approved") is True
            and 0 < r.get("scratch_allocated_bytes", 0) <= 256 * MIB
            for r in rows
        ),
        "conversion": all(
            p.get("status") == "converted"
            and p.get("offline_valid") is True
            and p.get("xml_bytes", 0) > 0
            and len(p.get("xml_sha256", "")) == 64
            for p in conversions
        ),
        "stored_limits": probes.get("stored_16m", {}).get("input_bytes") == 16 * MIB
        and probes.get("stored_100m", {}).get("input_bytes") == 100 * MIB,
        "expanded_limit": probes.get("expanded_500m", {}).get("expanded_bytes") == 500 * MIB
        and 1 <= probes.get("expanded_500m", {}).get("max_compression_ratio", 0) <= 100,
        "text_volume": probes.get("text_14m", {}).get("input_bytes", 0) >= 14 * MIB
        and probes.get("text_14m", {}).get("xml_bytes", 0) >= 14 * MIB,
        "file_quota": probes.get("files_10000", {}).get("status") == "artifact_quota_exceeded"
        and probes.get("files_10000", {}).get("usage") == [138890, 10000],
        "disk_pressure": probes.get("disk_reserve", {}).get("status") == "artifact_disk_reserve",
        "bounded_rss": bool(probes)
        and all(0 < p.get("peak_rss_bytes", 0) <= 256 * MIB for p in probes.values()),
        "privacy": report.get("restricted_content_emitted") is False
        and all(
            p.get("restricted_content_emitted") is False and p.get("provider_calls") == 0
            for p in probes.values()
        ),
        "cleanup": report.get("cleanup_errors") == [],
        "services": report.get("existing_services_unchanged") is True,
        "host": len(samples) >= 5
        and all(
            s.get("memory_available_bytes", 0) >= 512 * MIB
            and s.get("ready") is True
            and s.get("ready_ms", 501) <= 500
            and s.get("disk_free_bytes", 0) >= 5 * 1024**3
            and s.get("disk_used_percent", 100) < 90
            for s in samples
        ),
        "isolation": report.get("limits")
        == {
            "memory_mib": 256,
            "cpus": 0.25,
            "tmpfs_mib": 64,
            "network": "none",
        },
    }
    return {
        "version": "phase7-v12-volume-gate-1.0",
        "approved": all(checks.values()),
        "checks": checks,
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
    paths = [
        p
        for directory, pattern in (
            ("src/idml_foundation", "*.py"),
            ("profiles", "*.json"),
            ("schemas", "*.json"),
        )
        for p in (ROOT / directory).rglob(pattern)
    ]
    paths += [
        ROOT / p
        for p in (
            "ops/probe_phase7_v12_volume.py",
            "ops/observe_phase7_v12_volume.py",
            "ops/observe_phase7_v12.py",
            "tests/phase3_helpers.py",
        )
    ]
    result["checks"]["sources"] = all(
        report.get("source_sha256", {}).get(p.relative_to(ROOT).as_posix())
        == hashlib.sha256(p.read_bytes()).hexdigest()
        for p in paths
    )
    result["approved"] = all(result["checks"].values())
    result["evidence_sha256"] = hashlib.sha256(raw).hexdigest()
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if result["approved"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
