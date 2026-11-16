"""Rebind V10 only after its workflows and VH1 trust-boundary tests actually pass."""

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
    junit = ROOT / "tmp/vh1-lot1-workflow.xml"
    suite = ElementTree.parse(junit).getroot().find("testsuite")  # noqa: S314 - local pytest
    if (
        suite is None
        or int(suite.get("tests", "0")) < 71
        or any(int(suite.get(key, "0")) for key in ("failures", "errors", "skipped"))
    ):
        raise ValueError("incomplete_vh1_workflow_evidence")
    cases = suite.findall("testcase")
    if sum(row.get("name", "").startswith("test_v10_") for row in cases) != 3:
        raise ValueError("missing_v10_workflow_evidence")
    gates = {
        name: function()
        for name, function in (
            ("api", _api_contract_gate),
            ("jobs", _job_contract_gate),
            ("package", _package_integrity_gate),
            ("interface", _interface_and_degraded_gate),
        )
    }
    prior = ROOT / "benchmarks/qualification/reports/v10-operational-workflow-h1-doi-v1.json"
    report = json.loads(prior.read_text(encoding="utf-8"))
    paths = set(report["source_sha256"]) | {
        "src/idml_foundation/services/source_authorization.py",
        "ops/provision_enrichment.py",
        "tests/test_source_authorization.py",
        "tests/test_enrichment_bundles.py",
        "tests/test_vh1_baseline.py",
    }
    report.update(
        executed_at=datetime.now(UTC).isoformat(),
        requalification_of=prior.name,
        previous_report_sha256=hashlib.sha256(prior.read_bytes()).hexdigest(),
        full_tests=None,
        line_coverage_percent=None,
        focused_tests=int(suite.get("tests")),
        focused_junit_sha256=hashlib.sha256(junit.read_bytes()).hexdigest(),
        source_sha256={
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in sorted(paths)
        },
        contract_gates=gates,
        scope="V10 workflows, formal diagnostics, VH1 source authorization and baseline tests. "
        "Local qualification only; no XML approval, remote catalog consent or deployment.",
    )
    target = ROOT / "benchmarks/qualification/reports/v10-operational-workflow-vh1-lot1-v1.json"
    with target.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"focused_tests": report["focused_tests"], "contract_gates": gates}))


if __name__ == "__main__":
    main()
