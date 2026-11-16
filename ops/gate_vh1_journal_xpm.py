"""Verify the preserved native compatibility proof, without granting readiness."""

import json

from ops.gate_vh1_journal_metadata import ROOT, sha
from ops.gate_vh1_journal_metadata import evaluate as journal_gate
from ops.gate_vh1_journal_metadata import inputs as journal_inputs

REPORT = ROOT / "benchmarks/qualification/reports/vh1-journal-xpm-compatibility-v1.json"
PROOF = "136f16664167dee6ca01042cbfb9f43fde77c9062a7042d8c1cde4daeab4a26e"


def evaluate(report, reader):
    checks = {}
    try:
        checks["native_identity"] = (
            sha(json.dumps(report, sort_keys=True, indent=2).encode()) == PROOF
        )
        native = report["native"]
        checks["current_sources"] = all(
            sha(reader(p)) == h
            for sources in (report["source_sha256"], native["source_sha256"])
            for p, h in sources.items()
        )
        checks["comparison_contraproof"] = (
            sha(reader("benchmarks/qualification/reports/vh1-xpm-doi-comparisons-v1.json"))
            == report["doi_comparison_probe_sha256"]
        )
        checks["no_approval"] = (
            all(
                report[k] is False
                for k in ("homologation_ready", "release_approved", "active_application_changed")
            )
            and native["release_approved"] is False
            and native["production_deployed"] is False
        )
        checks["negative_and_isolation"] = (
            native["negative_control_detected"] is True
            and native["boundary_denials"] == 3
            and native["services_unchanged"] is True
            and native["observed_service_count"] == 25
        )
        for name, value in report["assessments"].items():
            case = next(
                c for c in native["cases"] if c["article"] == name and c["mutation"] == "baseline"
            )
            checks[name] = (
                value["homologation_ready"] is False
                and value["release_approved"] is False
                and value["original"]["report_sha256"] == case["report_sha256"]
                and {k: value["original"][k] for k in case["counts"]} == case["counts"]
                and value["original"]["errors"] == 4
                and value["unresolved_counts"]["errors"] == 2
                and {e["rule_id"] for e in value["exceptions"]}
                == {"xpm-doi-journal-exact-1.0", "xpm-doi-article-exact-1.0"}
                and "required-queries-incomplete" in value["reasons"]
            )
    except (KeyError, ValueError, TypeError, OSError, StopIteration):
        checks["complete_evidence"] = False
    return {
        "passed": bool(checks) and all(checks.values()),
        "checks": checks,
        "homologation_ready": False,
        "release_approved": False,
    }


if __name__ == "__main__":
    result = evaluate(json.loads(REPORT.read_bytes()), lambda p: (ROOT / p).read_bytes())
    result["journal_successor_passed"] = journal_gate(
        *journal_inputs(), lambda p: (ROOT / p).read_bytes()
    )["passed"]
    result["passed"] = result["passed"] and result["journal_successor_passed"]
    print(json.dumps(result))
    raise SystemExit(0 if result["passed"] else 1)
