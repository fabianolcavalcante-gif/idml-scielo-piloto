import copy
import hashlib
import json
from pathlib import Path

import pytest

from idml_foundation.services.validation_diagnosis import describe_validation
from idml_foundation.services.validation_followups import query_followups, wayta_followup
from tests.test_validation_diagnosis import stored_result
from tests.test_xpm_query_semantics import ORCID, assess, sample


def selected(public_change=None, deposit=None):
    scope, _package, now, evidence = sample()
    for receipt in evidence["receipts"]:
        body = json.loads(receipt["payload"])
        if receipt["kind"] == "orcid" and public_change:
            public_change(body)
        if receipt["kind"] == "crossref" and deposit:
            body["message"]["author"][0]["ORCID"] = deposit
        receipt["payload"] = json.dumps(body)
        receipt["response_sha256"] = hashlib.sha256(receipt["payload"].encode()).hexdigest()
    return assess(scope, now, evidence)


def codes(value):
    return {r["code"]: r for r in query_followups(value)}


def test_actual_semantic_results_are_projected_without_identity_claim_or_mutation():
    value = selected(deposit=f"https://orcid.org/{ORCID}")
    before = copy.deepcopy(value)
    rows = query_followups(value)
    assert len(rows) == 3
    assert all(r["status"] == "observed" and r["next_action"] for r in rows)
    assert {r["source_status"] for r in rows} == {"matched"}
    assert sum("titularidade" in r["detail"] for r in rows) == 2
    assert value == before
    assert ORCID not in json.dumps(rows) and "Ana" not in json.dumps(rows)


@pytest.mark.parametrize(
    "change,description",
    [
        (lambda b: b["name"].pop("family-name"), "nome suficiente"),
        (lambda b: b["name"].update({"family-name": {"value": "Other"}}), "não coincide"),
        (lambda b: b["name"].update(visibility="private"), "não está disponível"),
    ],
)
def test_public_name_problem_kept_separate_from_matching_crossref_deposit(change, description):
    value = selected(public_change=change, deposit=f"https://orcid.org/{ORCID}")
    rows = query_followups(value)
    public = next(r for r in rows if r["code"].startswith("query-orcid-"))
    deposit = next(r for r in rows if r["code"].startswith("crossref-orcid-link-"))
    assert public["source_status"] == "conflict" and public["status"] == "action-required"
    assert description in public["detail"]
    assert deposit["source_status"] == "matched"
    assert "titularidade" in deposit["detail"]


def test_missing_deposit_is_not_a_conflict_or_permission_to_remove_orcid():
    rows = query_followups(selected())
    row = next(r for r in rows if r["code"].startswith("crossref-orcid-link-"))
    assert row["source_status"] == "not-deposited" and row["status"] == "observed"
    assert "não é uma divergência" in row["detail"]
    assert "não remover" in row["next_action"]


@pytest.mark.parametrize(
    "deposit,reason",
    [
        ("https://orcid.org/0000-0001-5109-3700", "difere"),
        ("invalid", "inválido"),
    ],
)
def test_deposit_conflict_cannot_be_hidden_by_matching_public_name(deposit, reason):
    rows = query_followups(selected(deposit=deposit))
    row = next(r for r in rows if r["code"].startswith("crossref-orcid-link-"))
    assert row["source_status"] == "conflict" and row["status"] == "action-required"
    assert reason in row["detail"]


def test_failed_crossref_blocks_deposit_interpretation():
    scope, _package, now, evidence = sample()
    evidence["receipts"][0].update(status="unavailable", payload=None, response_sha256=None)
    rows = codes(assess(scope, now, evidence))
    assert "crossref-links-unavailable" in rows
    assert any("falha de rede" in r["next_action"] for r in rows.values())
    assert not any(k.startswith("crossref-orcid-link-") for k in rows)


@pytest.mark.parametrize(
    "field,value",
    [
        ("version", "unknown"),
        ("checks", None),
        ("checks", []),
        ("checks", [None]),
        ("required_queries_complete", True),
        ("authenticated_orcid_ownership", True),
        ("crossref_author_links", None),
    ],
)
def test_unknown_inconsistent_or_missing_contract_is_not_interpreted(field, value):
    data = selected()
    data[field] = value
    assert list(codes(data)) == ["selected-query-evidence-unavailable"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("kind", []),
        ("identifier_sha256", None),
        ("response_sha256", None),
        ("reason", "private-text"),
        ("status", "approved"),
        ("public_name_check", "fuzzy-match"),
    ],
)
def test_inconsistent_public_match_is_not_displayed_as_match(field, value):
    data = selected()
    data["checks"][1][field] = value
    assert list(codes(data)) == ["selected-query-evidence-unavailable"]
    assert "private-text" not in json.dumps(query_followups(data))


@pytest.mark.parametrize(
    "case",
    [
        "duplicate",
        "missing_crossref",
        "wrong_receipt",
        "extra_link",
        "missing_link",
        "other_orcid",
        "claim",
    ],
)
def test_query_and_deposit_sets_must_be_consistent(case):
    data = selected()
    links = data["crossref_author_links"]
    if case == "duplicate":
        data["checks"].append(data["checks"][0])
    elif case == "missing_crossref":
        data["checks"].pop(0)
    elif case == "wrong_receipt":
        links["response_sha256"] = "f" * 64
    elif case == "extra_link":
        links["checks"].append(copy.deepcopy(links["checks"][0]))
    elif case == "missing_link":
        links["checks"] = []
    elif case == "other_orcid":
        links["checks"][0]["identifier_sha256"] = "f" * 64
    else:
        links["authenticated_ownership"] = True
    assert list(codes(data)) == ["selected-query-evidence-unavailable"]


def test_diagnosis_integration_preserves_warning_counts_and_selected_query_states():
    result = stored_result()
    result["formal_validation"]["xpm"]["selected_queries"] = selected()
    before = copy.deepcopy(result)
    diagnosis = describe_validation(result)
    rows = {r["code"]: r for r in diagnosis["items"]}
    assert rows["packtools-warnings-review"]["counts"] == {"warning": 5}
    assert rows["spsvalidator-warnings-review"]["counts"] == {"warning": 5}
    assert rows["xpm-warnings-review"]["counts"] == {"warning": 2}
    assert all("next_action" in rows[k] for k in rows if k.endswith("warnings-review"))
    assert any(k.startswith("query-orcid-") for k in rows)
    assert diagnosis["approval_granted"] is False and result == before


def test_unbound_outer_xpm_cannot_supply_nested_query_diagnoses():
    result = stored_result()
    result["formal_validation"]["xpm"]["selected_queries"] = selected()
    result["formal_validation"]["xpm"]["candidate_package_sha256"] = "f" * 64
    rows = describe_validation(result)["items"]
    assert not any(r["code"].startswith(("query-", "crossref-orcid-link-")) for r in rows)


def test_warning_zero_or_unknown_never_becomes_warning_acceptance():
    result = stored_result()
    for run in result["formal_validation"]["external_runs"]:
        run["counts"]["warning"] = 0
    result["formal_validation"]["xpm"]["counts"]["warnings"] = 0
    diagnosis = describe_validation(result)
    assert not any(r["code"].endswith("warnings-review") for r in diagnosis["items"])
    assert diagnosis["approval_granted"] is False


def native_cases():
    # Archived execution, not fresh queries or a new XPM run.
    path = (
        Path(__file__).parents[1] / "benchmarks/qualification/reports/vh1-xpm-composed-real-v1.json"
    )
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == (
        "aeaafc8e2375a3d464cfccf749ec95ba98fb8115f12d60cd6b9839e9e30dc5d2"
    )
    return json.loads(raw)["cases"]


def test_native_archived_queries_keep_seven_deposits_and_four_public_name_conflicts():
    counts = []
    for case in native_cases()[:2]:
        assessment = case["assessment"]
        before = copy.deepcopy(assessment)
        rows = query_followups(assessment["selected_queries"])
        public = [r for r in rows if r["code"].startswith("query-orcid-")]
        links = [r for r in rows if r["code"].startswith("crossref-orcid-link-")]
        assert all(r["source_status"] == "matched" for r in links)
        counts.append((len(links), sum(r["source_status"] == "conflict" for r in public)))
        wayta = wayta_followup(assessment["compatibility"])
        assert wayta["code"] == "wayta-service-observation"
        assert "esgotado" in wayta["detail"] and "não consultou" in wayta["detail"]
        assert assessment == before
    assert counts == [(3, 0), (4, 4)]


@pytest.mark.parametrize(
    "field,value",
    [
        ("institution_identity_verified", True),
        ("article_query_completed", True),
        ("mandatory_affiliation_validation_required", False),
        ("release_approved", True),
        ("policy_version", "unknown"),
        ("normative_sha256", "f" * 64),
        ("service_report_sha256", None),
        ("service_observation", {}),
    ],
)
def test_wayta_inconsistent_qualification_does_not_become_institution_verification(field, value):
    compatibility = copy.deepcopy(native_cases()[0]["assessment"]["compatibility"])
    compatibility["wayta"][field] = value
    assert wayta_followup(compatibility)["code"] == "wayta-evidence-unavailable"


def test_wayta_http_success_does_not_validate_institution():
    compatibility = copy.deepcopy(native_cases()[0]["assessment"]["compatibility"])
    compatibility["wayta"]["service_observation"].update(
        outcome="http_response",
        http_status=200,
        response_sha256="f" * 64,
    )
    row = wayta_followup(compatibility)
    assert row["status"] == "action-required"
    assert "não consultou" in row["detail"]
    assert "obrigatoriamente" in row["next_action"]
