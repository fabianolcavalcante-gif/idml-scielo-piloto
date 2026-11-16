import json

import pytest

from ops.gate_vh1_references import ROOT, inputs
from ops.vh1_source_evolution import source_matches

MAPPER = "src/idml_foundation/pipeline/canonical_mapper.py"


def test_only_the_native_qualified_source_successor_can_replace_old_mapper_evidence():
    current, previous = inputs()
    old_hash = previous["qualification"]["source_sha256"][MAPPER]
    assert current["qualification"]["source_sha256"][MAPPER] != old_hash
    assert source_matches(MAPPER, old_hash, lambda p: (ROOT / p).read_bytes())
    assert not source_matches(MAPPER, "0" * 64, lambda p: (ROOT / p).read_bytes())


@pytest.mark.parametrize("mutation", ["mapper", "parser", "report", "missing", "warning"])
def test_stale_or_mutated_successor_cannot_refresh_historical_proofs(mutation):
    _, previous = inputs()

    def reader(path):
        raw = (ROOT / path).read_bytes()
        if path == MAPPER and mutation == "mapper":
            return raw + b"changed"
        if path.endswith("/reference_parser.py") and mutation == "parser":
            return raw + b"changed"
        if path.endswith("vh1-references-linux-v1.json"):
            if mutation == "missing":
                raise FileNotFoundError(path)
            report = json.loads(raw)
            if mutation == "report":
                report["formal_xml_approved"] = True
            elif mutation == "warning":
                report["cases"][1]["validators"][0]["findings"].pop()
            return json.dumps(report).encode()
        return raw

    assert not source_matches(MAPPER, previous["qualification"]["source_sha256"][MAPPER], reader)


def test_unrelated_source_cannot_use_mapper_successor():
    assert not source_matches(
        "src/idml_foundation/worker.py", "0" * 64, lambda p: (ROOT / p).read_bytes()
    )
