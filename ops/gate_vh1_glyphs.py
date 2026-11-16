"""Verify the native source-glyph checkpoint without granting scientific approval."""

import argparse
import json
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from ops.gate_vh1_doctype import code_matches
from ops.gate_vh1_formula_revisions import FINAL as BEFORE
from ops.gate_vh1_formula_revisions import REPORT as PREVIOUS
from ops.qualify_vh1_glyphs import ROOT, RUNNER, SOURCES, sha
from ops.qualify_vh1_history_images import IMAGES
from ops.vh1_source_evolution import source_matches

REPORT = ROOT / "benchmarks/qualification/reports/vh1-glyphs-linux-v1.json"
PLAN = "77f9b158d42d5dcc3092453b2f4c0aca0cff21b9859b0aaf10d7308df737a878"
CANONICAL_PLAN = "244667080c1c571566db98601666399525ecc39b31a569f85495e910ccc66f9d"
FINAL = {
    "esa-e20240086": BEFORE["esa-e20240086"],
    "esa-e20240135": (
        "84ab07204bd7debff2fc9f4c1623926f1637a722d12cbe964f4d5f4b178e899e",
        "e355adc2e049c7fc38e9fadbda93e739efdca5b833aac6bd200d3210bafa5d10",
    ),
}


def evaluate(report, previous, reader):
    checks = {}
    try:
        plan = report["qualification"]
        checks["pinned_plan"] = (
            report["version"] == "vh1-history-linux-1.0"
            and report["transport"] == "scoped-broker-executor-not-socket"
            and plan["version"] == "vh1-glyphs-local-1.0"
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
            and plan["autonomous_application"] is False
            and plan["human_review_required"] is True
            and plan["remaining_ambiguous_glyphs"] == 1
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
            first = name.endswith("86")
            detail = plan["cases"][name]
            old_case = next(c for c in previous["cases"] if c["case"] == name)
            checks[name + "/preservation"] = (
                (detail["before_xml_sha256"], detail["before_package_sha256"]) == BEFORE[name]
                and (detail["xml_sha256"], detail["package_sha256"]) == FINAL[name]
                and detail["files"]["candidate.xml"] == FINAL[name][0]
                and detail["files"]["candidate.zip"] == FINAL[name][1]
                and detail["files"]["formula_catalog.json"] == detail["catalog_sha256"]
                and detail["delta"]["all_other_xml_unchanged"] is True
                and detail["delta"]["formula_count"] == (17 if first else 43)
                and len(detail["delta"]["changes"]) == (0 if first else 4)
                and len(detail["delta"]["source_normal_positions"]) == (0 if first else 14)
                and detail["offline_valid"] is True
                and detail["deterministic"] is True
                and detail["unchanged_assets"]
                == previous["qualification"]["cases"][name]["unchanged_assets"]
            )
            started = datetime.fromisoformat(plan["created_at"])
            collected = detail["fresh_authorities"]
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
