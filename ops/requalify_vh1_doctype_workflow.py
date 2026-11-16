"""Fresh V-10/V-11 checks for the exact audited header and runner successor."""

import json
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree

from ops.gate_vh1_doctype import DEPENDENCIES, REPORT, qualified, sha
from ops.requalify_vh1_articlemeta_workflow import (
    _api_contract_gate,
    _fuzz_gate,
    _interface_and_degraded_gate,
    _job_contract_gate,
    _package_integrity_gate,
    _package_property_gate,
    _xml_and_unicode_property_gate,
)

ROOT = Path(__file__).parents[1]


def main():
    junit = ROOT / "tmp/vh1-doctype-focused.xml"
    suite = ElementTree.parse(junit).getroot().find("testsuite")  # noqa: S314 - local pytest
    assert suite is not None and all(
        int(suite.get(k, "0")) == 0 for k in ("failures", "errors", "skipped")
    )
    for module, count in (
        ("test_jats_doctype", 8),
        ("test_vh1_doctype_gate", 19),
        ("test_vh1_journal_gate", 23),
        ("test_vh1_final_gate", 32),
        ("test_vh1_source_evolution", 7),
        ("test_phase7_v10_workflow", 3),
        ("test_phase7_v11_robustness", 9),
    ):
        assert sum(module in t.get("classname", "") for t in suite.findall("testcase")) >= count
    assert qualified(lambda p: (ROOT / p).read_bytes())
    chain_junit = ROOT / "tmp/vh1-doctype-compatibility-chain.xml"
    chain = ElementTree.parse(chain_junit).getroot().find("testsuite")  # noqa: S314
    assert chain is not None and int(chain.get("tests", "0")) == 48
    assert all(int(chain.get(k, "0")) == 0 for k in ("failures", "errors", "skipped"))
    checks = {
        "v10": dict(
            api=_api_contract_gate(),
            jobs=_job_contract_gate(),
            package=_package_integrity_gate(),
            interface=_interface_and_degraded_gate(),
        ),
        "v11": dict(
            fuzz=_fuzz_gate(),
            xml_unicode=_xml_and_unicode_property_gate(),
            package=_package_property_gate(),
        ),
    }
    for gate, stem in (("v10", "v10-operational-workflow"), ("v11", "v11-robustness-mutation")):
        directory = ROOT / "benchmarks/qualification/reports"
        prior = directory / (stem + "-vh1-doctype-v2.json")
        report = json.loads(prior.read_bytes())
        sources = (
            set(report["source_sha256"])
            | set(DEPENDENCIES)
            | {
                "ops/gate_vh1_doctype.py",
                "ops/requalify_vh1_doctype_workflow.py",
                "tests/test_vh1_doctype_gate.py",
                "tests/test_vh1_composed_sources.py",
            }
        )
        sources.update(p.relative_to(ROOT).as_posix() for p in (ROOT / "ops").glob("gate_vh1*.py"))
        report.update(
            executed_at=datetime.now(UTC).isoformat(),
            requalification_of=prior.name,
            previous_report_sha256=sha(prior.read_bytes()),
            focused_tests=int(suite.get("tests")),
            focused_junit_sha256=sha(junit.read_bytes()),
            compatibility_chain_tests=48,
            compatibility_chain_junit_sha256=sha(chain_junit.read_bytes()),
            full_tests=None,
            line_coverage_percent=None,
            doctype_current_checks=checks[gate],
            doctype_native_report_sha256=sha((ROOT / REPORT).read_bytes()),
            source_sha256={p: sha((ROOT / p).read_bytes()) for p in sorted(sources)},
            scope=(
                "Audited MathML3 header and current package assessment; "
                "no publication or deployment."
            ),
        )
        with (directory / (stem + "-vh1-doctype-v3.json")).open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2)
    print(json.dumps(dict(focused_tests=int(suite.get("tests")), checks=checks)))


if __name__ == "__main__":
    main()
