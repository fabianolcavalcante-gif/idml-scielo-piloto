"""Verify SPS compatibility proof and both unchanged native predecessors."""

import json

from ops import gate_vh1_journal_metadata as modern
from ops import gate_vh1_journal_xpm as xpm
from ops.audit_vh1_sps_compatibility import PROBE, SOURCES
from ops.gate_vh1_composed_sources import source_matches

ROOT = modern.ROOT
REPORT = ROOT / "benchmarks/qualification/reports/vh1-sps-compatibility-v2.json"
PROOF = "7cc8b1fae0f5376cd0bf7757603e6a16ef3d2fe7a5a0fd922aee8a5b8d86a094"


def evaluate(report, reader):
    checks = {}
    try:
        checks["proof_identity"] = (
            modern.sha(json.dumps(report, sort_keys=True, indent=2).encode()) == PROOF
        )
        checks["current_sources"] = set(report["source_sha256"]) == set(SOURCES) and all(
            source_matches(path, expected, reader)
            for path, expected in report["source_sha256"].items()
        )
        prior = reader(xpm.REPORT.relative_to(ROOT).as_posix())
        native = reader(modern.REPORT.relative_to(ROOT).as_posix())
        previous = reader(modern.PREVIOUS.relative_to(ROOT).as_posix())
        checks["native_predecessors"] = (
            modern.sha(prior) == report["previous_xpm_proof_sha256"]
            and modern.sha(native) == report["independent_report_sha256"]
            and xpm.evaluate(json.loads(prior), reader)["passed"]
            and modern.evaluate(json.loads(native), json.loads(previous), reader)["passed"]
        )
        checks["probe_binding"] = modern.sha(reader(PROBE)) == report["probe_sha256"]
        checks["no_mutation_or_approval"] = all(
            report[key] is False
            for key in (
                "native_xpm_rerun",
                "candidate_changed",
                "vendor_changed",
                "active_application_changed",
                "homologation_ready",
                "release_approved",
            )
        )
        checks["cases"] = set(report["assessments"]) == {"esa-e20240086", "esa-e20240135"}
        for name, result in report["assessments"].items():
            base = json.loads(prior)["assessments"][name]
            checks[name] = (
                result["base"] == base
                and result["homologation_ready"] is False
                and result["release_approved"] is False
                and len(result["exceptions"]) == 4
                and len({e["occurrence_sha256"] for e in result["exceptions"]}) == 4
                and {e["rule_id"] for e in result["exceptions"]}
                == {
                    "xpm-sps110-version-table-1.0",
                    "xpm-sps110-date-type-1.0",
                    "xpm-sps110-date-combination-1.0",
                }
                and result["unresolved_counts"]
                == {
                    "blocking_errors": 0,
                    "fatal_errors": 1,
                    "errors": 1,
                    "warnings": base["original"]["warnings"],
                }
                and "required-queries-incomplete" in result["reasons"]
                and "doctype-jats-decision-pending" in result["reasons"]
            )
    except (KeyError, ValueError, TypeError, OSError):
        checks["complete_evidence"] = False
    return {
        "passed": bool(checks) and all(checks.values()),
        "checks": checks,
        "homologation_ready": False,
        "release_approved": False,
    }


if __name__ == "__main__":
    result = evaluate(json.loads(REPORT.read_bytes()), lambda path: (ROOT / path).read_bytes())
    print(json.dumps(result))
    raise SystemExit(0 if result["passed"] else 1)
