"""Qualify bounded synthetic ingestion only; storage/HTTP capacity remain pending."""

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).parents[1]
EXPECTED = {
    "nodes_100k": "accepted",
    "nodes_500k": "rejected:unsafe_xml",
    "nodes_2m": "rejected:unsafe_xml",
    "xml_oversize": "rejected:unsafe_xml",
    "mimetype_oversize": "rejected:invalid_mimetype",
    "expanded_oversize": "rejected:expanded_too_large",
    "xml_total_near_limit": "accepted",
    "xml_total_over_limit": "rejected:expanded_xml_too_large",
}


def evaluate(report):
    cases = report.get("cases", [])
    samples = report.get("samples", [])
    checks = {
        "version": report.get("version") == "phase7-v12-ingest-observation-1.0",
        "complete": report.get("observation_complete") is True and report.get("failures") == [],
        "no_oom": report.get("all_probes_survived") is True
        and bool(cases)
        and all(c.get("oom_killed") is False and c.get("exit_code") == 0 for c in cases),
        "matrix": len(cases) == len(EXPECTED) and {c.get("case") for c in cases} == set(EXPECTED),
        "outcomes": bool(cases)
        and all((c.get("probe") or {}).get("status") == EXPECTED.get(c.get("case")) for c in cases),
        "rss_headroom": bool(cases)
        and all(
            0 < (c.get("probe") or {}).get("peak_rss_bytes", 0) <= 192 * 1024**2 for c in cases
        ),
        "host_reserves": len(samples) >= 5
        and all(
            s.get("ready") is True
            and s.get("ready_ms", 501) <= 500
            and s.get("memory_available_bytes", 0) >= 512 * 1024**2
            and s.get("disk_free_bytes", 0) >= 5 * 1024**3
            and s.get("disk_used_percent", 100) < 90
            for s in samples
        ),
        "cleanup": report.get("cleanup_errors") == [],
        "existing_services": report.get("existing_services_unchanged") is True,
        "isolation": report.get("limits")
        == {"memory_mib": 256, "cpus": 0.25, "network": "none", "read_only": True},
        "privacy": report.get("restricted_content_emitted") is False
        and all((c.get("probe") or {}).get("restricted_content_emitted") is False for c in cases),
        "no_provider": report.get("provider_calls") == 0,
    }
    return {
        "version": "phase7-v12-ingest-gate-1.0",
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
        "src/idml_foundation/" + p
        for p in (
            "ingest/safe_zip.py",
            "ingest/xml_security.py",
            "pipeline/idml_parser.py",
            "services/artifacts.py",
        )
    ]
    result["checks"]["candidate_sources"] = all(
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
