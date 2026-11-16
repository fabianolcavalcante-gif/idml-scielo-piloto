"""Fresh workflow/robustness runs, bound to the journal/compatibility increment."""

import json
from datetime import UTC, datetime
from xml.etree import ElementTree

from ops.gate_vh1_journal_metadata import REPORT, ROOT, evaluate, inputs, sha
from ops.qualify_vh1_journal_metadata import SOURCES
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
    junit = ROOT / "tmp/vh1-journal-focused.xml"
    suite = ElementTree.parse(junit).getroot().find("testsuite")  # noqa: S314 - local pytest output
    if suite is None or any(int(suite.get(k, "0")) for k in ("failures", "errors", "skipped")):
        raise ValueError("focused_tests_incomplete")
    for module, minimum in (
        ("test_phase7_v10_workflow", 3),
        ("test_phase7_v11_robustness", 9),
        ("test_journal_metadata", 23),
        ("test_xpm_compatibility", 25),
        ("test_vh1_journal_gate", 23),
        ("test_vh1_journal_xpm_gate", 12),
        ("test_vh1_final_gate", 32),
        ("test_vh1_source_evolution", 7),
        ("test_enrichment_bundles", 30),
        ("test_source_authorization", 1),
    ):
        if sum(module in c.get("classname", "") for c in suite.findall("testcase")) < minimum:
            raise ValueError("required_tests_not_reexecuted:" + module)
    if not evaluate(*inputs(), lambda p: (ROOT / p).read_bytes())["passed"]:
        raise ValueError("native_successor_not_qualified")
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
        prior = REPORT.parent / (stem + "-vh1-journal-metadata-v1.json")
        report = json.loads(prior.read_bytes())
        sources = (
            set(report["source_sha256"])
            | set(SOURCES)
            | {
                "ops/gate_vh1_journal_metadata.py",
                "ops/gate_vh1_final_validation.py",
                "ops/requalify_vh1_journal_workflow.py",
                "tests/test_vh1_journal_gate.py",
                "ops/audit_vh1_journal_xpm.py",
                "ops/run_vh1_journal_xpm.py",
                "ops/gate_vh1_journal_xpm.py",
                "tests/test_vh1_journal_xpm_gate.py",
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
            journal_current_checks=checks[gate],
            journal_native_report_sha256=sha(REPORT.read_bytes()),
            source_sha256={p: sha((ROOT / p).read_bytes()) for p in sorted(sources)},
            scope=(
                "Journal registry corrections and first exact DOI compatibility rules; not release."
            ),
        )
        with (REPORT.parent / (stem + "-vh1-journal-metadata-v2.json")).open(
            "x", encoding="utf-8"
        ) as stream:
            json.dump(report, stream, indent=2)
    print(json.dumps({"focused_tests": int(suite.get("tests")), "checks": checks}))


if __name__ == "__main__":
    main()
