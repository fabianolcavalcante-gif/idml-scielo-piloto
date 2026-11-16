"""Source-bound acceptance of scoped VH-04 integration; never release approval."""

import hashlib
import json
from pathlib import Path

from ops.gate_vh1_doctype import code_matches
from ops.gate_vh1_editorial import CASES, PACKAGES
from ops.prepare_vh1_scoped_images import FILES
from ops.prepare_vh1_scoped_socket import SOURCES

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "benchmarks/qualification/reports"
SCOPES = {
    "esa-e20240086": "587c7187f9bc338b3ed0b951bd38906edd15ba45bb010a46316b2c43eb5d4808",
    "esa-e20240135": "a690cbabbcbeb099dd47597cc5d30fbde828ed6c54082d1f1a4d640b290c22a8",
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def evaluate(report, images, baseline, registry_bytes, reader):
    checks = {}
    try:
        registry = json.loads(registry_bytes)
        tools = {v["name"]: v for v in registry["validators"] if v["channel"] == "active"}
        checks["scope"] = (
            report["version"] == "vh1-scoped-socket-1.0"
            and report["synthetic_scopes_only"] is True
            and report["active_application_changed"] is False
            and report["formal_xml_approved"] is False
            and images["active_application_changed"] is False
        )
        checks["registry"] = report["registry_sha256"] == sha(registry_bytes)
        checks["current_socket_code"] = code_matches(report["code_sha256"], SOURCES, reader)
        checks["current_image_code"] = images["source_sha256"] == {
            path: sha(reader(path)) for path in FILES.values()
        }
        checks["images"] = (
            set(images["validators"]) == set(tools) == {"packtools", "spsvalidator"}
            and images["native_libraries_unchanged"] is True
            and images["wrapper_sources_verified"] is True
        )
        for name, item in images["validators"].items():
            runtime = item["runtime"]
            prior = baseline["validators"][name]["runtime"]
            checks[name + "/native"] = (
                item["image_id"] == tools[name]["image_id"]
                and runtime["package_trees"] == prior["package_trees"]
                and runtime["packages"] == prior["packages"]
            )
            checks[name + "/wrappers"] = all(
                runtime["wrappers_sha256"][
                    name + "_validate.py" if target == "scoped_validator_adapter.py" else target
                ]
                == sha(reader(path))
                for target, path in FILES.items()
                if target != "Dockerfile"
            )
        cases = report["cases"]
        checks["exact_cases"] = len(cases) == 2 and {c["case"] for c in cases} == set(CASES)
        for case in cases:
            name, assessment = case["case"], case["assessment"]
            xml_hash, orcids = CASES[name]
            prefix = name + "/"
            checks[prefix + "assessment"] = (
                assessment["xml_sha256"] == xml_hash
                and assessment["package_sha256"] == PACKAGES[name]
                and assessment["complete"] is False
                and assessment["ready_for_scielo"] is False
                and assessment["production_activation_authorized"] is False
                and assessment["state"] == "blocked"
                and assessment["xpm"]["attested"] is False
            )
            runs = assessment["external_runs"]
            checks[prefix + "tools"] = len(runs) == 2 and {r["name"] for r in runs} == set(tools)
            bindings = []
            for run in runs:
                tool = run["name"]
                evidence = run["authority_verification"]
                binding = evidence["binding"]
                bindings.append(binding)
                checks[prefix + tool + "/run"] = (
                    run["status"] == "completed"
                    and run["failure_code"] is None
                    and run["passed"] is False
                    and run["unavailable_external_checks"] == []
                    and run["tool_sha256"] == tools[tool]["image_id"].removeprefix("sha256:")
                    and run["version"] == tools[tool]["version"]
                    and run["candidate_sha256"]
                    == (xml_hash if tool == "packtools" else PACKAGES[name])
                )
                checks[prefix + tool + "/evidence"] = (
                    evidence["version"] == "scoped-authority-evidence-1.0"
                    and binding["scope_sha256"] == SCOPES[name]
                    and evidence["expected"]
                    == {"doi": 1, "issue": 1, "section": 1, "orcid": orcids}
                    and evidence["checks"]
                    == {
                        "doi": [True],
                        "issue": [True],
                        "section": [True],
                        "orcid": [True] * orcids,
                        "orcid_reasons": ["public_registry_and_crossref_author_match"] * orcids,
                    }
                    and all(
                        type(value) is bool
                        for key, values in evidence["checks"].items()
                        if key != "orcid_reasons"
                        for value in values
                    )
                )
            checks[prefix + "same_authority"] = len(bindings) == 2 and bindings[0] == bindings[1]
        negatives = report["negative_controls"]
        checks["negative_controls"] = set(negatives) == {
            "foreign-tenant",
            "foreign-resource",
            "changed-xml",
            "revoked",
            "expired",
        } and all(
            result["not_approved"] is True
            and result["statuses"]
            == {
                "packtools": "unavailable",
                "spsvalidator": "completed" if name == "changed-xml" else "unavailable",
            }
            for name, result in negatives.items()
        )
    except (KeyError, TypeError, ValueError, OSError):
        checks["evidence_readable"] = False
    return {
        "passed": bool(checks) and all(checks.values()),
        "checks": checks,
        "scope": "VH-04 scoped candidate integration; not deployed end-to-end qualification",
        "formal_xml_approved": False,
    }


def main():
    result = evaluate(
        json.loads((REPORTS / "vh1-scoped-socket-v1.json").read_bytes()),
        json.loads((REPORTS / "vh1-scoped-images-v1.json").read_bytes()),
        json.loads((REPORTS / "vh1-lot2-baseline-v1.json").read_bytes()),
        (ROOT / "config/validator-registry-vh1-scoped.json").read_bytes(),
        lambda path: (ROOT / path).read_bytes(),
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
