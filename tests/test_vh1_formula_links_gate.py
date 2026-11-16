import copy

import pytest

from ops.gate_vh1_formula_links import ROOT, evaluate, inputs


def run(values, changed_source=None):
    return evaluate(
        *values, lambda p: b"changed" if p == changed_source else (ROOT / p).read_bytes()
    )


def test_formula_proof_passes_without_approving_scientific_fidelity_or_release():
    result = run(inputs())
    assert result["passed"], result
    assert not result["formal_xml_approved"]
    assert not result["scientific_fidelity_approved"]
    assert not result["active_application_changed"]


@pytest.mark.parametrize(
    "mutation",
    [
        "release",
        "deployed",
        "gold",
        "catalog",
        "plan",
        "plan_content",
        "version",
        "transport",
        "missing_case",
        "duplicate_case",
        "missing_tool",
        "duplicate_tool",
        "image",
        "xml",
        "zip",
        "drop_warning",
        "add_error",
        "severity",
        "counts",
        "authority",
        "binding",
        "policy",
        "history_original",
        "history_effective",
        "registry",
        "delta",
        "mathml",
        "baseline_warning",
        "baseline_error",
        "baseline_xml",
    ],
)
def test_corrupted_formula_link_evidence_is_rejected(mutation):
    values = copy.deepcopy(inputs())
    report, previous, registry = values
    run = report["cases"][0]["validators"][0]
    plan = report["qualification"]
    details = plan["cases"]["esa-e20240086"]
    if mutation in {"release", "deployed"}:
        report["formal_xml_approved" if mutation == "release" else "active_application_changed"] = (
            True
        )
    elif mutation in {"gold", "catalog"}:
        plan["gold_read" if mutation == "gold" else "catalog_values_changed"] = True
    elif mutation == "plan":
        report["plan_sha256"] = "0" * 64
    elif mutation == "plan_content":
        plan["created_at"] = "forged"
    elif mutation in {"version", "transport"}:
        report[mutation] = "other"
    elif mutation == "missing_case":
        report["cases"].pop()
    elif mutation == "duplicate_case":
        report["cases"].append(copy.deepcopy(report["cases"][0]))
    elif mutation == "missing_tool":
        report["cases"][0]["validators"].pop()
    elif mutation == "duplicate_tool":
        report["cases"][0]["validators"].append(copy.deepcopy(run))
    elif mutation == "image":
        run["image_id"] = "sha256:" + "0" * 64
    elif mutation in {"xml", "zip"}:
        report["cases"][0]["validators"][0 if mutation == "xml" else 1]["candidate_sha256"] = (
            "0" * 64
        )
    elif mutation == "drop_warning":
        run["findings"].pop()
    elif mutation == "add_error":
        run["findings"].append({"code": "new", "response": "error"})
    elif mutation == "severity":
        run["findings"][0]["response"] = "info"
    elif mutation == "counts":
        run["counts"] = {}
    elif mutation == "authority":
        run["authority_evidence"]["checks"]["doi"] = [False]
    elif mutation == "binding":
        run["authority_evidence"]["binding"]["scope_sha256"] = "0" * 64
    elif mutation == "policy":
        run["history_policy_evidence"]["policy"] = "other"
    elif mutation == "history_original":
        run["history_policy_evidence"]["invocations"][0]["default_failures"] = []
    elif mutation == "history_effective":
        run["history_policy_evidence"]["invocations"][0]["effective_failures"] = [{}]
    elif mutation == "registry":
        next(r for r in registry["validators"] if r["channel"] == "active")["image_id"] = "other"
    elif mutation == "delta":
        details["delta"]["added_links"].pop()
    elif mutation == "mathml":
        details["delta"]["mathml_unchanged"] = False
    elif mutation == "baseline_warning":
        previous["cases"][0]["validators"][0]["findings"].pop()
    elif mutation == "baseline_error":
        old = previous["cases"][0]["validators"][0]
        old["findings"] = [f for f in old["findings"] if f["response"] != "error"]
    elif mutation == "baseline_xml":
        previous["cases"][0]["validators"][0]["candidate_sha256"] = "0" * 64
    assert not evaluate(*values, lambda p: (ROOT / p).read_bytes())["passed"]


@pytest.mark.parametrize(
    "path",
    [
        "src/idml_foundation/pipeline/object_reference_resolver.py",
        "src/idml_foundation/pipeline/service.py",
        "ops/qualify_vh1_formula_links.py",
        "ops/run_vh1_history_linux.py",
        "ops/scoped_validator_broker.py",
        "config/validator-registry-vh1-history.json",
    ],
)
def test_stale_source_proof_fails(path):
    assert not run(inputs(), path)["passed"]
