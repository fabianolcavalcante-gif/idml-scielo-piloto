"""Fresh warning/query presentation checks; archived native evidence stays historical."""

import json
import shutil
import subprocess
from datetime import UTC, datetime
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
from ops.requalify_vh1_diagnosis import ROOT, sha
from tests.test_validation_diagnosis import stored_result
from tests.test_validation_followups import (
    test_native_archived_queries_keep_seven_deposits_and_four_public_name_conflicts,
)


def main():
    junit = ROOT / "tmp/vh1-followups-focused.xml"
    suite = ElementTree.parse(junit).getroot().find("testsuite")  # noqa: S314 - local pytest
    assert suite is not None and all(
        int(suite.get(k, "0")) == 0 for k in ("failures", "errors", "skipped")
    )
    for name in (
        "test_validation_followups",
        "test_validation_diagnosis",
        "test_xpm_query_semantics",
        "test_xpm_query_requirements",
        "test_xpm_execution",
        "test_package_formal_validation",
        "test_phase7_v10_workflow",
        "test_phase7_v11_robustness",
        "test_xpm_composed",
        "test_jats_doctype",
        "test_phase5_review_ui",
        "test_jobs",
        "test_api",
        "test_auth_and_rbac",
    ):
        assert any(t.get("classname", "").endswith(name) for t in suite.findall("testcase"))
    node = shutil.which("node")
    assert node
    execution = subprocess.run(  # noqa: S603 - repository source/test code only
        [node, str(ROOT / "tests/ui_validation_diagnosis.cjs")],
        input=json.dumps(dict(js=_JS, diagnosis=describe_validation(stored_result()))),
        text=True,
        capture_output=True,
        check=True,
        timeout=30,
    )
    javascript = json.loads(execution.stdout)
    assert javascript == dict(checks=6, passed=True, real_browser=False)
    test_native_archived_queries_keep_seven_deposits_and_four_public_name_conflicts()
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
        "src/idml_foundation/services/validation_diagnosis.py",
        "src/idml_foundation/routers/ui.py",
        "tests/ui_validation_diagnosis.cjs",
        "ops/gate_phase7_v10.py",
        "ops/gate_phase7_v11.py",
    }
    pending = []
    for family, stem in (("v10", "v10-operational-workflow"), ("v11", "v11-robustness-mutation")):
        directory = ROOT / "benchmarks/qualification/reports"
        prior = directory / f"{stem}-vh1-diagnosis-v2.json"
        report = json.loads(prior.read_bytes())
        changed = {
            p for p, s in report["source_sha256"].items() if sha((ROOT / p).read_bytes()) != s
        }
        assert changed == changed_expected
        sources = set(report["source_sha256"]) | {
            "src/idml_foundation/services/validation_followups.py",
            "tests/test_validation_followups.py",
            "ops/requalify_vh1_followups.py",
            "benchmarks/qualification/reports/vh1-xpm-composed-real-v1.json",
        }
        report.update(
            executed_at=datetime.now(UTC).isoformat(),
            requalification_of=prior.name,
            previous_report_sha256=sha(prior.read_bytes()),
            focused_tests=int(suite.get("tests")),
            focused_junit_sha256=sha(junit.read_bytes()),
            full_tests=None,
            line_coverage_percent=None,
            followup_checks=checks[family],
            javascript_checks=javascript,
            archived_native_query_replay=dict(
                articles=2, matched_deposits=7, public_name_conflicts=4, new_online_execution=False
            ),
            source_sha256={p: sha((ROOT / p).read_bytes()) for p in sorted(sources)},
            scope="Warning/query followups; no acceptance, validator or XML changes.",
        )
        path = directory / f"{stem}-vh1-followups-v1.json"
        assert not path.exists()
        pending.append((path, report))
    for path, report in pending:
        with path.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2)
    print(
        json.dumps(
            dict(tests=int(suite.get("tests")), javascript=javascript, native_replay_articles=2)
        )
    )


if __name__ == "__main__":
    main()
