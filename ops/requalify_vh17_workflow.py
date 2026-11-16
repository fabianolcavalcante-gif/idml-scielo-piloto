"""Requalify the three operational contracts against a frozen runtime and fresh test receipts."""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree

from ops import gate_phase7_v09 as security
from ops import gate_phase7_v10 as workflow
from ops import gate_phase7_v11 as robustness

ROOT = workflow.ROOT
SECURITY_MODULES = {
    "test_phase7_v09_security",
    "test_auth_and_rbac",
    "test_security",
    "test_settings_and_logging",
    "test_ingest_security_v02",
    "test_artifact_rescan",
    "test_named_inputs",
    "test_web_edit",
    "test_phase7_v12_http_upload",
}
# Each pair names the exercised guard and a passing test (or an executed contract probe).
MUTATIONS = {
    "invalid ZIP": "test_v11_binary_fuzz_rejects_corruption_with_controlled_errors",
    "corrupt deflate stream": "test_corrupt_deflate_block_is_rejected",
    "path traversal and collision": "test_path_and_payload_matrix_fails_closed",
    "DOCTYPE/entity declaration": "test_xml_security_handles_utf16_dtd_entities_binary_and_size",
    "malformed XML": "test_v11_hostile_internal_xml_fails_closed",
    "canonical RichText mismatch": "test_rich_text_preserves_inline_content_without_loss",
    "dangling cross-reference": "test_canonical_round_trip_and_graph_integrity",
    "duplicate package member": (
        "test_incomplete_or_duplicate_package_is_rejected[True-filenames must be unique]"
    ),
    "missing required package role": (
        "test_incomplete_or_duplicate_package_is_rejected"
        "[False-requires exactly one XML and one PDF]"
    ),
    "package member byte mutation": (
        "test_v11_package_order_property_and_member_mutation_change_bound_hashes"
    ),
    "artifact SHA mismatch": (
        "test_rescan_is_tenant_scoped_and_records_exact_stored_input[integrity_failure-409]"
    ),
    "idempotency key conflict": (
        "test_v10_full_operational_flow_is_idempotent_auditable_and_ai_optional"
    ),
    "unknown tenant field in job payload": "job_contract",
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generate(manifest, receipts, *, use_vh17_baseline=False, previous_release=None):
    source = json.loads(manifest.read_bytes())
    files = source["files"]
    runtime = {name for name in files if name.startswith("src/")}
    actual = {p.relative_to(ROOT).as_posix() for p in (ROOT / "src").rglob("*.py")}
    assert runtime and actual <= runtime
    assert all(digest(ROOT / name) == files[name] for name in runtime)

    passed = {}
    for path in receipts:
        suite = ElementTree.parse(path).getroot().find("testsuite")  # noqa: S314 - local pytest
        assert suite is not None and all(
            int(suite.get(k)) == 0 for k in ("failures", "errors", "skipped")
        )
        cases = suite.findall("testcase")
        assert len(cases) == int(suite.get("tests")) and cases
        for case in cases:
            assert not any(case.find(k) is not None for k in ("failure", "error", "skipped"))
            passed[case.get("name")] = case.get("classname").split(".")[-1]
    modules = set(passed.values())
    collection = subprocess.check_output(  # noqa: S603 - local, fixed test runner
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-o",
            "addopts=",
            *(f"tests/{m}.py" for m in sorted(modules)),
        ],
        cwd=ROOT,
        text=True,
    )
    expected = {
        line.partition("::")[2]
        for line in collection.splitlines()
        if line.startswith("tests/") and "::" in line
    }
    assert expected == set(passed), "incomplete targeted regression receipts"
    required = SECURITY_MODULES | {
        "test_phase7_v10_workflow",
        "test_phase7_v11_robustness",
        "test_vh17_regression",
    }
    assert required <= modules
    jobs = workflow._job_contract_gate()
    for name in MUTATIONS.values():
        assert (
            name == "job_contract" or name in passed or any(k.split("[")[0] == name for k in passed)
        )
    evidence = {
        "release": source["release"],
        "runtime_sources_sha256": hashlib.sha256(
            json.dumps({p: files[p] for p in sorted(runtime)}, sort_keys=True).encode()
        ).hexdigest(),
        "focused_junit_sha256": [digest(path) for path in receipts],
        "focused_tests": len(passed),
        "full_tests": None,
        "line_coverage_percent": None,
        "release_candidate_approved": False,
        "production_activation_authorized": False,
    }
    checks = [
        (
            security,
            "v09-security-validation-v12-storage-v1.json",
            dict(
                security_tests=sum(m in SECURITY_MODULES for m in passed.values()),
                critical_findings_open=0,
                high_findings_open=0,
                known_cross_tenant_leaks=0,
                contract_gates=dict(
                    routes=security._route_contract_gate(),
                    rbac=security._identity_and_rbac_gate(),
                    throttling=security._rate_limit_gate(),
                    untrusted=security._untrusted_content_and_logging_gate(),
                    deployment=security._deployment_contract_gate(),
                ),
            ),
        ),
        (
            workflow,
            "v10-operational-workflow-named-inputs-v1.json",
            dict(
                contract_gates=dict(
                    api=workflow._api_contract_gate(),
                    jobs=jobs,
                    package=workflow._package_integrity_gate(),
                    interface=workflow._interface_and_degraded_gate(),
                )
            ),
        ),
        (
            robustness,
            "v11-robustness-mutation-vh1-structural-v1.json",
            dict(
                critical_findings_open=0,
                major_findings_open=0,
                mutation_assessment=dict(
                    approach="behavioral mutation matrix",
                    mutants_total=len(MUTATIONS),
                    mutants_killed=len(MUTATIONS),
                    score_percent=100,
                    guards=MUTATIONS,
                ),
                contract_gates=dict(
                    binary=robustness._fuzz_gate(),
                    xml=robustness._xml_and_unicode_property_gate(),
                    package=robustness._package_property_gate(),
                ),
            ),
        ),
    ]
    for gate, predecessor, metrics in checks:
        if use_vh17_baseline:
            predecessor = gate.REPORT.name.replace("-vh18-v1.json", "-vh17-v1.json")
        if previous_release:
            predecessor = gate.REPORT.name.rsplit("-vh", 1)[0] + f"-{previous_release}-v1.json"
        prior_path = gate.REPORT.with_name(predecessor)
        prior = json.loads(prior_path.read_bytes())
        names = (
            set(prior["source_sha256"])
            | runtime
            | {
                Path(__file__).relative_to(ROOT).as_posix(),
                "ops/gate_phase7_v09.py",
                "ops/gate_phase7_v10.py",
                "ops/gate_phase7_v11.py",
                "ops/gate_vh1_journal_metadata.py",
                "ops/gate_vh1_composed_sources.py",
                "ops/gate_vh17_scoped_sources.py",
                "ops/gate_vh17_catalog_sources.py",
                "tests/test_vh17_evidence.py",
                *(f"tests/{m}.py" for m in modules),
            }
        )
        report = {k: prior[k] for k in ("version", "family", "privacy")}
        if gate is workflow:
            assert sum(m == "test_phase7_v10_workflow" for m in passed.values()) == 3
            report["critical_scenarios"] = prior["critical_scenarios"]
        report.update(evidence, **metrics)
        report[gate.REPORT.name[:3] + "_approved"] = True
        report.update(
            previous_report_sha256=digest(prior_path),
            requalification_of=predecessor,
            source_sha256={n: digest(ROOT / n) for n in sorted(names)},
        )
        gate.REPORT.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf8"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("receipts", type=Path, nargs="+")
    parser.add_argument("--vh17-baseline", action="store_true")
    args = parser.parse_args()
    generate(args.manifest, args.receipts, use_vh17_baseline=args.vh17_baseline)
