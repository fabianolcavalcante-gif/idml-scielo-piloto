import copy

import pytest

from ops.gate_vh1_reference_types import ROOT, evaluate, inputs


def run(values, changed=None):
    return evaluate(*values, lambda p: b"changed" if p == changed else (ROOT / p).read_bytes())


def test_qualified_reference_checkpoint_keeps_abstention_and_no_release():
    result = run(inputs())
    assert result["passed"], result
    assert result["remaining_ambiguous_glyphs"] == 1
    assert not result["formal_xml_approved"]
    assert not result["scientific_fidelity_approved"]
    assert not result["active_application_changed"]


@pytest.mark.parametrize(
    "mutation",
    [
        "approved",
        "deployed",
        "gold",
        "autonomous",
        "human",
        "abstention",
        "plan",
        "version",
        "transport",
        "case",
        "tool",
        "image",
        "candidate",
        "findings",
        "counts",
        "authority",
        "history",
        "before",
        "delta",
        "positions",
        "asset",
        "catalog",
        "fresh",
    ],
)
def test_altered_reference_evidence_is_rejected(mutation):
    values = copy.deepcopy(inputs())
    report, previous = values
    plan = report["qualification"]
    detail = plan["cases"]["esa-e20240135"]
    native = report["cases"][1]["validators"][0]
    if mutation in {"approved", "deployed"}:
        report[
            "formal_xml_approved" if mutation == "approved" else "active_application_changed"
        ] = True
    elif mutation in {"gold", "autonomous", "human", "abstention"}:
        key = {
            "gold": "gold_read",
            "autonomous": "autonomous_application",
            "human": "human_review_required",
            "abstention": "remaining_ambiguous_glyphs",
        }[mutation]
        plan[key] = False if mutation == "human" else 0 if mutation == "abstention" else True
    elif mutation == "plan":
        report["plan_sha256"] = "0" * 64
    elif mutation in {"version", "transport"}:
        report[mutation] = "other"
    elif mutation == "case":
        report["cases"].append(copy.deepcopy(report["cases"][0]))
    elif mutation == "tool":
        report["cases"][1]["validators"].append(copy.deepcopy(native))
    elif mutation in {"image", "candidate"}:
        native["image_id" if mutation == "image" else "candidate_sha256"] = "0" * 64
    elif mutation == "findings":
        native["findings"].pop()
    elif mutation == "counts":
        native["counts"] = {}
    elif mutation == "authority":
        native["authority_evidence"]["checks"]["doi"] = [False]
    elif mutation == "history":
        native["history_policy_evidence"]["policy"] = "other"
    elif mutation == "before":
        previous["cases"][1]["validators"][0]["candidate_sha256"] = "0" * 64
    elif mutation == "delta":
        detail["delta"]["fields"].pop()
    elif mutation == "positions":
        detail["delta"]["changed_references"] = 0
    elif mutation == "asset":
        detail["unchanged_assets"] = {}
    elif mutation == "catalog":
        detail["catalog_sha256"] = "0" * 64
    elif mutation == "fresh":
        detail["fresh_authorities"]["doi"]["retrieved_at"] = "2000-01-01T00:00:00+00:00"
    assert not run(values)["passed"]


@pytest.mark.parametrize(
    "path",
    [
        "src/idml_foundation/pipeline/idml_parser.py",
        "src/idml_foundation/pipeline/canonical_mapper.py",
        "src/idml_foundation/pipeline/reference_parser.py",
        "src/idml_foundation/release/reference_types.py",
        "src/idml_foundation/services/source_authorization.py",
        "src/idml_foundation/services/enrichment.py",
        "src/idml_foundation/pipeline/service.py",
        "src/idml_foundation/domain/canonical.py",
        "src/idml_foundation/domain/schema_migrations.py",
        "schemas/canonical-article-1.6.0.schema.json",
        "ops/vh1_source_evolution.py",
        "src/idml_foundation/ai/formula_catalog.py",
        "ops/qualify_vh1_references.py",
        "ops/run_vh1_history_linux.py",
        "config/validator-registry-vh1-history.json",
    ],
)
def test_source_changed_after_native_run_is_rejected(path):
    assert not run(inputs(), path)["passed"]
