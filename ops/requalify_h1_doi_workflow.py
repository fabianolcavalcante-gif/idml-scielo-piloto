"""New source-bound V10 evidence after verified focused tests; preserve prior report."""

import hashlib
import json
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
    junit = ROOT / "tmp/h1-doi-focused.xml"
    suite = ElementTree.parse(junit).getroot().find("testsuite")  # noqa: S314 - local pytest output
    if (
        suite is None
        or int(suite.get("tests", "0")) != 59
        or any(int(suite.get(key, "0")) for key in ("errors", "failures", "skipped"))
    ):
        raise ValueError("focused evidence incomplete")
    gates = {
        name: function()
        for name, function in (
            ("api", _api_contract_gate),
            ("jobs", _job_contract_gate),
            ("package", _package_integrity_gate),
            ("interface", _interface_and_degraded_gate),
        )
    }
    prior = ROOT / "benchmarks/qualification/reports/v10-operational-workflow-h1-external-v1.json"
    report = json.loads(prior.read_text(encoding="utf-8"))
    paths = set(report["source_sha256"]) | {
        "src/idml_foundation/release/validation_engine.py",
        "ops/validator_adapter_common.py",
        "ops/external_verification.py",
        "tests/test_external_verification.py",
        "src/idml_foundation/release/doi_snapshot.py",
        "tests/test_doi_snapshot.py",
    }
    report.update(
        executed_at="2026-09-30",
        requalification_of=prior.name,
        previous_report_sha256=hashlib.sha256(prior.read_bytes()).hexdigest(),
        full_tests=None,
        line_coverage_percent=None,
        focused_tests=59,
        focused_junit_sha256=hashlib.sha256(junit.read_bytes()).hexdigest(),
        source_sha256={
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in sorted(paths)
        },
        contract_gates=gates,
        scope="V10 workflows and formal diagnostics re-executed locally (59 focused tests). "
        "Full regression recorded separately; no formal XML or deployment approval.",
    )
    path = ROOT / "benchmarks/qualification/reports/v10-operational-workflow-h1-doi-v1.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"focused_tests": 59, "contract_gates": list(gates), "report": path.name}))


if __name__ == "__main__":
    main()
