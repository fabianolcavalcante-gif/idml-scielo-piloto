"""CI can verify warning triage without access to private scientific inputs."""

import json

from ops.gate_vh1_final_validation import FINAL, ROOT, inputs, sha
from ops.gate_vh1_final_validation import evaluate as native_evaluate
from ops.triage_vh1_final_warnings import OUTPUT, SPEC_SHA, fingerprint

PIN = "40ace7e7f026be8964a8ac84cd5477dec5328cae078e1decc549302ccb0310d0"
REPORT = ROOT / OUTPUT


def evaluate(raw, reader):
    checks = {}
    try:
        report = json.loads(raw)
        checks["pinned_report"] = sha(raw) == PIN
        checks["current_sources"] = all(
            sha(reader(p)) == h for p, h in report["source_sha256"].items()
        )
        checks["no_approval_or_suppression"] = all(
            report[k] is False
            for k in (
                "raw_findings_modified",
                "warnings_accepted_for_release",
                "formal_xml_approved",
                "scientific_fidelity_approved",
                "active_application_changed",
                "content_emitted",
                "vh07_complete",
            )
        )
        checks["dependencies_retained"] = (
            report["release_status"] == "validation-unavailable"
            and report["remaining_ambiguous_glyphs"] == 1
            and report["reference_locator_reviews"] == 2
            and report["specification_sha256"] == SPEC_SHA
        )
        checks["cases"] = set(report["cases"]) == set(FINAL)
        for name, case in report["cases"].items():
            checks[name + "/candidate"] = (case["xml_sha256"], case["package_sha256"]) == FINAL[
                name
            ]
            checks[name + "/xpm"] = (
                case["xpm"]["status"] == "unavailable"
                and case["xpm"]["candidate_package_sha256"] == FINAL[name][1]
            )
            checks[name + "/coverage"] = (
                case["all_warnings_classified"] is True
                and len(case["validators"]) == 2
                and all(len(v["decisions"]) == 5 for v in case["validators"])
                and all(
                    d["accepted_for_release"] is False
                    and d["human_review_required"] is True
                    and d["severity_retained"] == "warning"
                    and d["structural_group_sha256"]
                    == fingerprint(case["structural_groups"][d["group"]])
                    for v in case["validators"]
                    for d in v["decisions"]
                )
            )
    except (KeyError, ValueError, TypeError, OSError):
        checks["complete_evidence"] = False
    return {
        "passed": bool(checks) and all(checks.values()),
        "checks": checks,
        "formal_xml_approved": False,
        "vh07_complete": False,
    }


def main():
    reader = lambda p: (ROOT / p).read_bytes()  # noqa: E731
    result = evaluate(REPORT.read_bytes(), reader)
    result["native_checkpoint_current"] = native_evaluate(*inputs(), reader)["passed"]
    result["passed"] = result["passed"] and result["native_checkpoint_current"]
    print(json.dumps(result, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
