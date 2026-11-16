"""Public, fail-closed audit coverage; not a scientific or publication gate."""

import json

from ops.gate_vh1_reference_types import ROOT, inputs, sha
from ops.gate_vh1_reference_types import evaluate as native_evaluate
from ops.triage_vh1_content import AUDIT, OUTPUT, check_complete

REPORT = ROOT / OUTPUT
PIN = "65c0b782ee797c2a7bbd70a0507a4d058122fc9d11d03848d8129f1bd3990d84"


def evaluate(raw, reader):
    checks = {}
    try:
        report = json.loads(raw)
        checks["pinned_report"] = sha(raw) == PIN
        checks["current_evidence"] = all(
            sha(reader(path)) == digest for path, digest in report["source_sha256"].items()
        )
        checks["not_release"] = (
            all(
                report[k] is False
                for k in (
                    "raw_findings_modified",
                    "converter_invoked",
                    "scientific_fidelity_approved",
                    "formal_xml_approved",
                    "active_application_changed",
                    "content_emitted",
                )
            )
            and report["human_review_required"] is True
        )
        audit = json.loads(reader(AUDIT))
        checks["cases"] = (
            set(report["cases"]) == set(audit["cases"]) == {"esa-e20240086", "esa-e20240135"}
        )
        abstentions = 0
        for case, detail in report["cases"].items():
            comparison = audit["cases"][case]["raw_comparison"]
            counts = check_complete(comparison["findings"], detail["decisions"])
            abstentions += counts.get("scientific_glyph_abstention", 0)
            checks[case] = (
                counts == detail["classification_counts"]
                and detail["candidate_sha256"] == comparison["candidate_xml_sha256"]
                and detail["raw_blocking_findings"]
                == comparison["blocking_findings"]
                == (7 if case.endswith("86") else 23)
                and detail["raw_comparison_passed"] is comparison["passed"] is False
                and detail["all_raw_blocking_findings_classified"] is True
            )
        checks["scientific_abstention_retained"] = abstentions == 1
    except (KeyError, TypeError, ValueError, OSError):
        checks["complete_evidence"] = False
    return {
        "passed": bool(checks) and all(checks.values()),
        "checks": checks,
        "scientific_fidelity_approved": False,
        "formal_xml_approved": False,
        "human_review_required": True,
    }


def main():
    reader = lambda path: (ROOT / path).read_bytes()  # noqa: E731
    result = evaluate(REPORT.read_bytes(), reader)
    result["native_checkpoint_current"] = native_evaluate(*inputs(), reader)["passed"]
    result["passed"] = result["passed"] and result["native_checkpoint_current"]
    print(json.dumps(result, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
