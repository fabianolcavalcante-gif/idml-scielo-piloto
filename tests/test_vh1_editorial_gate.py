import copy
import json

import pytest

from ops.gate_vh1_editorial import REPORT, ROOT, evaluate


def evidence():
    return json.loads(REPORT.read_bytes())


def check(report):
    registry = json.loads((ROOT / "config/validator-registry-vh1.json").read_bytes())
    return evaluate(report, registry, lambda name: (ROOT / "ops" / name).read_bytes())


def test_pinned_native_qualification_passes_but_is_not_xml_or_deployment_approval():
    result = check(evidence())
    assert result["passed"] is True
    assert result["formal_xml_approved"] is False


@pytest.mark.parametrize(
    "change",
    [
        "absent_doi",
        "absent_orcid",
        "wrong_image",
        "changed_source",
        "missing_negative",
        "unavailable_passed",
        "missing_case",
        "duplicate_case",
        "claimed_approval",
        "xml_changed",
        "wrong_package",
    ],
)
def test_gate_cannot_accept_missing_or_forged_evidence(change):
    report = evidence()
    row = report["cases"][1]["validators"]["spsvalidator"]
    if change == "absent_doi":
        row["native_doi_comparisons"] = 0
    elif change == "absent_orcid":
        row["native_context_evidence"]["orcid"] = []
    elif change == "wrong_image":
        row["image_id"] = "sha256:" + "0" * 64
    elif change == "changed_source":
        report["code_sha256"]["editorial_authority.py"] = "0" * 64
    elif change == "missing_negative":
        del row["negative_controls"]["section"]
    elif change == "unavailable_passed":
        row["unavailable_control"]["native_evidence"]["orcid"] = [True] * 4
    elif change == "missing_case":
        report["cases"].pop()
    elif change == "duplicate_case":
        report["cases"][1] = copy.deepcopy(report["cases"][0])
    elif change == "claimed_approval":
        report["formal_xml_approved"] = True
    elif change == "wrong_package":
        row["package_sha256"] = "0" * 64
    else:
        row["xml_unchanged"] = False
    assert check(report)["passed"] is False
