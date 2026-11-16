"""Verify the native bibliographic-field checkpoint without granting scientific approval."""

import argparse
import json
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from ops.gate_vh1_doctype import code_matches
from ops.gate_vh1_glyphs import FINAL as BEFORE
from ops.gate_vh1_glyphs import REPORT as PREVIOUS
from ops.qualify_vh1_history_images import IMAGES
from ops.qualify_vh1_references import CONTRACT, ROOT, RUNNER, SOURCES, sha

REPORT = ROOT / "benchmarks/qualification/reports/vh1-references-linux-v1.json"
PLAN = "59153bcd5b79be67dd456f586c80cec95423bdeff7e9838d72098844c5eca564"
CANONICAL_PLAN = "8489880e9a3c0ea1cf994d81e6d4ea8a797a9e39528fb60eeab23d17ab9e5295"
FINAL = {
    "esa-e20240086": (
        "aeaac3caa534d442b13d67881b67a650bb42c5c93f6184dee8fc4a1225e54e63",
        "2c53550ad878f459356505f407567b25b368176114018e0eca9e6b91328cf55b",
    ),
    "esa-e20240135": (
        "ccc0553baa5c11d17b7ce1fd47d7e4da766a59543c2ae8e2bc41d2269ff51992",
        "146f934528744f5c048b5e5282018f4cf840bd5fb74fb24e9948ba71c173e025",
    ),
}
ADDITIONAL_WARNING = {
    "packtools": {
        "code": (
            "reference-element-citation-versus-mixed-citation-element-citation-match-d18501a6974d"
        ),
        "message": (
            "warning reported by rule reference-element-citation-versus-mixed-citation-"
            "element-citation-match-d18501a6974d"
        ),
        "path": "locator-sha256:84393add8c489d33569360efd1bcb5f70ed5a22408127d241c751e5ea345eb7c",
        "response": "warning",
    },
    "spsvalidator": {
        "code": (
            "reference-reference-element-citation-versus-mixed-citation-"
            "element-citation-match-dcd31799e4f0"
        ),
        "message": (
            "warning reported by rule reference-reference-element-citation-versus-mixed-citation-"
            "element-citation-match-dcd31799e4f0"
        ),
        "response": "warning",
    },
}


def evaluate(report, previous, reader):
    from ops.vh1_source_evolution import source_matches

    checks = {}
    try:
        plan = report["qualification"]
        checks["pinned_plan"] = (
            report["version"] == "vh1-history-linux-1.0"
            and report["transport"] == "scoped-broker-executor-not-socket"
            and plan["version"] == "vh1-references-local-1.0"
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
            and all(source_matches(p, h, reader) for p, h in plan["source_sha256"].items())
            and code_matches(plan["code_sha256"], RUNNER, reader)
            and plan["registry_sha256"] == sha(reader("config/validator-registry-vh1-history.json"))
        )
        contract = json.loads(reader(CONTRACT))
        checks["contract"] = (
            contract["gold_used"] is False and contract["scientific_fidelity_approved"] is False
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
                and detail["delta"]["reference_count"] == (52 if first else 35)
                and detail["delta"]["fields"] == contract["cases"][name]
                and detail["source_idml_sha256"] == contract["source_idml_sha256"][name]
                and detail["delta"]["changed_references"] == (12 if first else 1)
                and detail["delta"]["mixed_citations_unchanged"] is True
                and detail["catalog_sha256"]
                == previous["qualification"]["cases"][name]["catalog_sha256"]
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
                    and Counter(json.dumps(f, sort_keys=True) for f in run["findings"])
                    == Counter(
                        json.dumps(f, sort_keys=True)
                        for f in old["findings"] + ([] if first else [ADDITIONAL_WARNING[tool]])
                    )
                    and run["counts"]
                    == dict(Counter(f["response"] for f in run["findings"]))
                    == {"warning": 9 if first else 6}
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
        "additional_reference_access_date_warning": True,
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
