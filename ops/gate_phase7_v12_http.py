"""Verify isolated multipart evidence without claiming full conversion capacity."""

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).parents[1]
CASES = {
    "2097152-declared",
    "104857600-declared",
    "104857600-chunked",
    "disconnect",
    "oversized_declared",
}


def evaluate(report):
    probe = report.get("probe") or {}
    cases = probe.get("cases", [])
    samples = report.get("samples", [])
    cleanup = [case for case in cases if case.get("case") != "oversized_declared"]
    checks = {
        "admission": probe.get("admission")
        == {
            "busy_status": 503,
            "idle_status": 408,
            "recovery_status": 200,
            "open_files_after_timeout": 0,
            "approved": True,
        },
        "versions": report.get("version") == "phase7-v12-http-observation-1.0"
        and probe.get("version") == "phase7-v12-http-probe-1.0",
        "observation": report.get("approved") is True and report.get("failures") == [],
        "probe": probe.get("approved") is True,
        "matrix": len(cases) == len(CASES) and {r.get("case") for r in cases} == CASES,
        "cases": bool(cases) and all(r.get("approved") is True for r in cases),
        "statuses": all(
            r.get("status") == (413 if r.get("case") == "oversized_declared" else 200)
            for r in cases
            if r.get("case") != "disconnect"
        ),
        "files_closed": len(cleanup) == 4
        and all(r.get("stats", {}).get("open_files") == 0 for r in cleanup),
        "disk_spooling_exercised": any(
            r.get("case") == "disconnect" and r.get("stats", {}).get("rolled_files", 0) >= 4
            for r in cases
        ),
        "rss": bool(cleanup)
        and all(0 < r.get("stats", {}).get("peak_rss_bytes", 0) <= 128 * 1024**2 for r in cleanup),
        "no_oom": report.get("container_exit") == {"ExitCode": 0, "OOMKilled": False},
        "cleanup": report.get("cleanup_errors") == [],
        "services": report.get("existing_services_unchanged") is True,
        "host": len(samples) >= 5
        and all(
            s.get("ready") is True
            and s.get("ready_ms", 501) <= 500
            and s.get("memory_available_bytes", 0) >= 512 * 1024**2
            and s.get("disk_free_bytes", 0) >= 5 * 1024**3
            and s.get("disk_used_percent", 100) < 90
            for s in samples
        ),
        "isolation": report.get("limits")
        == {"memory_mib": 256, "cpus": 0.25, "tmpfs_mib": 128, "network": "none"},
        "privacy": all(r.get("restricted_content_emitted") is False for r in (report, probe)),
        "no_provider": probe.get("provider_calls") == 0,
    }
    return {
        "version": "phase7-v12-http-gate-1.0",
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
    paths = (
        "src/idml_foundation/ingest/http_upload.py",
        "src/idml_foundation/ingest/upload_admission.py",
        "src/idml_foundation/settings.py",
        "ops/probe_phase7_v12_http.py",
    )
    result["checks"]["sources"] = all(
        report.get("source_sha256", {}).get(p)
        == hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
        for p in paths
    )
    result["approved"] = all(result["checks"].values())
    result["evidence_sha256"] = hashlib.sha256(raw).hexdigest()
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if result["approved"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
