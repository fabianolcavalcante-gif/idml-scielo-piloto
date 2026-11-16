"""Verify VH-06 literal-link evidence; never approve scientific fidelity or release."""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from ops.gate_vh1_doctype import code_matches
from ops.gate_vh1_metadata import FINAL as BEFORE
from ops.qualify_vh1_formula_links import EXPECTED, RUNNER, SOURCES
from ops.qualify_vh1_history_images import IMAGES
from ops.vh1_source_evolution import source_matches

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "benchmarks/qualification/reports"
REPORT = REPORTS / "vh1-formula-links-linux-v1.json"
PLAN_SHA256 = "49b9e1154cd87f3ae26dd6c59d48f6ec9f0639d028f9b9077b965d40ec2129e5"
PLAN_CANONICAL_SHA256 = "a88c74dd4f9ef12523552c2da324989c367a86db416d66f955a61f625b20b54b"
FINAL = {
    "esa-e20240086": (
        "297d660afa87e34ca530bdf0c22d8f9c1f5623461c8cd425eaa3b3177a119b3d",
        "6b2ba60422107ad023893995b6149a1fe5d3926daf9cc679532bb27dc0f5d3be",
    ),
    "esa-e20240135": BEFORE["esa-e20240135"],
}
REMOVED = {
    "packtools": {
        "id-and-rid-disp-formula-id-e-formula-0e118109-65d4-56f5-8082-3ea1436f0d10-is-linked-to-xref-disp-formula-id-match-2f146ebcc8e7",
        "id-and-rid-disp-formula-id-e-formula-44665dfc-6476-50ef-a786-f9a5fe6a51f7-is-linked-to-xref-disp-formula-id-match-4bbeca1fa4c8",
        "id-and-rid-disp-formula-id-e-formula-500818b8-d682-5149-893e-c989336435b0-is-linked-to-xref-disp-formula-id-match-c0eb2f7a55f7",
    },
    "spsvalidator": {
        "id-and-rid-id-and-rid-disp-formula-id-e-formula-0e118109-65d4-56f5-8082-3ea1436f0d10-is-linked-to-xref-disp-formula-id-m-087e8465041c",
        "id-and-rid-id-and-rid-disp-formula-id-e-formula-44665dfc-6476-50ef-a786-f9a5fe6a51f7-is-linked-to-xref-disp-formula-id-m-a9e280337564",
        "id-and-rid-id-and-rid-disp-formula-id-e-formula-500818b8-d682-5149-893e-c989336435b0-is-linked-to-xref-disp-formula-id-m-01880654cbe7",
    },
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def evaluate(report, previous, registry, reader):
    checks = {}
    try:
        plan = report["qualification"]
        checks["not_release"] = (
            all(
                obj[key] is False
                for obj in (report, plan)
                for key in ("active_application_changed", "formal_xml_approved")
            )
            and plan["gold_read"] is False
            and plan["catalog_values_changed"] is False
        )
        checks["pinned_plan"] = (
            report["version"] == "vh1-history-linux-1.0"
            and plan["version"] == "vh1-formula-links-local-1.0"
            and report["plan_sha256"] == PLAN_SHA256
            and sha(json.dumps(plan, indent=2, sort_keys=True).encode()) == PLAN_CANONICAL_SHA256
            and report["transport"] == "scoped-broker-executor-not-socket"
        )
        checks["current_sources"] = (
            set(plan["source_sha256"]) == set(SOURCES)
            and all(source_matches(p, h, reader) for p, h in plan["source_sha256"].items())
            and code_matches(plan["code_sha256"], RUNNER, reader)
        )
        checks["registry"] = (
            plan["registry_sha256"] == sha(reader("config/validator-registry-vh1-history.json"))
            and {
                v["name"]: v["image_id"] for v in registry["validators"] if v["channel"] == "active"
            }
            == IMAGES
        )
        checks["cases"] = len(report["cases"]) == 2 and {c["case"] for c in report["cases"]} == set(
            FINAL
        )
        for case in report["cases"]:
            name = case["case"]
            details = plan["cases"][name]
            old_case = next(c for c in previous["cases"] if c["case"] == name)
            expected_links = (
                [
                    {"paragraph_id": p, "target_id": t, "anchor_sha256": sha(s.encode())}
                    for p, t, s in EXPECTED
                ]
                if name == "esa-e20240086"
                else []
            )
            checks[name + "/conversion"] = (
                (details["xml_sha256"], details["package_sha256"]) == FINAL[name]
                and details["before_xml_sha256"] == BEFORE[name][0]
                and details["offline_valid"] is True
                and details["deterministic"] is True
                and details["delta"]
                == {
                    "added_links": expected_links,
                    "all_other_xml_unchanged": True,
                    "mathml_unchanged": True,
                }
                and details["files"]["candidate.xml"] == FINAL[name][0]
                and details["files"]["candidate.zip"] == FINAL[name][1]
            )
            checks[name + "/tools"] = len(case["validators"]) == 2 and {
                r["name"] for r in case["validators"]
            } == set(IMAGES)
            for run in case["validators"]:
                tool = run["name"]
                old = next(r for r in old_case["validators"] if r["name"] == tool)
                removed = REMOVED[tool] if name == "esa-e20240086" else set()
                expected = [f for f in old["findings"] if f["code"] not in removed]
                key = name + "/" + tool
                checks[key + "/findings"] = (
                    run["image_id"] == old["image_id"] == IMAGES[tool]
                    and old["candidate_sha256"] == BEFORE[name][0 if tool == "packtools" else 1]
                    and run["candidate_sha256"] == FINAL[name][0 if tool == "packtools" else 1]
                    and {f["code"] for f in old["findings"] if f["code"] in removed} == removed
                    and run["findings"] == expected
                    and len(old["findings"]) - len(expected) == len(removed)
                    and run["counts"]
                    == dict(Counter(f["response"] for f in expected))
                    == {"warning": 9 if name == "esa-e20240086" else 5}
                )
                checks[key + "/history"] = run["history_policy_evidence"] == {
                    **old["history_policy_evidence"],
                    "candidate_sha256": run["candidate_sha256"],
                }
                checks[key + "/authorities"] = run["authority_evidence"] == {
                    **old["authority_evidence"],
                    "binding": {
                        "bundle_sha256": details["files"]["incoming/manifest.json"],
                        "grant_sha256": details["files"]["grant.json"],
                        "scope_sha256": details["scope_sha256"],
                    },
                }
    except (KeyError, ValueError, TypeError, StopIteration, OSError):
        checks["complete_evidence"] = False
    return {
        "passed": bool(checks) and all(checks.values()),
        "checks": checks,
        "formal_xml_approved": False,
        "scientific_fidelity_approved": False,
        "active_application_changed": False,
    }


def inputs(path=REPORT):
    return (
        json.loads(path.read_bytes()),
        json.loads((REPORTS / "vh1-history-linux-v1.json").read_bytes()),
        json.loads((ROOT / "config/validator-registry-vh1-history.json").read_bytes()),
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--publish", type=Path, help="Verify and preserve a new native report once")
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
