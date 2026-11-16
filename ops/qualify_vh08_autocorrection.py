"""Export frozen VH-08 contracts and record focused tests; no application/AI execution."""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from lxml import etree

from idml_foundation.ai.autocorrection_contracts import (
    AutomationDecision,
    AutomationEvent,
    AutomationIntent,
)
from idml_foundation.ai.autocorrection_policy import policy_digest, policy_manifest

ROOT = Path(__file__).resolve().parents[1]
SOURCES = (
    "src/idml_foundation/ai/autocorrection_contracts.py",
    "src/idml_foundation/ai/autocorrection_policy.py",
    "src/idml_foundation/ai/security.py",
    "src/idml_foundation/ai/policy.py",
    "src/idml_foundation/ai/outputs.py",
    "src/idml_foundation/domain/canonical.py",
    "src/idml_foundation/domain/common.py",
    "src/idml_foundation/services/reviews.py",
    "profiles/esa-aop-1.1.json",
    "tests/test_autocorrection_policy.py",
    "tests/domain_helpers.py",
    "ops/qualify_vh08_autocorrection.py",
)


def outputs():
    return {
        "schemas/autocorrection-intent-1.0.schema.json": AutomationIntent.model_json_schema(),
        "schemas/autocorrection-decision-1.0.schema.json": AutomationDecision.model_json_schema(),
        "schemas/autocorrection-event-1.0.schema.json": AutomationEvent.model_json_schema(),
        "config/autocorrection-policy-vh1-1.0.json": policy_manifest(),
    }


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def export():
    for name, value in outputs().items():
        raw = (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()
        path = ROOT / name
        if path.exists():
            if path.read_bytes() != raw:
                raise ValueError("export_exists_with_different_content")
        else:
            with path.open("xb") as stream:
                stream.write(raw)


def report():
    junit = ROOT / "tmp/vh08-policy-tests.xml"
    coverage = ROOT / "tmp/vh08-policy-coverage.json"
    xml = etree.fromstring(
        junit.read_bytes(), etree.XMLParser(resolve_entities=False, no_network=True)
    )
    suite = xml.find("testsuite")
    if suite is None or any(
        int(suite.get(k, "-1")) != 0 for k in ("errors", "failures", "skipped")
    ):
        raise ValueError("focused_tests_incomplete")
    if int(suite.get("tests", "0")) != 102:
        raise ValueError("focused_test_matrix_changed")
    metrics = json.loads(coverage.read_bytes())["totals"]
    if metrics["missing_lines"] or metrics["missing_branches"]:
        raise ValueError("new_module_paths_not_exercised")
    return {
        "version": "vh08-policy-qualification-1.0",
        "created_at": datetime.now(UTC).isoformat(),
        "policy_sha256": policy_digest(),
        "source_sha256": {p: sha((ROOT / p).read_bytes()) for p in SOURCES},
        "export_sha256": {p: sha((ROOT / p).read_bytes()) for p in outputs()},
        "tests": {
            "passed": 102,
            "failures": 0,
            "skipped": 0,
            "junit_sha256": sha(junit.read_bytes()),
            "coverage_sha256": sha(coverage.read_bytes()),
            "new_modules_line_branch_percent": 100,
        },
        "scope": "deterministic-policy-synthetic-tests-only",
        "live_ai_called": False,
        "executor_implemented": False,
        "active_application_changed": False,
        "homologation_ready": False,
        "release_approved": False,
    }


def verify(proof):
    return (
        proof["policy_sha256"] == policy_digest()
        and set(proof["source_sha256"]) == set(SOURCES)
        and all(sha((ROOT / p).read_bytes()) == v for p, v in proof["source_sha256"].items())
        and set(proof["export_sha256"]) == set(outputs())
        and all(sha((ROOT / p).read_bytes()) == v for p, v in proof["export_sha256"].items())
        and all(json.loads((ROOT / p).read_bytes()) == v for p, v in outputs().items())
        and all(
            proof[k] is False
            for k in (
                "live_ai_called",
                "executor_implemented",
                "active_application_changed",
                "homologation_ready",
                "release_approved",
            )
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check", type=Path)
    args = parser.parse_args()
    if bool(args.output) == bool(args.check):
        parser.error("choose --output or --check")
    if args.check:
        passed = verify(json.loads(args.check.read_bytes()))
        print(json.dumps({"passed": passed, "release_approved": False}))
        raise SystemExit(0 if passed else 1)
    export()
    proof = report()
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(proof, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"tests": proof["tests"]["passed"], "release_approved": False}))
