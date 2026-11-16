"""Current workflow gates after exact legacy capability composition."""

import json
from datetime import UTC, datetime
from xml.etree import ElementTree

from ops.qualify_vh1_structural_compatibility import ROOT, SOURCES, sha
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
    junit = ROOT / "tmp/vh1-structural-focused.xml"
    suite = ElementTree.parse(junit).getroot().find("testsuite")  # noqa: S314 - local pytest
    assert suite is not None and all(
        int(suite.get(k, "0")) == 0 for k in ("failures", "errors", "skipped")
    )
    for name in (
        "test_xpm_structural_compatibility",
        "test_vh1_structural_sources",
        "test_xpm_composed",
        "test_package_formal_validation",
        "test_phase7_v10_workflow",
        "test_phase7_v11_robustness",
    ):
        assert any(t.get("classname", "").endswith(name) for t in suite.findall("testcase"))
    checks = dict(
        v10=dict(
            api=_api_contract_gate(),
            jobs=_job_contract_gate(),
            package=_package_integrity_gate(),
            interface=_interface_and_degraded_gate(),
        ),
        v11=dict(
            fuzz=_fuzz_gate(),
            xml_unicode=_xml_and_unicode_property_gate(),
            package=_package_property_gate(),
        ),
    )
    changed_expected = {
        "ops/gate_vh1_composed_sources.py",
        "ops/gate_phase7_v10.py",
        "ops/gate_phase7_v11.py",
    }
    pending = []
    for family, stem in (("v10", "v10-operational-workflow"), ("v11", "v11-robustness-mutation")):
        directory = ROOT / "benchmarks/qualification/reports"
        prior = directory / f"{stem}-vh1-followups-v1.json"
        report = json.loads(prior.read_bytes())
        assert {
            p for p, s in report["source_sha256"].items() if sha((ROOT / p).read_bytes()) != s
        } == changed_expected
        sources = (
            set(report["source_sha256"])
            | set(SOURCES)
            | {
                "ops/gate_vh1_structural_sources.py",
                "tests/test_vh1_structural_sources.py",
                "ops/requalify_vh1_structural.py",
                "benchmarks/qualification/reports/vh1-structural-native-replay-v1.json",
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
            structural_checks=checks[family],
            source_sha256={p: sha((ROOT / p).read_bytes()) for p in sorted(sources)},
            scope="Qualified structural compatibility; raw publication gate unchanged.",
        )
        path = directory / f"{stem}-vh1-structural-v1.json"
        assert not path.exists()
        pending.append((path, report))
    for path, report in pending:
        with path.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2)
    print(json.dumps(dict(focused_tests=int(suite.get("tests")), gates=["V-10", "V-11"])))


if __name__ == "__main__":
    main()
