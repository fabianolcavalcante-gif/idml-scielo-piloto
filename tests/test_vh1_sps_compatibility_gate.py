import json

import pytest

from ops import gate_vh1_sps_compatibility as gate


def reader(path):
    return (gate.ROOT / path).read_bytes()


def test_native_proof_chain_passes_without_approval():
    result = gate.evaluate(json.loads(gate.REPORT.read_bytes()), reader)
    assert result["passed"] and not result["release_approved"] and not result["homologation_ready"]


@pytest.mark.parametrize(
    "field",
    [
        "release_approved",
        "homologation_ready",
        "candidate_changed",
        "active_application_changed",
        "vendor_changed",
        "native_xpm_rerun",
    ],
)
def test_tampered_outcomes_rejected(field):
    report = json.loads(gate.REPORT.read_bytes())
    report[field] = True
    assert not gate.evaluate(report, reader)["passed"]


@pytest.mark.parametrize("name", ["esa-e20240086", "esa-e20240135"])
def test_fatal_and_unknown_error_cannot_be_erased(name):
    report = json.loads(gate.REPORT.read_bytes())
    report["assessments"][name]["unresolved_counts"]["fatal_errors"] = 0
    report["assessments"][name]["unresolved_counts"]["errors"] = 0
    assert not gate.evaluate(report, reader)["passed"]


@pytest.mark.parametrize(
    "path",
    [
        *gate.SOURCES,
        gate.PROBE,
        "benchmarks/qualification/reports/vh1-journal-metadata-linux-v1.json",
        "benchmarks/qualification/reports/vh1-journal-xpm-compatibility-v1.json",
    ],
)
def test_current_source_and_native_proof_tampering_rejected(path):
    def tampered(name):
        return reader(name) + b"tampered" if name == path else reader(name)

    assert not gate.evaluate(json.loads(gate.REPORT.read_bytes()), tampered)["passed"]


def test_missing_evidence_fails_closed():
    def missing(path):
        raise FileNotFoundError(path)

    assert not gate.evaluate(json.loads(gate.REPORT.read_bytes()), missing)["passed"]
