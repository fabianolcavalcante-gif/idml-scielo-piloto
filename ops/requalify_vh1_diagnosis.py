"""Requalify read-only diagnosis with current Python and shipped JavaScript checks."""

import hashlib
import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree

from idml_foundation.routers.ui import _JS
from idml_foundation.services.validation_diagnosis import describe_validation
from ops.requalify_vh1_articlemeta_workflow import (
    _api_contract_gate,
    _fuzz_gate,
    _interface_and_degraded_gate,
    _job_contract_gate,
    _package_integrity_gate,
    _package_property_gate,
    _xml_and_unicode_property_gate,
)
from tests.test_validation_diagnosis import stored_result

ROOT = Path(__file__).resolve().parents[1]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    junit = ROOT / "tmp/vh1-diagnosis-focused.xml"
    suite = ElementTree.parse(junit).getroot().find("testsuite")  # noqa: S314 - local pytest
    assert suite is not None and all(
        int(suite.get(key, "0")) == 0 for key in ("errors", "failures", "skipped")
    )
    for module in (
        "test_validation_diagnosis",
        "test_xpm_execution",
        "test_package_formal_validation",
        "test_phase7_v10_workflow",
        "test_phase7_v11_robustness",
        "test_xpm_composed",
        "test_jats_doctype",
    ):
        assert any(t.get("classname", "").endswith(module) for t in suite.findall("testcase"))
    node = shutil.which("node")
    assert node, "Node required for actual JavaScript checks"
    result = subprocess.run(  # noqa: S603 - trusted app and test script, no user commands
        [node, str(ROOT / "tests/ui_validation_diagnosis.cjs")],
        input=json.dumps(dict(js=_JS, diagnosis=describe_validation(stored_result()))),
        text=True,
        capture_output=True,
        check=True,
        timeout=30,
    )
    javascript = json.loads(result.stdout)
    assert javascript == {"checks": 6, "passed": True, "real_browser": False}
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
    for family, stem in (("v10", "v10-operational-workflow"), ("v11", "v11-robustness-mutation")):
        directory = ROOT / "benchmarks/qualification/reports"
        prior = directory / f"{stem}-vh1-doctype-v3.json"
        report = json.loads(prior.read_bytes())
        changed = {
            p
            for p, digest in report["source_sha256"].items()
            if sha((ROOT / p).read_bytes()) != digest
        }
        assert changed == set(report["source_sha256"]) & {
            "src/idml_foundation/routers/jobs.py",
            "src/idml_foundation/routers/ui.py",
        }, "unexpected predecessor source changes"
        sources = set(report["source_sha256"]) | {
            "src/idml_foundation/routers/jobs.py",
            "src/idml_foundation/routers/ui.py",
            "src/idml_foundation/services/validation_diagnosis.py",
            "tests/test_validation_diagnosis.py",
            "tests/ui_validation_diagnosis.cjs",
            "ops/requalify_vh1_diagnosis.py",
            "ops/gate_phase7_v10.py",
            "ops/gate_phase7_v11.py",
        }
        report.update(
            executed_at=datetime.now(UTC).isoformat(),
            requalification_of=prior.name,
            previous_report_sha256=sha(prior.read_bytes()),
            focused_tests=int(suite.get("tests")),
            focused_junit_sha256=sha(junit.read_bytes()),
            full_tests=None,
            line_coverage_percent=None,
            diagnosis_checks=checks[family],
            javascript_checks=javascript,
            source_sha256={p: sha((ROOT / p).read_bytes()) for p in sorted(sources)},
            scope="Stored job diagnosis; no validator, XML, policy or deployment changes.",
        )
        with (directory / f"{stem}-vh1-diagnosis-v2.json").open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2)
    print(json.dumps(dict(tests=int(suite.get("tests")), javascript=javascript, checks=checks)))


if __name__ == "__main__":
    main()
