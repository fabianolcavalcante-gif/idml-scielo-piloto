"""Reexecute V10/V11 checks and bind immutable evidence to current metadata integration."""

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
from ops.gate_phase7_v11 import _fuzz_gate, _package_property_gate, _xml_and_unicode_property_gate
from ops.qualify_vh1_metadata import CHANGED

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "benchmarks/qualification/reports"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    junit = ROOT / "tmp/vh1-funding-focused.xml"
    suite = ElementTree.parse(junit).getroot().find("testsuite")  # noqa: S314 - local pytest output
    if (
        suite is None
        or int(suite.get("tests", "0")) < 198
        or any(int(suite.get(k, "0")) for k in ("failures", "errors", "skipped"))
    ):
        raise ValueError("focused_tests_incomplete")
    cases = suite.findall("testcase")
    for module, minimum in (
        ("test_phase7_v10_workflow", 3),
        ("test_phase7_v11_robustness", 9),
        ("test_articlemeta_dates", 36),
        ("test_articlemeta_orcids", 41),
        ("test_institution_locations", 40),
        ("test_verified_funding", 33),
        ("test_enrichment_bundles", 30),
    ):
        if sum(module in c.get("classname", "") for c in cases) < minimum:
            raise ValueError("required_tests_not_reexecuted")
    checks = {
        "v10": {
            "api": _api_contract_gate(),
            "jobs": _job_contract_gate(),
            "package": _package_integrity_gate(),
            "interface": _interface_and_degraded_gate(),
        },
        "v11": {
            "fuzz": _fuzz_gate(),
            "xml_unicode": _xml_and_unicode_property_gate(),
            "package": _package_property_gate(),
        },
    }
    for gate, previous, filename in (
        (
            "v10",
            "v10-operational-workflow-vh1-articlemeta-v3.json",
            "v10-operational-workflow-vh1-articlemeta-v4.json",
        ),
        (
            "v11",
            "v11-robustness-mutation-vh1-articlemeta-v3.json",
            "v11-robustness-mutation-vh1-articlemeta-v4.json",
        ),
    ):
        prior = REPORTS / previous
        report = json.loads(prior.read_bytes())
        sources = (
            set(report["source_sha256"])
            | set(CHANGED)
            | {
                "tests/test_articlemeta_dates.py",
                "tests/test_articlemeta_orcids.py",
                "tests/test_institution_locations.py",
                "tests/test_verified_funding.py",
                "ops/requalify_vh1_articlemeta_workflow.py",
            }
        )
        report.update(
            executed_at=datetime.now(UTC).isoformat(),
            requalification_of=previous,
            previous_report_sha256=sha(prior.read_bytes()),
            focused_tests=int(suite.get("tests")),
            focused_junit_sha256=sha(junit.read_bytes()),
            full_tests=None,
            line_coverage_percent=None,
            articlemeta_current_checks=checks[gate],
            source_sha256={name: sha((ROOT / name).read_bytes()) for name in sorted(sources)},
            scope=(
                "Dates, ORCIDs, institutional states and verified funding, scoped worker; "
                "not deployment or XML approval."
            ),
        )
        with (REPORTS / filename).open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2)
    print(json.dumps({"focused_tests": int(suite.get("tests")), "gates": checks}))


if __name__ == "__main__":
    main()
