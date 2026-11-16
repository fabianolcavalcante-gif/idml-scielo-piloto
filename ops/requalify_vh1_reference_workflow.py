"""Reexecute workflow and robustness checks for the literal bibliographic field parser."""

import json
from datetime import UTC, datetime
from xml.etree import ElementTree

from ops.gate_vh1_references import REPORT, ROOT, sha
from ops.qualify_vh1_references import SOURCES
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
    junit = ROOT / "tmp/vh1-reference-focused.xml"
    suite = ElementTree.parse(junit).getroot().find("testsuite")  # noqa: S314 - local pytest output
    if suite is None or any(int(suite.get(k, "0")) for k in ("failures", "errors", "skipped")):
        raise ValueError("focused_tests_incomplete")
    for module, minimum in (
        ("test_phase7_v10_workflow", 3),
        ("test_phase7_v11_robustness", 9),
        ("test_idml_fidelity_v03", 3),
        ("test_formula_catalog", 5),
        ("test_formula_source_revisions", 35),
        ("test_reference_boundaries", 32),
        ("test_vh1_reference_delta", 16),
        ("test_vh1_reference_gate", 32),
        ("test_vh1_source_evolution", 7),
        ("test_vh1_reference_adjudication", 8),
    ):
        if sum(module in c.get("classname", "") for c in suite.findall("testcase")) < minimum:
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
    reports = REPORT.parent
    for gate, stem in (("v10", "v10-operational-workflow"), ("v11", "v11-robustness-mutation")):
        prior = reports / (stem + "-vh1-glyphs-v1.json")
        report = json.loads(prior.read_bytes())
        sources = (
            set(report["source_sha256"])
            | set(SOURCES)
            | {
                "ops/gate_vh1_references.py",
                "ops/requalify_vh1_reference_workflow.py",
                "tests/test_reference_boundaries.py",
                "tests/test_vh1_source_evolution.py",
                "tests/test_vh1_reference_adjudication.py",
                "ops/audit_vh1_references.py",
                "tests/test_vh1_reference_delta.py",
                "tests/test_vh1_reference_gate.py",
            }
        )
        report.update(
            executed_at=datetime.now(UTC).isoformat(),
            requalification_of=prior.name,
            previous_report_sha256=sha(prior.read_bytes()),
            focused_tests=int(suite.get("tests")),
            focused_junit_sha256=sha(junit.read_bytes()),
            full_tests=None,
            line_coverage_percent=None,
            reference_current_checks=checks[gate],
            reference_native_report_sha256=sha(REPORT.read_bytes()),
            source_sha256={p: sha((ROOT / p).read_bytes()) for p in sorted(sources)},
            scope=(
                "Literal bibliographic field corrections; "
                "not scientific acceptance, deployment or release."
            ),
        )
        with (reports / (stem + "-vh1-references-v1.json")).open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2)
    print(json.dumps({"focused_tests": int(suite.get("tests")), "checks": checks}))


if __name__ == "__main__":
    main()
