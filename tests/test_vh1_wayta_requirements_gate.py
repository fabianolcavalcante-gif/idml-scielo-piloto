import json

import pytest

from ops import gate_vh1_wayta_requirements as gate


def reader(path):
    return (gate.ROOT / path).read_bytes()


def test_native_qualification_preserves_all_original_findings_and_pending_queries():
    result = gate.evaluate(json.loads(gate.REPORT.read_bytes()), reader)
    assert result["passed"] and not result["release_approved"] and not result["homologation_ready"]


@pytest.mark.parametrize(
    "path",
    [
        *gate.SOURCES,
        gate.PROBE,
        gate.SERVICE,
        "benchmarks/qualification/reports/vh1-sps-compatibility-v2.json",
        "benchmarks/qualification/reports/vh1-journal-metadata-linux-v1.json",
    ],
)
def test_changed_sources_or_native_evidence_fail_closed(path):
    def tampered(name):
        return reader(name) + b"tampered" if name == path else reader(name)

    assert not gate.evaluate(json.loads(gate.REPORT.read_bytes()), tampered)["passed"]


@pytest.mark.parametrize(
    "field",
    [
        "article_query_completed",
        "institution_identity_verified",
        "release_approved",
        "homologation_ready",
    ],
)
def test_query_or_release_success_cannot_be_forged(field):
    report = json.loads(gate.REPORT.read_bytes())
    report["assessments"]["esa-e20240086"][field] = True
    assert not gate.evaluate(report, reader)["passed"]


def test_unknown_fatal_cannot_disappear():
    report = json.loads(gate.REPORT.read_bytes())
    report["assessments"]["esa-e20240135"]["base"]["unresolved_counts"]["fatal_errors"] = 0
    assert not gate.evaluate(report, reader)["passed"]


def test_missing_native_proof_fails_closed():
    def missing(path):
        raise FileNotFoundError(path)

    assert not gate.evaluate(json.loads(gate.REPORT.read_bytes()), missing)["passed"]
