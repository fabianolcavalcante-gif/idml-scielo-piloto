import json
from pathlib import Path

import pytest

from ops import gate_phase7_v09, gate_phase7_v11, gate_vh17_catalog_sources

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("gate", [gate_phase7_v09, gate_phase7_v11])
def test_empty_source_evidence_cannot_approve_current_release(gate):
    report = json.loads(gate.REPORT.read_bytes())
    report["source_sha256"] = {}
    with pytest.raises(ValueError, match="source evidence"):
        gate._published_report_gate(report)


def test_missing_mutation_cases_cannot_score_one_hundred_percent():
    report = json.loads(gate_phase7_v11.REPORT.read_bytes())
    report["mutation_assessment"].update(mutants_total=0, mutants_killed=0, guards={})
    with pytest.raises(ValueError, match="mutation threshold"):
        gate_phase7_v11._published_report_gate(report)


@pytest.mark.parametrize("tampered", gate_vh17_catalog_sources.DEPENDENCIES)
def test_historical_catalog_comparison_is_bound_to_its_sources(tampered):
    gate = gate_vh17_catalog_sources
    proof = json.loads((ROOT / gate.REPORT).read_bytes())
    source = gate.CATALOG_SOURCES[0]

    def reader(p):
        return (ROOT / p).read_bytes()

    assert gate.source_matches(source, proof["before"][source], reader)
    assert not gate.source_matches(
        source, proof["before"][source], lambda p: reader(p) + (b"!" if p == tampered else b"")
    )


def test_changed_native_socket_receipt_cannot_refresh_a_broker():
    from ops import gate_vh17_scoped_sources as gate

    def reader(path):
        return (ROOT / path).read_bytes()

    broker = "ops/scoped_validator_broker.py"
    before = json.loads(reader(gate.OLD))["code_sha256"]["scoped_validator_broker.py"]
    assert gate.source_matches(broker, before, reader)
    assert not gate.source_matches(broker, "0" * 64, reader)
    assert not gate.source_matches(
        broker, before, lambda p: reader(p) + (b"!" if p == gate.NEW else b"")
    )


def test_composed_successor_requires_the_current_xpm_negative_controls():
    from ops import gate_vh1_composed_sources as gate

    path, before = next(iter(gate.PREDECESSORS.items()))

    def reader(p):
        return (ROOT / p).read_bytes()

    assert gate.source_matches(path, before, reader)
    assert not gate.source_matches(
        path, before, lambda p: reader(p) + (b"!" if p == gate.FRESH_PROOF else b"")
    )


def test_synthetic_xpm_package_identity_is_independent_of_clock(monkeypatch):
    import time

    from tests.test_xpm_compatibility import zip_xml

    clock = time.localtime
    monkeypatch.setattr(time, "localtime", lambda *args: clock(1_700_000_000))
    first = zip_xml(b"<article/>")
    monkeypatch.setattr(time, "localtime", lambda *args: clock(1_700_000_060))
    assert zip_xml(b"<article/>") == first
    assert zip_xml(b"<article>changed</article>") != first
