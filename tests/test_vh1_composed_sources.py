from pathlib import Path

import pytest

from ops.gate_vh1_composed_sources import PINS, PREDECESSORS, RUNTIME, source_matches

ROOT = Path(__file__).parents[1]


def reader(path):
    return (ROOT / path).read_bytes()


@pytest.mark.parametrize("path,expected", PREDECESSORS.items())
def test_only_audited_composed_successor_is_accepted(path, expected):
    assert source_matches(path, expected, reader)
    assert not source_matches(path, "0" * 64, reader)


@pytest.mark.parametrize("target", [*PINS, *RUNTIME])
def test_current_runtime_or_historical_evidence_change_invalidates_chain(target):
    def changed(path):
        return reader(path) + b"changed" if path == target else reader(path)

    assert all(not source_matches(p, h, changed) for p, h in PREDECESSORS.items())


def test_unrelated_file_cannot_borrow_composed_evidence():
    assert not source_matches("src/idml_foundation/worker.py", "0" * 64, reader)
