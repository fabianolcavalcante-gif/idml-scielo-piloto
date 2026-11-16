"""Rerun operational/property checks after the formula-reference resolver change."""

import json
from datetime import UTC, datetime
from xml.etree import ElementTree

from ops.gate_vh1_formula_links import REPORT, REPORTS, ROOT, sha
from ops.qualify_vh1_formula_links import SOURCES
from ops.requalify_vh1_articlemeta_workflow import (
    _api_contract_gate,
    _fuzz_gate,
    _interface_and_degraded_gate,
    _job_contract_gate,
    _package_integrity_gate,
    _package_property_gate,
    _xml_and_unicode_property_gate,
)


def main():
    junit = ROOT / "tmp/vh1-formula-links-focused.xml"
    suite = ElementTree.parse(junit).getroot().find("testsuite")  # noqa: S314 - local pytest output
    if suite is None or any(int(suite.get(k, "0")) for k in ("failures", "errors", "skipped")):
        raise ValueError("focused_tests_incomplete")
    cases = suite.findall("testcase")
    for module, minimum in (
        ("test_phase7_v10_workflow", 3),
        ("test_phase7_v11_robustness", 9),
        ("test_formula_reference_links", 35),
        ("test_object_reference_resolver", 2),
        ("test_vh1_formula_delta", 18),
        ("test_vh1_formula_links_gate", 37),
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
    for gate, stem in (("v10", "v10-operational-workflow"), ("v11", "v11-robustness-mutation")):
        previous = REPORTS / (stem + "-vh1-articlemeta-v4.json")
        report = json.loads(previous.read_bytes())
        sources = (
            set(report["source_sha256"])
            | set(SOURCES)
            | {
                "tests/test_formula_reference_links.py",
                "tests/test_object_reference_resolver.py",
                "tests/test_vh1_formula_delta.py",
                "tests/test_vh1_formula_links_gate.py",
                "ops/gate_vh1_formula_links.py",
                "ops/requalify_vh1_formula_workflow.py",
            }
        )
        report.update(
            executed_at=datetime.now(UTC).isoformat(),
            requalification_of=previous.name,
            previous_report_sha256=sha(previous.read_bytes()),
            focused_tests=int(suite.get("tests")),
            focused_junit_sha256=sha(junit.read_bytes()),
            full_tests=None,
            line_coverage_percent=None,
            formula_links_current_checks=checks[gate],
            formula_links_native_report_sha256=sha(REPORT.read_bytes()),
            source_sha256={p: sha((ROOT / p).read_bytes()) for p in sorted(sources)},
            scope=(
                "Literal formula links; repeated operational and robustness checks. "
                "Not scientific fidelity, deployed E2E or release approval."
            ),
        )
        with (REPORTS / (stem + "-vh1-formula-links-v1.json")).open(
            "x", encoding="utf-8"
        ) as stream:
            json.dump(report, stream, indent=2)
    print(json.dumps({"focused_tests": int(suite.get("tests")), "gates": checks}))


if __name__ == "__main__":
    main()
