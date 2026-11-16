"""Verify source-revision evidence without publishing scientific content or approving release."""

import argparse
import json
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from ops.gate_vh1_doctype import code_matches
from ops.gate_vh1_formula_links import FINAL as BEFORE
from ops.gate_vh1_formula_links import REPORTS, ROOT, sha
from ops.qualify_vh1_formula_revisions import RUNNER, SOURCES
from ops.qualify_vh1_history_images import IMAGES
from ops.vh1_source_evolution import source_matches

REPORT = REPORTS / "vh1-formula-revisions-linux-v1.json"
PLAN = "939dcee8ad1b50d09ee22abf51da6301ab7d2bfbb79675416fe2b7c71df88c82"
CANONICAL_PLAN = "3a63b6dc0b1714b8dac25fce2ca701d1076d1a883aa46fc3d8b099bb22e5e3cb"
FINAL = {
    "esa-e20240086": (
        "e0eb4cb4989a1d7ff2c6059f3b57b687fdca40bdf56664dafa4f342b4e772bbe",
        "32e4866803d5b8120453b98b1e1044bfbbd27316b3049ecb227946e3947ec0d8",
    ),
    "esa-e20240135": (
        "875dc7ff6d66d14dcc4fa125dad6a7db001e44444c75c5f31a4cbe49f5a1f0c7",
        "1ccac72fffebcf7793e59035ee5a02b3f0177b319f2802f95a1041cea8e91546",
    ),
}


def evaluate(report, previous, reader):
    checks = {}
    try:
        plan = report["qualification"]
        checks["not_release"] = (
            all(
                obj[k] is False
                for obj in (report, plan)
                for k in ("formal_xml_approved", "active_application_changed")
            )
            and plan["gold_read"] is False
            and plan["autonomous_application"] is False
            and plan["human_review_required"] is True
        )
        checks["pinned_plan"] = (
            report["version"] == "vh1-history-linux-1.0"
            and plan["version"] == "vh1-formula-revisions-local-1.0"
            and report["plan_sha256"] == PLAN
            and sha(json.dumps(plan, sort_keys=True, indent=2).encode()) == CANONICAL_PLAN
            and report["transport"] == "scoped-broker-executor-not-socket"
        )
        checks["current_sources"] = (
            set(plan["source_sha256"]) == set(SOURCES)
            and all(source_matches(p, h, reader) for p, h in plan["source_sha256"].items())
            and code_matches(plan["code_sha256"], RUNNER, reader)
            and plan["registry_sha256"] == sha(reader("config/validator-registry-vh1-history.json"))
        )
        checks["cases"] = len(report["cases"]) == 2 and {c["case"] for c in report["cases"]} == set(
            FINAL
        )
        for case in report["cases"]:
            name = case["case"]
            detail = plan["cases"][name]
            old_case = next(c for c in previous["cases"] if c["case"] == name)
            first = name == "esa-e20240086"
            expected_counts = (
                {"source_correction": 3, "reviewed_no_confirmed_transcription_defect": 14}
                if first
                else {
                    "source_correction": 11,
                    "reviewed_no_confirmed_transcription_defect": 27,
                    "glyph_or_style_review_pending": 5,
                }
            )
            changes = detail["delta"]["changes"]
            checks[name + "/preservation"] = (
                (detail["before_xml_sha256"], detail["before_package_sha256"]) == BEFORE[name]
                and (detail["xml_sha256"], detail["package_sha256"]) == FINAL[name]
                and detail["files"]["candidate.xml"] == FINAL[name][0]
                and detail["files"]["candidate.zip"] == FINAL[name][1]
                and detail["files"]["formula_catalog.json"] == detail["catalog_sha256"]
                and detail["delta"]["all_other_xml_unchanged"] is True
                and detail["delta"]["formula_count"] == (17 if first else 43)
                and len(changes) == len({c["id"] for c in changes}) == (3 if first else 11)
                and detail["review_counts"] == expected_counts
                and detail["offline_valid"] is True
                and detail["deterministic"] is True
            )
            collected = detail["fresh_authorities"]
            started = datetime.fromisoformat(plan["created_at"])
            checks[name + "/fresh_sources"] = (
                all(
                    started
                    <= datetime.fromisoformat(r["retrieved_at"])
                    <= started + timedelta(hours=1)
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
                old = next(r for r in old_case["validators"] if r["name"] == tool)
                key = name + "/" + tool
                checks[key + "/findings"] = (
                    run["image_id"] == old["image_id"] == IMAGES[tool]
                    and old["candidate_sha256"] == BEFORE[name][0 if tool == "packtools" else 1]
                    and run["candidate_sha256"] == FINAL[name][0 if tool == "packtools" else 1]
                    and run["findings"] == old["findings"]
                    and run["counts"]
                    == dict(Counter(f["response"] for f in run["findings"]))
                    == {"warning": 9 if first else 5}
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
    except (KeyError, ValueError, TypeError, StopIteration, OSError):
        checks["complete_evidence"] = False
    return {
        "passed": bool(checks) and all(checks.values()),
        "checks": checks,
        "formal_xml_approved": False,
        "scientific_fidelity_approved": False,
        "active_application_changed": False,
        "remaining_glyph_reviews": 5,
    }


def inputs(path=REPORT):
    return json.loads(path.read_bytes()), json.loads(
        (REPORTS / "vh1-formula-links-linux-v1.json").read_bytes()
    )


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
