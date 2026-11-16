import copy
import json

import pytest

from ops.gate_vh1_scoped import REPORTS, ROOT, evaluate


def evidence():
    return (
        json.loads((REPORTS / "vh1-scoped-socket-v1.json").read_bytes()),
        json.loads((REPORTS / "vh1-scoped-images-v1.json").read_bytes()),
    )


def check(report, images):
    return evaluate(
        report,
        images,
        json.loads((REPORTS / "vh1-lot2-baseline-v1.json").read_bytes()),
        (ROOT / "config/validator-registry-vh1-scoped.json").read_bytes(),
        lambda path: (ROOT / path).read_bytes(),
    )


def test_scoped_integration_gate_passes_without_release_approval():
    result = check(*evidence())
    assert result["passed"] is True, result
    assert result["formal_xml_approved"] is False


@pytest.mark.parametrize(
    "change",
    [
        "missing_case",
        "duplicate_case",
        "missing_tool",
        "missing_doi",
        "missing_orcid",
        "integer_boolean",
        "foreign_scope",
        "wrong_package",
        "wrong_image",
        "changed_code",
        "changed_native",
        "changed_wrapper",
        "missing_negative",
        "revoked_accepted",
        "release_approved",
        "missing_binding",
        "wrong_registry",
    ],
)
def test_scoped_gate_rejects_incomplete_or_tampered_evidence(change):
    report, images = evidence()
    assessment = report["cases"][1]["assessment"]
    run = assessment["external_runs"][1]
    authority = run["authority_verification"]
    if change == "missing_case":
        report["cases"].pop()
    elif change == "duplicate_case":
        report["cases"][1] = copy.deepcopy(report["cases"][0])
    elif change == "missing_tool":
        assessment["external_runs"].pop()
    elif change == "missing_doi":
        authority["checks"]["doi"] = []
    elif change == "missing_orcid":
        authority["checks"]["orcid"] = []
    elif change == "integer_boolean":
        authority["checks"]["doi"] = [1]
    elif change == "foreign_scope":
        authority["binding"]["scope_sha256"] = "0" * 64
    elif change == "wrong_package":
        run["candidate_sha256"] = "0" * 64
    elif change == "wrong_image":
        run["tool_sha256"] = "0" * 64
    elif change == "changed_code":
        report["code_sha256"]["scoped_validator_broker.py"] = "0" * 64
    elif change == "changed_native":
        images["validators"]["spsvalidator"]["runtime"]["package_trees"] = {}
    elif change == "changed_wrapper":
        images["validators"]["packtools"]["runtime"]["wrappers_sha256"] = {}
    elif change == "missing_negative":
        report["negative_controls"].pop("foreign-tenant")
    elif change == "revoked_accepted":
        report["negative_controls"]["revoked"]["not_approved"] = False
    elif change == "release_approved":
        assessment["ready_for_scielo"] = True
    elif change == "missing_binding":
        del authority["binding"]
    else:
        report["registry_sha256"] = "0" * 64
    assert check(report, images)["passed"] is False
