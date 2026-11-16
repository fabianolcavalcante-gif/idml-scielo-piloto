"""Close only the qualified VH-05 history false positive, not whole XML/release."""

import hashlib
import json
from collections import Counter
from pathlib import Path

from ops.gate_vh1_doctype import code_matches
from ops.gate_vh1_metadata import FINAL
from ops.history_compat import NATIVE_CONFIG_SHA256, POLICY, SECTION_SHA256, SPEC_SHA256, SPEC_URL
from ops.prepare_vh1_history_images import FILES
from ops.qualify_vh1_history_images import IMAGES
from ops.qualify_vh1_metadata import CHANGED, CODE
from ops.vh1_source_evolution import source_matches

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "benchmarks/qualification/reports"
PLAN_SHA256 = "0d094d45486eeba66387a0ad2120f17ea339eacfb8459b42df620d269deba1fa"
REMOVED = {
    "packtools": {
        "history-required-date-rev-recd-history-date-date-type-rev-recd-exist-3e953fb9b41f",
        "history-required-date-rev-request-history-date-date-type-rev-request-exist-4f1d58f9fc9d",
    },
    "spsvalidator": {
        "history-history-required-date-rev-recd-history-date-date-type-rev-recd-exist-ef912a098978",
        "history-history-required-date-rev-request-history-date-date-type-rev-request-exist-23889e3b4763",
    },
}
PROBES = {
    "absent_optional_revision",
    "present_complete_revisions",
    "present_year_only_revision",
    "missing_received",
    "missing_accepted",
    "missing_pub_still_required",
    "revision_without_year",
    "request_without_year",
    "incomplete_received",
    "unknown_type",
    "missing_type",
    "duplicate_history",
    "translation_missing_received",
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def evaluate(report, previous, images, original_images, registry, old_registry, reader):
    checks = {}
    try:
        plan = report["qualification"]
        checks["not_release"] = (
            report["formal_xml_approved"] is False
            and report["active_application_changed"] is False
            and plan["formal_xml_approved"] is False
            and plan["active_application_changed"] is False
            and images["active_application_changed"] is False
            and plan["history_reconversion_performed"] is False
        )
        checks["plan_and_specification"] = (
            report["version"] == "vh1-history-linux-1.0"
            and report["plan_sha256"] == PLAN_SHA256
            and plan["history_baseline_plan_sha256"] == previous["plan_sha256"]
            and plan["history_specification"]["sha256"] == SPEC_SHA256
            and plan["history_specification"]["history_sha256"] == SECTION_SHA256
            and plan["history_specification"]["runtime_network"] is False
            and plan["history_specification"]["url"]
            == SPEC_URL.replace("/edit#heading=h.history", "/export?format=txt")
        )
        prior = previous["qualification"]
        checks["baseline_unchanged"] = (
            all(
                plan[k] == v
                for k, v in prior.items()
                if k not in {"registry_sha256", "code_sha256"}
            )
            and {k: v for k, v in plan["code_sha256"].items() if k != "run_vh1_history_linux.py"}
            == prior["code_sha256"]
        )
        sources = {
            **plan["source_sha256"],
            **plan["history_source_sha256"],
            **images["source_sha256"],
        }
        checks["current_sources"] = (
            set(plan["source_sha256"]) == set(CHANGED)
            and set(plan["history_source_sha256"])
            == {
                "ops/history_compat.py",
                "ops/history_validator_adapter.py",
                "ops/probe_vh1_history.py",
                "ops/prepare_vh1_history_qualification.py",
                "ops/run_vh1_history_linux.py",
                "ops/collect_vh1_history_spec.py",
                "deploy/Dockerfile.validator-history-compat",
            }
            and set(images["source_sha256"])
            == {
                *FILES.values(),
                "ops/probe_vh1_history.py",
                "ops/qualify_vh1_history_images.py",
            }
            and code_matches(
                plan["code_sha256"],
                {
                    **CODE,
                    "run_vh1_history_linux.py": "ops/run_vh1_history_linux.py",
                },
                reader,
            )
            and all(source_matches(p, digest, reader) for p, digest in sources.items())
        )
        checks["registry"] = (
            plan["registry_sha256"] == sha(reader("config/validator-registry-vh1-history.json"))
            and registry["xpm"] == old_registry["xpm"]
            and registry["profile_id"] == old_registry["profile_id"]
        )
        active = {v["name"]: v for v in registry["validators"] if v["channel"] == "active"}
        rollback = {v["name"]: v for v in registry["validators"] if v["channel"] == "rollback"}
        parents = {v["name"]: v for v in old_registry["validators"] if v["channel"] == "active"}
        checks["images_set"] = set(active) == set(images["validators"]) == set(IMAGES)
        for tool, image in IMAGES.items():
            item = images["validators"][tool]
            old_runtime = original_images["validators"][tool]["runtime"]
            native = item["native_probe"]
            wrappers = item["runtime"]["wrappers_sha256"]
            checks[tool + "/image"] = (
                item["image_id"] == active[tool]["image_id"] == image
                and item["parent_image_id"] == parents[tool]["image_id"]
                and rollback[tool] == {**parents[tool], "channel": "rollback"}
                and {k: v for k, v in active[tool].items() if k not in {"image_id", "dockerfile"}}
                == {k: v for k, v in parents[tool].items() if k not in {"image_id", "dockerfile"}}
                and item["runtime"]["package_trees"] == old_runtime["package_trees"]
                and all(
                    wrappers[k] == v
                    for k, v in old_runtime["wrappers_sha256"].items()
                    if k != tool + "_validate.py"
                )
                and wrappers["scoped_validator_adapter.py"]
                == old_runtime["wrappers_sha256"][tool + "_validate.py"]
                and wrappers["history_compat.py"] == sha(reader("ops/history_compat.py"))
                and wrappers[tool + "_validate.py"]
                == sha(reader("ops/history_validator_adapter.py"))
            )
            checks[tool + "/native_probes"] = (
                native["passed"] is True
                and native["native_config_sha256"] == NATIVE_CONFIG_SHA256
                and set(native["checks"]) == PROBES
                and all(p["passed"] is True for p in native["checks"].values())
            )
        checks["cases"] = len(report["cases"]) == 2 and {c["case"] for c in report["cases"]} == set(
            FINAL
        )
        for case in report["cases"]:
            name = case["case"]
            old_case = next(c for c in previous["cases"] if c["case"] == name)
            checks[name + "/tools"] = len(case["validators"]) == 2 and {
                r["name"] for r in case["validators"]
            } == set(IMAGES)
            for run in case["validators"]:
                tool = run["name"]
                old = next(r for r in old_case["validators"] if r["name"] == tool)
                expected = [r for r in old["findings"] if r["code"] not in REMOVED[tool]]
                counts = {"error": 3, "warning": 9} if name == "esa-e20240086" else {"warning": 5}
                checks[name + "/" + tool + "/findings"] = (
                    run["image_id"] == IMAGES[tool]
                    and run["candidate_sha256"]
                    == old["candidate_sha256"]
                    == FINAL[name][0 if tool == "packtools" else 1]
                    and run["findings"] == expected
                    and len(old["findings"]) - len(expected) == 2
                    and run["counts"] == counts == dict(Counter(f["response"] for f in expected))
                    and run["authority_evidence"] == old["authority_evidence"]
                )
                proof = run["history_policy_evidence"]
                invocations = proof["invocations"]
                checks[name + "/" + tool + "/policy"] = (
                    proof["policy"] == POLICY
                    and proof["candidate_sha256"] == run["candidate_sha256"]
                    and proof["native_config_sha256"] == NATIVE_CONFIG_SHA256
                    and proof["specification_sha256"] == SPEC_SHA256
                    and proof["section_sha256"] == SECTION_SHA256
                    and proof["specification_url"] == SPEC_URL
                    and proof["absence_is_not_proof_of_no_revision"] is True
                    and len(invocations) == 1
                    and invocations[0]["only_revision_presence_changed"] is True
                    and invocations[0]["effective_failures"] == []
                    and sorted(invocations[0]["default_failures"], key=lambda r: r["rule"])
                    == [
                        {"rule": "required date: rev-recd", "outcome": "CRITICAL"},
                        {"rule": "required date: rev-request", "outcome": "CRITICAL"},
                    ]
                )
    except (KeyError, ValueError, TypeError, StopIteration, OSError):
        checks["complete_evidence"] = False
    return {
        "passed": bool(checks) and all(checks.values()),
        "checks": checks,
        "formal_xml_approved": False,
        "active_application_changed": False,
    }


def inputs():
    return (
        json.loads((REPORTS / "vh1-history-linux-v1.json").read_bytes()),
        json.loads((REPORTS / "vh1-metadata-linux-v7.json").read_bytes()),
        json.loads((REPORTS / "vh1-history-images-v1.json").read_bytes()),
        json.loads((REPORTS / "vh1-scoped-images-v1.json").read_bytes()),
        json.loads((ROOT / "config/validator-registry-vh1-history.json").read_bytes()),
        json.loads((ROOT / "config/validator-registry-vh1-scoped.json").read_bytes()),
    )


def main():
    result = evaluate(*inputs(), lambda p: (ROOT / p).read_bytes())
    print(json.dumps(result, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
