import copy

import pytest

from ops.gate_vh1_history import ROOT, evaluate, inputs


def run(values, changed_source=None):
    return evaluate(
        *values,
        lambda p: b"changed" if p == changed_source else (ROOT / p).read_bytes(),
    )


def test_history_proof_is_complete_and_not_release():
    outcome = run(inputs())
    assert outcome["passed"], outcome
    assert outcome["formal_xml_approved"] is False
    assert outcome["active_application_changed"] is False


@pytest.mark.parametrize(
    "mutation",
    [
        "release",
        "deployed",
        "plan",
        "spec",
        "section",
        "xml",
        "zip",
        "baseline",
        "drop_real_error",
        "drop_warning",
        "new_error",
        "lower_severity",
        "doi",
        "orcid",
        "policy",
        "proof_missing",
        "default_missing",
        "effective_bad",
        "no_revision_claim",
        "wrong_image",
        "native_changed",
        "wrapper_changed",
        "probe_missing",
        "probe_failed",
        "rollback",
        "xpm",
        "missing_tool",
        "missing_case",
    ],
)
def test_forged_or_incomplete_history_proof_is_rejected(mutation):
    values = copy.deepcopy(inputs())
    report, previous, images, _, registry, _ = values
    first = report["cases"][0]["validators"][0]
    proof = first["history_policy_evidence"]
    if mutation == "release":
        report["formal_xml_approved"] = True
    elif mutation == "deployed":
        report["active_application_changed"] = True
    elif mutation == "plan":
        report["plan_sha256"] = "a" * 64
    elif mutation in {"spec", "section"}:
        proof["specification_sha256" if mutation == "spec" else "section_sha256"] = "a" * 64
    elif mutation == "xml":
        first["candidate_sha256"] = "a" * 64
    elif mutation == "zip":
        report["cases"][0]["validators"][1]["candidate_sha256"] = "a" * 64
    elif mutation == "baseline":
        previous["qualification"]["cases"]["esa-e20240086"]["xml_sha256"] = "a" * 64
    elif mutation in {"drop_real_error", "drop_warning"}:
        response = "error" if mutation == "drop_real_error" else "warning"
        first["findings"] = [f for f in first["findings"] if f["response"] != response]
    elif mutation == "new_error":
        first["findings"].append({"code": "new-rule", "response": "error"})
    elif mutation == "lower_severity":
        first["findings"][0]["response"] = "warning"
    elif mutation in {"doi", "orcid"}:
        first["authority_evidence"]["checks"][mutation][0] = False
    elif mutation == "policy":
        proof["policy"] = "new-policy"
    elif mutation == "proof_missing":
        del first["history_policy_evidence"]
    elif mutation == "default_missing":
        proof["invocations"][0]["default_failures"] = []
    elif mutation == "effective_bad":
        proof["invocations"][0]["effective_failures"] = [
            {"rule": "missing received", "outcome": "CRITICAL"}
        ]
    elif mutation == "no_revision_claim":
        proof["absence_is_not_proof_of_no_revision"] = False
    elif mutation == "wrong_image":
        first["image_id"] = "sha256:" + "a" * 64
    elif mutation == "native_changed":
        images["validators"]["packtools"]["runtime"]["package_trees"] = {}
    elif mutation == "wrapper_changed":
        images["validators"]["packtools"]["runtime"]["wrappers_sha256"]["packtools_validate.py"] = (
            "a" * 64
        )
    elif mutation == "probe_missing":
        del images["validators"]["packtools"]["native_probe"]["checks"]["missing_received"]
    elif mutation == "probe_failed":
        images["validators"]["packtools"]["native_probe"]["checks"]["missing_received"][
            "passed"
        ] = False
    elif mutation == "rollback":
        next(r for r in registry["validators"] if r["channel"] == "rollback")["image_id"] = (
            "sha256:" + "a" * 64
        )
    elif mutation == "xpm":
        registry["xpm"]["integration_status"] = "waived"
    elif mutation == "missing_tool":
        report["cases"][0]["validators"].pop()
    elif mutation == "missing_case":
        report["cases"].pop()
    assert not run(values)["passed"]


@pytest.mark.parametrize(
    "path",
    [
        "ops/history_compat.py",
        "ops/history_validator_adapter.py",
        "ops/scoped_validator_adapter.py",
        "ops/probe_vh1_history.py",
        "ops/run_vh1_history_linux.py",
        "ops/prepare_vh1_history_qualification.py",
        "config/validator-registry-vh1-history.json",
        "deploy/Dockerfile.validator-history-compat",
    ],
)
def test_source_changes_require_new_qualification(path):
    assert not run(inputs(), changed_source=path)["passed"]


@pytest.mark.parametrize("mapping", ["source_sha256", "history_source_sha256", "code_sha256"])
def test_missing_source_binding_is_rejected(mapping):
    values = copy.deepcopy(inputs())
    values[0]["qualification"][mapping] = {}
    assert not run(values)["passed"]


def test_missing_image_source_binding_is_rejected():
    values = copy.deepcopy(inputs())
    values[2]["source_sha256"] = {}
    assert not run(values)["passed"]
