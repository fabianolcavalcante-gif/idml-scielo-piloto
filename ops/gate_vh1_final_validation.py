"""Verify the exact final package checkpoint; XPM remains an unavailable dependency."""

import argparse
import json
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from ops.gate_vh1_doctype import code_matches
from ops.gate_vh1_journal_metadata import source_matches as journal_source_matches
from ops.gate_vh1_reference_types import FINAL as BEFORE
from ops.gate_vh1_reference_types import REPORT as PREVIOUS
from ops.qualify_vh1_final_validation import CONTRACT, ROOT, RUNNER, SOURCES, sha
from ops.qualify_vh1_history_images import IMAGES
from ops.triage_vh1_final_warnings import CODES

REPORT = ROOT / "benchmarks/qualification/reports/vh1-final-validation-linux-v2.json"
PLAN = "7f4042490ef244603fd8910c5daf653979b2a9c1e7a2fc75de6216bb91847d4c"
CANONICAL_PLAN = "19772c3dbae211b8399abdddae20a78bb3f471bccf5355e91d21980635e38b1c"
# Canonical JSON hashes differ from the Windows report file's CRLF byte hash.
NATIVE = "6f4d474012bb2d5bfc02a47aec8be1156a7baa337f5358cfd266193aa3f48269"
PRIOR_NATIVE = "83de88b9b3553eaa0fa0881ae12b801c9f55013c8b984d44de024efda5e84c83"
FINAL = {
    "esa-e20240086": (
        "9a1386e47778597683f9ceb0c4d078b37a68e521d3b2e2eb7b3b51ad31e93916",
        "ba685142396801ed3901d8c63e3ad5da0c81af3b753c6a16b27bb63457a66c6c",
    ),
    "esa-e20240135": BEFORE["esa-e20240135"],
}


def evaluate(report, previous, reader):
    checks = {}
    try:
        plan = report["qualification"]
        checks["pinned_native_reports"] = (
            sha(json.dumps(report, sort_keys=True, indent=2).encode()) == NATIVE
            and sha(json.dumps(previous, sort_keys=True, indent=2).encode()) == PRIOR_NATIVE
        )
        checks["pinned_plan"] = (
            report["version"] == "vh1-history-linux-1.0"
            and report["transport"] == "scoped-broker-executor-not-socket"
            and plan["version"] == "vh1-final-validation-local-1.0"
            and report["plan_sha256"] == PLAN
            and sha(json.dumps(plan, sort_keys=True, indent=2).encode()) == CANONICAL_PLAN
        )
        checks["not_release"] = (
            all(
                obj[k] is False
                for obj in (report, plan)
                for k in ("formal_xml_approved", "active_application_changed")
            )
            and plan["gold_read"] is False
            and plan["inspection_only"] is False
            and plan["autonomous_application"] is False
            and plan["human_review_required"] is True
            and plan["remaining_ambiguous_glyphs"] == 1
        )
        checks["current_sources"] = (
            set(plan["source_sha256"]) == set(SOURCES)
            and plan["before_source_sha256"] == previous["qualification"]["source_sha256"]
            and all(journal_source_matches(p, h, reader) for p, h in plan["source_sha256"].items())
            and code_matches(plan["code_sha256"], RUNNER, reader)
            and plan["registry_sha256"] == sha(reader("config/validator-registry-vh1-history.json"))
        )
        contract = json.loads(reader(CONTRACT))
        checks["cases"] = len(report["cases"]) == 2 and {c["case"] for c in report["cases"]} == set(
            FINAL
        )
        for case in report["cases"]:
            name = case["case"]
            first = name.endswith("86")
            detail = plan["cases"][name]
            old_case = next(c for c in previous["cases"] if c["case"] == name)
            old_detail = previous["qualification"]["cases"][name]
            checks[name + "/preservation"] = (
                (detail["before_xml_sha256"], detail["before_package_sha256"]) == BEFORE[name]
                and (detail["xml_sha256"], detail["package_sha256"]) == FINAL[name]
                and detail["files"]["candidate.xml"] == FINAL[name][0]
                and detail["files"]["candidate.zip"] == FINAL[name][1]
                and detail["delta"]
                == {
                    "fields": contract["cases"][name],
                    "changed_affiliations": int(first),
                    "all_other_xml_unchanged": True,
                    "source_text_preserved": True,
                }
                and detail["source_idml_sha256"] == contract["source_idml_sha256"][name]
                and detail["catalog_sha256"] == old_detail["catalog_sha256"]
                and detail["files"]["canonical.json"] == old_detail["files"]["canonical.json"]
                and detail["files"]["reference_type_catalog.json"]
                == old_detail["files"]["reference_type_catalog.json"]
                and detail["offline_valid"] is True
                and detail["deterministic"] is True
                and detail["unchanged_assets"] == old_detail["unchanged_assets"]
            )
            start = datetime.fromisoformat(plan["created_at"])
            collected = detail["fresh_authorities"]
            checks[name + "/fresh_sources"] = (
                all(
                    start <= datetime.fromisoformat(r["retrieved_at"]) <= start + timedelta(hours=1)
                    for r in (collected["doi"], *collected["editorial"].values())
                )
                and collected["doi"]["sha256"] == detail["files"]["incoming/crossref.json"]
                and all(
                    r["sha256"] == detail["files"]["incoming/" + k + ".json"]
                    for k, r in collected["editorial"].items()
                )
            )
            checks[name + "/tools"] = len(case["validators"]) == 2 and {
                v["name"] for v in case["validators"]
            } == set(IMAGES)
            for run in case["validators"]:
                tool = run["name"]
                old = next(v for v in old_case["validators"] if v["name"] == tool)
                expected = Counter(json.dumps(f, sort_keys=True) for f in old["findings"])
                if first:
                    # One actual correction, not a blanket warning waiver.
                    code = next(c for c, group in CODES[tool].items() if group == "affiliation")
                    item = next(f for f in old["findings"] if f["code"] == code)
                    expected[json.dumps(item, sort_keys=True)] -= 1
                key = name + "/" + tool
                checks[key + "/findings"] = (
                    run["image_id"] == old["image_id"] == IMAGES[tool]
                    and run["candidate_sha256"] == FINAL[name][0 if tool == "packtools" else 1]
                    and Counter(json.dumps(f, sort_keys=True) for f in run["findings"]) == expected
                    and run["counts"]
                    == dict(Counter(f["response"] for f in run["findings"]))
                    == {"warning": 5}
                )
                checks[key + "/authorities"] = run["authority_evidence"] == {
                    **old["authority_evidence"],
                    "binding": {
                        "bundle_sha256": detail["files"]["incoming/manifest.json"],
                        "grant_sha256": detail["files"]["grant.json"],
                        "scope_sha256": detail["scope_sha256"],
                    },
                }
                checks[key + "/history"] = run["history_policy_evidence"] == {
                    **old["history_policy_evidence"],
                    "candidate_sha256": run["candidate_sha256"],
                }
    except (KeyError, TypeError, ValueError, OSError, StopIteration):
        checks["complete_evidence"] = False
    return {
        "passed": bool(checks) and all(checks.values()),
        "checks": checks,
        "formal_xml_approved": False,
        "scientific_fidelity_approved": False,
        "active_application_changed": False,
        "vh07_complete": False,
        "xpm_status": "unavailable",
        "remaining_ambiguous_glyphs": 1,
    }


def inputs(path=REPORT):
    return json.loads(path.read_bytes()), json.loads(PREVIOUS.read_bytes())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--publish", type=Path)
    args = parser.parse_args()
    values = inputs(args.publish or REPORT)
    result = evaluate(*values, lambda p: (ROOT / p).read_bytes())
    if args.publish and result["passed"]:
        with REPORT.open("x", encoding="utf-8") as stream:
            json.dump(values[0], stream, indent=2, sort_keys=True)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
