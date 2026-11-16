"""Refresh source-bound V11 only after current metadata and robustness tests pass."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree

from ops.gate_phase7_v11 import (
    _fuzz_gate,
    _package_property_gate,
    _xml_and_unicode_property_gate,
)

ROOT = Path(__file__).resolve().parents[1]


def main():
    junit = ROOT / "tmp/vh1-dates-funding-focused.xml"
    suite = ElementTree.parse(junit).getroot().find("testsuite")  # noqa: S314 - local pytest output
    if (
        suite is None
        or int(suite.get("tests", "0")) < 111
        or any(int(suite.get(key, "0")) for key in ("failures", "errors", "skipped"))
    ):
        raise ValueError("tests_not_passed")
    names = [item.get("classname", "") for item in suite.findall("testcase")]
    if sum("test_phase7_v11_robustness" in name for name in names) != 9:
        raise ValueError("robustness_not_reexecuted")
    if sum("test_vh1_dates_funding" in name for name in names) < 54:
        raise ValueError("dates_funding_not_reexecuted")
    gates = {
        "fuzz": _fuzz_gate(),
        "xml_unicode": _xml_and_unicode_property_gate(),
        "package": _package_property_gate(),
    }
    prior = ROOT / "benchmarks/qualification/reports/v11-robustness-mutation-vh1-metadata-v2.json"
    report = json.loads(prior.read_bytes())
    sources = set(report["source_sha256"]) | {
        "src/idml_foundation/pipeline/metadata_normalization.py",
        "tests/test_vh1_metadata_normalization.py",
        "ops/qualify_vh1_metadata.py",
        "src/idml_foundation/publication_dates.py",
        "src/idml_foundation/release/formal_metadata.py",
        "src/idml_foundation/pipeline/funding_parser.py",
        "tests/test_vh1_dates_funding.py",
    }
    report.update(
        executed_at=datetime.now(UTC).isoformat(),
        requalification_of=prior.name,
        previous_report_sha256=hashlib.sha256(prior.read_bytes()).hexdigest(),
        focused_tests=int(suite.get("tests")),
        full_tests=None,
        line_coverage_percent=None,
        focused_junit_sha256=hashlib.sha256(junit.read_bytes()).hexdigest(),
        current_gates=gates,
        source_sha256={
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in sorted(sources)
        },
    )
    target = ROOT / "benchmarks/qualification/reports/v11-robustness-mutation-vh1-metadata-v3.json"
    with target.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
    print(json.dumps({"focused_tests": int(suite.get("tests")), "gates": gates}))


if __name__ == "__main__":
    main()
