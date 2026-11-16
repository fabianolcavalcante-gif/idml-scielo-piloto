"""Source-bound acceptance of the native VH-04 experiment, NOT G-HOMOLOG."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "benchmarks/qualification/reports/vh1-editorial-linux-v1.json"
CASES = {
    "esa-e20240086": ("7081d302358f8c022114a0ebf568372af43e115bda38a748cc7c2ebbc1494ad0", 0),
    "esa-e20240135": ("1757cdb3a15b7fd44beb009e794ff812995eb59cd6e2c1eee2cabee15f9a9706", 4),
}
PACKAGES = {
    "esa-e20240086": "6b209eb4209e20aff17b653545f5553af3b562c9549ee34b5a2ca49671d9c4f6",
    "esa-e20240135": "e0be244b52eb524328a3f260c426617850bb057e3bbc9ecb82c43134929950c8",
}
SOURCES = {
    "editorial_authority.py",
    "editorial_authority_runtime.py",
    "probe_vh1_editorial.py",
    "doi_validation_evidence.py",
    "doi_package_binding.py",
    "doi_authority_transport.py",
    "validator_broker.py",
    "run_vh1_editorial_linux.py",
}


def evaluate(report, registry, code_reader):
    checks = {}
    checks["not_release_approval"] = (
        report.get("formal_xml_approved") is False and report.get("deployment_changed") is False
    )
    code = report.get("code_sha256", {})
    checks["current_code"] = set(code) == SOURCES and all(
        hashlib.sha256(code_reader(name)).hexdigest() == expected for name, expected in code.items()
    )
    images = {s["name"]: s["image_id"] for s in registry["validators"] if s["channel"] == "active"}
    cases = report.get("cases", [])
    checks["exact_cases"] = len(cases) == 2 and {c["case"] for c in cases} == set(CASES)
    for case in cases:
        name = case["case"]
        if name not in CASES:
            continue
        candidate, orcid_count = CASES[name]
        checks[name + "/tools"] = set(case["validators"]) == {"packtools", "spsvalidator"}
        for tool, result in case["validators"].items():
            prefix = name + "/" + tool + "/"
            evidence = result["native_context_evidence"]
            checks[prefix + "binding"] = (
                result["candidate_sha256"] == candidate
                and result["image_id"] == images.get(tool)
                and result["xml_unchanged"] is True
                and result["formal_xml_approved"] is False
                and result["package_sha256"] == (PACKAGES[name] if tool == "spsvalidator" else None)
            )
            checks[prefix + "positive"] = (
                result["native_doi_comparisons"] == 1
                and result["native_doi_passed"] is True
                and evidence["issue"] == [True]
                and evidence["section"] == [True]
                and evidence["orcid"] == [True] * orcid_count
                and len(evidence["orcid_reasons"]) == orcid_count
            )
            negatives = result["negative_controls"]
            checks[prefix + "negative"] = set(negatives) == {"issue", "section", "orcid"} and all(
                (
                    value.get("applicable") is True
                    and value.get("native_rejected") is True
                    and value.get("comparisons", 0) >= 1
                )
                if key != "orcid" or orcid_count
                else value == {"applicable": False}
                for key, value in negatives.items()
            )
            missing = result["unavailable_control"]
            expected = {"journal-issues", "journal-sections"}
            if orcid_count:
                expected.add("orcid-registry")
            observed = {
                f["code"].removeprefix("external-verification-unavailable-")
                for f in missing["result"]["findings"]
                if f["response"] == "blocking"
            }
            checks[prefix + "unavailable"] = observed == expected and all(
                missing["native_evidence"][key] == [False] * count
                for key, count in (("issue", 1), ("section", 1), ("orcid", orcid_count))
            )
    return {
        "passed": bool(checks) and all(checks.values()),
        "checks": checks,
        "scope": "native VH-04 qualification only; transport/deployment remain pending",
        "formal_xml_approved": False,
    }


def main():
    report = json.loads(REPORT.read_bytes())
    registry = json.loads((ROOT / "config/validator-registry-vh1.json").read_bytes())
    result = evaluate(report, registry, lambda n: (ROOT / "ops" / n).read_bytes())
    print(json.dumps(result, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
