import copy

import pytest

from ops.gate_vh1_final_validation import ROOT, evaluate, inputs
from ops.vh1_source_evolution import source_matches


def run(values, changed=None):
    return evaluate(*values, lambda p: b"changed" if p == changed else (ROOT / p).read_bytes())


def test_native_checkpoint_is_current_without_declaring_release():
    result = run(inputs())
    assert result["passed"], result
    assert not result["formal_xml_approved"]
    assert not result["vh07_complete"]
    assert result["xpm_status"] == "unavailable"


@pytest.mark.parametrize(
    "mutation",
    [
        "approved",
        "deployed",
        "plan",
        "scope",
        "canonical",
        "catalog",
        "assets",
        "delta",
        "gold",
        "version",
        "inspection",
        "autonomous",
        "human",
        "case",
        "tool",
        "image",
        "candidate",
        "findings",
        "severity",
        "counts",
        "authority",
        "history",
        "before",
        "fresh",
    ],
)
def test_changed_native_evidence_fails_closed(mutation):
    values = copy.deepcopy(inputs())
    report, _ = values
    plan = report["qualification"]
    detail = plan["cases"]["esa-e20240086"]
    native = report["cases"][0]["validators"][0]
    if mutation in {"approved", "deployed"}:
        report[
            "formal_xml_approved" if mutation == "approved" else "active_application_changed"
        ] = True
    elif mutation == "plan":
        report["plan_sha256"] = "0" * 64
    elif mutation in {"gold", "inspection", "autonomous", "human"}:
        key = {
            "gold": "gold_read",
            "inspection": "inspection_only",
            "autonomous": "autonomous_application",
            "human": "human_review_required",
        }[mutation]
        plan[key] = mutation != "human"
    elif mutation == "version":
        plan["version"] = "unexpected"
    elif mutation == "case":
        report["cases"].pop()
    elif mutation == "tool":
        report["cases"][0]["validators"].pop()
    elif mutation == "image":
        native["image_id"] = "sha256:" + "0" * 64
    elif mutation == "candidate":
        native["candidate_sha256"] = "0" * 64
    elif mutation == "findings":
        native["findings"].pop()
    elif mutation == "severity":
        native["findings"][0]["response"] = "info"
    elif mutation == "counts":
        native["counts"]["warning"] = 0
    elif mutation == "authority":
        native["authority_evidence"]["checks"]["doi"] = [False]
    elif mutation == "history":
        native["history_policy_evidence"]["invocations"][0]["effective_failures"] = ["error"]
    elif mutation in {"canonical", "catalog"}:
        detail["files"][
            "canonical.json" if mutation == "canonical" else "reference_type_catalog.json"
        ] = "0" * 64
    elif mutation == "scope":
        detail["scope_sha256"] = "0" * 64
    elif mutation == "assets":
        detail["unchanged_assets"] = []
    elif mutation == "delta":
        detail["delta"]["all_other_xml_unchanged"] = False
    elif mutation == "before":
        detail["before_xml_sha256"] = "0" * 64
    else:
        detail["fresh_authorities"]["doi"]["retrieved_at"] = "2000-01-01T00:00:00+00:00"
    assert not run(values)["passed"]


@pytest.mark.parametrize(
    "path",
    [
        "src/idml_foundation/pipeline/affiliation_hierarchy.py",
        "src/idml_foundation/pipeline/jats_builder.py",
        "ops/qualify_vh1_final_validation.py",
        "ops/vh1_source_evolution.py",
        "config/validator-registry-vh1-history.json",
    ],
)
def test_changed_current_source_does_not_reuse_native_success(path):
    assert not run(inputs(), path)["passed"]


def test_historical_builder_requires_new_native_proof():
    _, previous = inputs()
    path = "src/idml_foundation/pipeline/jats_builder.py"
    digest = previous["qualification"]["source_sha256"][path]
    assert source_matches(path, digest, lambda p: (ROOT / p).read_bytes())

    def reader(p):
        if p.endswith("vh1-final-validation-linux-v2.json"):
            raise FileNotFoundError(p)
        return (ROOT / p).read_bytes()

    assert not source_matches(path, digest, reader)


def test_coordinated_tampering_of_previous_and_current_authority_is_rejected():
    values = copy.deepcopy(inputs())
    for report in values:
        for case in report["cases"]:
            for entry in case["validators"]:
                entry["authority_evidence"]["checks"]["doi"] = [False]
    assert not run(values)["passed"]
