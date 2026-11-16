"""Requalify V10 after scoped worker/socket changes using freshly executed focused tests."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree

from ops.gate_phase7_v10 import (
    _api_contract_gate,
    _interface_and_degraded_gate,
    _job_contract_gate,
    _package_integrity_gate,
)

ROOT = Path(__file__).resolve().parents[1]


def main():
    junit = ROOT / "tmp/vh1-scoped-workflow.xml"
    suite = ElementTree.parse(junit).getroot().find("testsuite")  # noqa: S314 - local pytest artifact
    if (
        suite is None
        or int(suite.get("tests", "0")) < 100
        or any(int(suite.get(k, "0")) for k in ("failures", "errors", "skipped"))
    ):
        raise ValueError("focused_tests_incomplete")
    if sum(c.get("name", "").startswith("test_v10_") for c in suite.findall("testcase")) != 3:
        raise ValueError("workflow_evidence_missing")
    gates = {
        key: check()
        for key, check in (
            ("api", _api_contract_gate),
            ("jobs", _job_contract_gate),
            ("package", _package_integrity_gate),
            ("interface", _interface_and_degraded_gate),
        )
    }
    prior = ROOT / "benchmarks/qualification/reports/v10-operational-workflow-vh1-lot1-v1.json"
    report = json.loads(prior.read_bytes())
    sources = set(report["source_sha256"]) | {
        "src/idml_foundation/services/scoped_validator_transport.py",
        "src/idml_foundation/services/validation_scope.py",
        "ops/scoped_validator_broker.py",
        "ops/scoped_authority_transport.py",
        "ops/scoped_validator_adapter.py",
        "ops/provision_scoped_authorities.py",
        "tests/test_scoped_authority_transport.py",
        "tests/test_scoped_authority_provision.py",
        "tests/test_scoped_validator_transport.py",
    }
    report.update(
        executed_at=datetime.now(UTC).isoformat(),
        requalification_of=prior.name,
        previous_report_sha256=hashlib.sha256(prior.read_bytes()).hexdigest(),
        focused_tests=int(suite.get("tests")),
        full_tests=None,
        line_coverage_percent=None,
        focused_junit_sha256=hashlib.sha256(junit.read_bytes()).hexdigest(),
        contract_gates=gates,
        source_sha256={
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in sorted(sources)
        },
        scope="V10 and scoped validator worker/transport. No deployment or XML approval.",
    )
    target = ROOT / "benchmarks/qualification/reports/v10-operational-workflow-vh1-scoped-v1.json"
    with target.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
    print(json.dumps({"focused_tests": int(suite.get("tests")), "gates": gates}))


if __name__ == "__main__":
    main()
