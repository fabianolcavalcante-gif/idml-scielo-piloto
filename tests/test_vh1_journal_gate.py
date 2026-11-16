import copy
import json

import pytest

from ops.gate_vh1_journal_metadata import ROOT, evaluate, inputs, source_matches
from ops.qualify_vh1_journal_metadata import verify_delta


def run(values, changed=None):
    return evaluate(*values, lambda p: b"changed" if p == changed else (ROOT / p).read_bytes())


def test_native_journal_successor_does_not_approve_release():
    result = run(inputs())
    assert result["passed"], result
    assert not result["formal_xml_approved"]
    assert not result["active_application_changed"]


@pytest.mark.parametrize(
    "mutation",
    [
        "image",
        "counts",
        "candidate",
        "findings",
        "authority",
        "history",
        "approved",
        "delta",
        "assets",
        "source",
        "prior",
    ],
)
def test_changed_native_successor_rejected(mutation):
    values = copy.deepcopy(inputs())
    report, previous = values
    run = report["cases"][0]["validators"][0]
    detail = report["qualification"]["cases"][report["cases"][0]["case"]]
    if mutation == "image":
        run["image_id"] = "sha256:" + "0" * 64
    elif mutation == "counts":
        run["counts"] = {}
    elif mutation == "candidate":
        run["candidate_sha256"] = "0" * 64
    elif mutation == "findings":
        run["findings"].pop()
    elif mutation == "authority":
        run["authority_evidence"] = {}
    elif mutation == "history":
        run["history_policy_evidence"] = {}
    elif mutation == "approved":
        report["formal_xml_approved"] = True
    elif mutation == "delta":
        detail["delta"]["all_other_xml_unchanged"] = False
    elif mutation == "assets":
        detail["unchanged_assets"] = {}
    elif mutation == "source":
        report["qualification"]["source_sha256"] = {}
    else:
        previous["formal_xml_approved"] = True
    assert not evaluate(*values, lambda p: (ROOT / p).read_bytes())["passed"]


@pytest.mark.parametrize(
    "path",
    [
        "src/idml_foundation/release/journal_metadata.py",
        "src/idml_foundation/release/xpm_compatibility.py",
        "src/idml_foundation/pipeline/service.py",
        "src/idml_foundation/services/enrichment.py",
        "ops/vh1_source_evolution.py",
    ],
)
def test_changed_source_cannot_borrow_native_success(path):
    assert not run(inputs(), path)["passed"]


def test_old_source_requires_unmodified_successor():
    path = "src/idml_foundation/pipeline/service.py"
    report, previous = inputs()
    expected = previous["qualification"]["source_sha256"][path]
    assert source_matches(path, expected, lambda p: (ROOT / p).read_bytes())

    def reader(p):
        if p.endswith("vh1-journal-metadata-linux-v1.json"):
            changed = copy.deepcopy(report)
            changed["cases"][0]["validators"][0]["counts"] = {}
            return json.dumps(changed).encode()
        return (ROOT / p).read_bytes()

    assert not source_matches(path, expected, reader)


@pytest.mark.parametrize(
    "target",
    [
        "src/idml_foundation/release/journal_metadata.py",
        "benchmarks/qualification/reports/vh1-journal-metadata-linux-v1.json",
    ],
)
def test_cached_success_cannot_hide_changed_bytes_with_same_reader(target):
    path = "src/idml_foundation/pipeline/service.py"
    _, previous = inputs()
    expected = previous["qualification"]["source_sha256"][path]
    changed = False

    def reader(p):
        return b"changed" if changed and p == target else (ROOT / p).read_bytes()

    assert source_matches(path, expected, reader)
    changed = True
    assert not source_matches(path, expected, reader)
    changed = False
    assert source_matches(path, expected, reader)


def xml(title="Old", body="Scientific text"):
    return (
        f"<article><front><journal-meta><journal-title-group><journal-title>{title}"
        "</journal-title></journal-title-group><publisher><publisher-name>Publisher"
        f"</publisher-name></publisher></journal-meta></front><body>{body}</body></article>"
    ).encode()


def test_delta_allows_only_two_reviewable_fields():
    result = verify_delta(xml(), xml("New"))
    assert result["all_other_xml_unchanged"] and len(result["fields"]) == 1


def test_delta_rejects_scientific_change_even_with_journal_correction():
    with pytest.raises(ValueError, match="non_journal_metadata_change"):
        verify_delta(xml(), xml("New", "Changed scientific text"))


def test_delta_rejects_removed_field():
    with pytest.raises(ValueError, match="journal_field_not_unique"):
        verify_delta(xml(), xml().replace(b"<journal-title>Old</journal-title>", b""))
