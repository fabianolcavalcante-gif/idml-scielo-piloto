import hashlib
import json
from pathlib import Path

import pytest

from ops.gate_vh1_doctype import (
    BUILDER,
    DEPENDENCIES,
    PACKAGE_VALIDATION,
    REPORT,
    code_matches,
    qualified,
    source_matches,
)
from ops.gate_vh1_journal_metadata import evaluate, inputs

ROOT = Path(__file__).parents[1]


def reader(path):
    return (ROOT / path).read_bytes()


def test_exact_native_transition_restores_historical_checks_without_approval():
    proof = json.loads(reader(REPORT))
    assert qualified(reader)
    assert source_matches(BUILDER, proof["before_builder_sha256"], reader)
    assert evaluate(*inputs(), reader)["passed"]
    assert not proof["formal_xml_approved"]
    assert not proof["active_application_changed"]
    assert proof["compatibility_exceptions_added"] == 0


@pytest.mark.parametrize("path", DEPENDENCIES)
def test_any_changed_source_or_native_evidence_invalidates_successor(path):
    def changed(name):
        return reader(name) + b"changed" if name == path else reader(name)

    assert not qualified(changed)
    proof = json.loads(reader(REPORT))
    assert not source_matches(BUILDER, proof["before_builder_sha256"], changed)
    assert not evaluate(*inputs(), changed)["passed"]


def test_unknown_predecessor_and_unrelated_sources_cannot_borrow_proof():
    proof = json.loads(reader(REPORT))
    assert not source_matches(BUILDER, "0" * 64, reader)
    assert not source_matches(
        "src/idml_foundation/worker.py", proof["before_builder_sha256"], reader
    )
    current = hashlib.sha256(reader(BUILDER)).hexdigest()
    assert source_matches(BUILDER, current, reader)


def test_missing_native_proof_cannot_refresh_builder():
    def missing(path):
        if path == REPORT:
            raise FileNotFoundError(path)
        return reader(path)

    proof = json.loads(reader(REPORT))
    assert not source_matches(BUILDER, proof["before_builder_sha256"], missing)


@pytest.mark.parametrize("mutation", ["extra", "missing", "unknown_hash", "other_file"])
def test_runner_evidence_keeps_exact_keys_and_predecessor(mutation):
    proof = json.loads(reader(REPORT))
    mapping = {"package_validation.py": PACKAGE_VALIDATION}
    expected = {"package_validation.py": proof["before_package_validation_sha256"]}
    assert code_matches(expected, mapping, reader)
    if mutation == "extra":
        expected["unknown.py"] = "0" * 64
    elif mutation == "missing":
        expected = {}
    elif mutation == "unknown_hash":
        expected["package_validation.py"] = "0" * 64
    else:
        mapping["package_validation.py"] = "src/idml_foundation/worker.py"
    assert not code_matches(expected, mapping, reader)
