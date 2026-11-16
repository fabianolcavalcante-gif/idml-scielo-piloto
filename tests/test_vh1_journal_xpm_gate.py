import json

import pytest

from ops.gate_vh1_journal_xpm import REPORT, ROOT, evaluate


def test_native_compatibility_proof_is_partial_and_not_release():
    result = evaluate(json.loads(REPORT.read_bytes()), lambda p: (ROOT / p).read_bytes())
    assert result["passed"], result
    assert not result["homologation_ready"] and not result["release_approved"]


@pytest.mark.parametrize(
    "change",
    ["ready", "approved", "exceptions", "raw", "unresolved", "negative", "image", "queries"],
)
def test_altered_proof_rejected(change):
    report = json.loads(REPORT.read_bytes())
    first = report["assessments"]["esa-e20240086"]
    if change == "ready":
        report["homologation_ready"] = True
    elif change == "approved":
        first["release_approved"] = True
    elif change == "exceptions":
        first["exceptions"].pop()
    elif change == "raw":
        first["original"]["errors"] = 2
    elif change == "unresolved":
        first["unresolved_counts"]["fatal_errors"] = 0
    elif change == "negative":
        report["native"]["negative_control_detected"] = False
    elif change == "queries":
        first["reasons"] = []
    else:
        report["native"]["image"] = "wrong"
    assert not evaluate(report, lambda p: (ROOT / p).read_bytes())["passed"]


@pytest.mark.parametrize(
    "path",
    [
        "ops/audit_vh1_journal_xpm.py",
        "src/idml_foundation/release/xpm_compatibility.py",
        "benchmarks/qualification/reports/vh1-xpm-doi-comparisons-v1.json",
    ],
)
def test_changed_source_or_probe_cannot_borrow_success(path):
    result = evaluate(
        json.loads(REPORT.read_bytes()),
        lambda p: b"changed" if p == path else (ROOT / p).read_bytes(),
    )
    assert not result["passed"]
