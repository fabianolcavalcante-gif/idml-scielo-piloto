import copy

import pytest

from ops.gate_vh1_formula_revisions import ROOT, evaluate, inputs


def run(values, changed=None):
    return evaluate(*values, lambda p: b"changed" if p == changed else (ROOT / p).read_bytes())


def test_source_revision_proof_passes_without_scientific_or_release_approval():
    outcome = run(inputs())
    assert outcome["passed"], outcome
    assert not outcome["scientific_fidelity_approved"]
    assert not outcome["formal_xml_approved"]
    assert not outcome["active_application_changed"]
    assert outcome["remaining_glyph_reviews"] == 5


@pytest.mark.parametrize(
    "mutation",
    [
        "release",
        "deployed",
        "autonomous",
        "human",
        "gold",
        "plan",
        "plan_content",
        "missing_case",
        "missing_tool",
        "duplicate_case",
        "image",
        "xml",
        "zip",
        "drop_warning",
        "new_error",
        "severity",
        "counts",
        "doi",
        "scope",
        "history",
        "history_original",
        "before",
        "delta",
        "extra_delta",
        "math_count",
        "omit_pending",
        "stale_source",
        "source_hash",
    ],
)
def test_revision_proof_corruption_fails_closed(mutation):
    values = copy.deepcopy(inputs())
    report, previous = values
    plan = report["qualification"]
    detail = plan["cases"]["esa-e20240086"]
    row = report["cases"][0]["validators"][0]
    if mutation in {"release", "deployed"}:
        report["formal_xml_approved" if mutation == "release" else "active_application_changed"] = (
            True
        )
    elif mutation in {"autonomous", "human", "gold"}:
        key = {
            "autonomous": "autonomous_application",
            "human": "human_review_required",
            "gold": "gold_read",
        }[mutation]
        plan[key] = not plan[key]
    elif mutation == "plan":
        report["plan_sha256"] = "0" * 64
    elif mutation == "plan_content":
        plan["created_at"] = "forged"
    elif mutation == "missing_case":
        report["cases"].pop()
    elif mutation == "missing_tool":
        report["cases"][0]["validators"].pop()
    elif mutation == "duplicate_case":
        report["cases"].append(copy.deepcopy(report["cases"][0]))
    elif mutation == "image":
        row["image_id"] = "other"
    elif mutation in {"xml", "zip"}:
        report["cases"][0]["validators"][0 if mutation == "xml" else 1]["candidate_sha256"] = (
            "0" * 64
        )
    elif mutation == "drop_warning":
        row["findings"].pop()
    elif mutation == "new_error":
        row["findings"].append({"code": "new", "response": "error"})
    elif mutation == "severity":
        row["findings"][0]["response"] = "info"
    elif mutation == "counts":
        row["counts"] = {}
    elif mutation == "doi":
        row["authority_evidence"]["checks"]["doi"] = [False]
    elif mutation == "scope":
        row["authority_evidence"]["binding"]["scope_sha256"] = "0" * 64
    elif mutation == "history":
        row["history_policy_evidence"]["policy"] = "other"
    elif mutation == "history_original":
        row["history_policy_evidence"]["invocations"][0]["default_failures"] = []
    elif mutation == "before":
        previous["cases"][0]["validators"][0]["candidate_sha256"] = "0" * 64
    elif mutation == "delta":
        detail["delta"]["all_other_xml_unchanged"] = False
    elif mutation == "extra_delta":
        detail["delta"]["changes"].append(copy.deepcopy(detail["delta"]["changes"][0]))
    elif mutation == "math_count":
        detail["delta"]["formula_count"] = 18
    elif mutation == "omit_pending":
        plan["cases"]["esa-e20240135"]["review_counts"]["glyph_or_style_review_pending"] = 0
    elif mutation == "stale_source":
        detail["fresh_authorities"]["doi"]["retrieved_at"] = "2026-10-01T11:00:00+00:00"
    elif mutation == "source_hash":
        detail["fresh_authorities"]["doi"]["sha256"] = "0" * 64
    assert not run(values)["passed"]


@pytest.mark.parametrize(
    "path",
    [
        "src/idml_foundation/ai/formula_catalog.py",
        "src/idml_foundation/pipeline/service.py",
        "src/idml_foundation/pipeline/object_reference_resolver.py",
        "ops/qualify_vh1_formula_revisions.py",
        "ops/run_vh1_history_linux.py",
        "config/validator-registry-vh1-history.json",
    ],
)
def test_stale_revision_source_proof_is_rejected(path):
    assert not run(inputs(), path)["passed"]
