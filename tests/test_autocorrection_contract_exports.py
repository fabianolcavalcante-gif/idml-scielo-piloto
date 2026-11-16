import json

import pytest

from ops.qualify_vh08_autocorrection import ROOT, outputs, verify

REPORT = ROOT / "benchmarks/qualification/reports/vh08-autocorrection-policy-v2.json"


@pytest.mark.parametrize("path,value", outputs().items())
def test_exported_contract_is_current(path, value):
    assert json.loads((ROOT / path).read_bytes()) == value


def test_qualification_sources_are_current_without_application_or_release():
    assert verify(json.loads(REPORT.read_bytes()))


@pytest.mark.parametrize(
    "field",
    [
        "live_ai_called",
        "executor_implemented",
        "active_application_changed",
        "homologation_ready",
        "release_approved",
    ],
)
def test_qualification_cannot_be_promoted_by_editing_a_flag(field):
    report = json.loads(REPORT.read_bytes())
    report[field] = True
    assert not verify(report)


def test_changed_policy_identity_or_source_hash_rejected():
    report = json.loads(REPORT.read_bytes())
    report["policy_sha256"] = "f" * 64
    assert not verify(report)
    report = json.loads(REPORT.read_bytes())
    report["source_sha256"]["src/idml_foundation/ai/autocorrection_policy.py"] = "f" * 64
    assert not verify(report)
