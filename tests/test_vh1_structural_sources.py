import json
from pathlib import Path

import pytest

from ops.gate_vh1_structural_sources import PATH, PREDECESSOR_SHA256, PROOF, source_matches

ROOT = Path(__file__).parents[1]


def reader(path):
    return (ROOT / path).read_bytes()


def test_only_exact_qualified_successor_matches():
    assert source_matches(PATH, PREDECESSOR_SHA256, reader)
    assert not source_matches(PATH, "0" * 64, reader)
    assert not source_matches("src/idml_foundation/worker.py", PREDECESSOR_SHA256, reader)


@pytest.mark.parametrize("target", [PROOF, *json.loads(reader(PROOF))["source_sha256"]])
def test_changed_proof_or_dependency_invalidates_successor(target):
    def changed(path):
        return reader(path) + b"changed" if path == target else reader(path)

    assert not source_matches(PATH, PREDECESSOR_SHA256, changed)
