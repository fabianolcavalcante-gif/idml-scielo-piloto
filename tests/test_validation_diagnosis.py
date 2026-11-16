import copy
import json

import pytest

from idml_foundation.models import Job, Organization
from idml_foundation.rbac import Role
from idml_foundation.release.xpm_compatibility import TOOL_SHA256
from idml_foundation.services.validation_diagnosis import describe_validation
from tests.test_phase7_v10_workflow import _headers, _user


def stored_result():
    return {
        "package_sha256": "a" * 64,
        "validation": {
            "xml_sha256": "b" * 64,
            "validator_profile": "jats-1.3-mathml3+sps-baseline-1.2.0",
            "valid": True,
            "issues": [],
        },
        "formal_validation": {
            "version": "package-formal-assessment-1.0",
            "package_sha256": "a" * 64,
            "xml_sha256": "b" * 64,
            "state": "blocked",
            "ready_for_scielo": False,
            "external_runs": [
                {
                    "name": name,
                    "input_kind": kind,
                    "candidate_sha256": candidate * 64,
                    "status": "completed",
                    "report_sha256": "c" * 64,
                    "tool_sha256": "d" * 64,
                    "counts": {"blocking": 0, "critical": 0, "error": 0, "warning": 5},
                }
                for name, kind, candidate in (
                    ("packtools", ".xml", "b"),
                    ("spsvalidator", ".zip", "a"),
                )
            ],
            "xpm": {
                "status": "completed",
                "attested": True,
                "candidate_package_sha256": "a" * 64,
                "report_sha256": "e" * 64,
                "tool_sha256": TOOL_SHA256,
                "xpm_version": "4.0.096",
                "required_queries_complete": False,
                "counts": {"blocking_errors": 3, "fatal_errors": 1, "errors": 4, "warnings": 2},
                "compatibility": {"unresolved_counts": {"errors": 1}},
            },
        },
    }


def items(result):
    return {i["code"]: i for i in describe_validation(result)["items"]}


def test_diagnosis_separates_known_capability_from_unclassified_article_errors():
    result = stored_result()
    before = copy.deepcopy(result)
    diagnosis = describe_validation(result)
    rows = items(result)
    assert {i["category"] for i in diagnosis["items"]} == {"xml", "tool", "editorial"}
    assert rows["xpm-raw-findings"]["counts"] == result["formal_validation"]["xpm"]["counts"]
    assert rows["packtools-findings"]["counts"]["warning"] == 5
    assert rows["packtools-findings"]["status"] == "observed"
    assert rows["xpm-legacy-capability"]["status"] == "known-limitation"
    assert "não atribuição de causa" in rows["xpm-legacy-capability"]["detail"]
    assert rows["doctype-delivery-pending"]["category"] == "editorial"
    assert "xpm-queries-pending" in rows
    assert diagnosis["basis"] == "stored-job-result"
    assert diagnosis["approval_granted"] is False
    assert diagnosis["modifies_validation"] is False
    assert result == before


def test_real_header_error_remains_a_correction_with_legacy_context_present():
    result = stored_result()
    result["validation"].update(
        valid=False,
        issues=[
            {
                "stage": "jats-dtd",
                "severity": "error",
                "code": "unexpected-doctype",
                "message": "private article text",
            },
        ],
    )
    rows = items(result)
    assert rows["doctype-pair-mismatch"]["status"] == "action-required"
    assert rows["offline-findings"]["counts"]["error"] == 1
    assert "xpm-legacy-capability" in rows
    assert "private" not in json.dumps(rows)


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "failed"),
        ("attested", "true"),
        ("attested", False),
        ("candidate_package_sha256", "f" * 64),
        ("report_sha256", None),
        ("counts", {"errors": 0}),
    ],
)
def test_unbound_xpm_cannot_explain_legacy_errors(field, value):
    result = stored_result()
    result["formal_validation"]["xpm"][field] = value
    rows = items(result)
    assert "xpm-unavailable" in rows
    assert "xpm-legacy-capability" not in rows
    assert "xpm-raw-findings" not in rows


@pytest.mark.parametrize("field,value", [("tool_sha256", "f" * 64), ("xpm_version", "other")])
def test_known_limitation_only_for_qualified_tool(field, value):
    result = stored_result()
    result["formal_validation"]["xpm"][field] = value
    assert "xpm-legacy-capability" not in items(result)
    assert "xpm-raw-findings" in items(result)


@pytest.mark.parametrize(
    "field,value",
    [
        ("candidate_sha256", "f" * 64),
        ("input_kind", ".zip"),
        ("report_sha256", None),
        ("status", "failed"),
        ("counts", {"error": 0}),
        ("counts", {"blocking": 0, "critical": 0, "error": False, "warning": 5}),
        ("counts", {"blocking": 0, "critical": 0, "error": -1, "warning": 5}),
    ],
)
def test_inconsistent_modern_receipt_is_not_clean_xml(field, value):
    result = stored_result()
    result["formal_validation"]["external_runs"][0][field] = value
    assert "packtools-unavailable" in items(result)
    assert "packtools-findings" not in items(result)


def test_duplicates_do_not_choose_favorable_receipt():
    result = stored_result()
    result["formal_validation"]["external_runs"].append(
        copy.deepcopy(result["formal_validation"]["external_runs"][0])
    )
    assert "packtools-unavailable" in items(result)


def test_modern_errors_are_actionable_and_not_dismissed_by_legacy_context():
    result = stored_result()
    result["formal_validation"]["external_runs"][0]["counts"]["error"] = 2
    assert items(result)["packtools-findings"]["status"] == "action-required"
    assert items(result)["packtools-findings"]["counts"]["error"] == 2


@pytest.mark.parametrize("value", [None, [], "private", 0, {}])
def test_missing_or_old_job_result_is_explicitly_unavailable(value):
    rows = items(value)
    assert "formal-evidence-unavailable" in rows
    assert "offline-evidence-unavailable" in rows
    assert "xpm-legacy-capability" not in rows


@pytest.mark.parametrize(
    "field,value",
    [
        ("xml_sha256", "f" * 64),
        ("issues", None),
        ("issues", [None]),
        ("issues", [{"severity": []}]),
        ("valid", "true"),
        ("valid", False),
    ],
)
def test_invalid_local_summary_cannot_be_reported_clean(field, value):
    result = stored_result()
    result["validation"][field] = value
    assert "offline-evidence-unavailable" in items(result)
    assert "offline-no-errors" not in items(result)


def test_unrecognized_profile_or_text_cannot_trigger_known_cause():
    result = stored_result()
    result["validation"]["validator_profile"] = []
    result["formal_validation"]["xpm"]["html"] = "<script>private</script> sps-1.10"
    result["validation"]["issues"] = [{"severity": "warning", "message": "sps-1.10 private"}]
    assert "xpm-legacy-capability" not in items(result)
    assert "doctype-delivery-pending" not in items(result)
    assert "private" not in json.dumps(describe_validation(result))


def test_formal_result_for_another_package_cannot_be_used():
    result = stored_result()
    result["formal_validation"]["package_sha256"] = "f" * 64
    rows = items(result)
    assert "formal-evidence-unavailable" in rows
    assert "xpm-raw-findings" not in rows
    assert "packtools-findings" not in rows


def test_conversion_job_has_local_findings_without_formal_approval():
    result = stored_result()
    result.pop("formal_validation")
    result.pop("package_sha256")
    result["xml_sha256"] = "b" * 64
    assert "offline-no-errors" in items(result)
    assert "formal-evidence-unavailable" in items(result)


def test_diagnosis_endpoint_auth_tenant_isolation_and_no_mutation(client, db, settings):
    org = Organization(slug="diagnosis-org", name="Diagnosis")
    other = Organization(slug="diagnosis-other", name="Other")
    db.add_all([org, other])
    db.flush()
    user = _user(db, org, "diagnosis@example.test", Role.OPERATOR)
    other_user = _user(db, other, "other-diagnosis@example.test", Role.OPERATOR)
    job = Job(
        organization_id=org.id,
        kind="scielo.package",
        state="succeeded",
        idempotency_key="diagnosis-job",
        payload={},
        result=stored_result(),
    )
    db.add(job)
    db.flush()
    headers = _headers(db, user, org, settings)
    other_headers = _headers(db, other_user, other, settings)
    path = f"/v1/jobs/{job.id}/validation-diagnosis"
    assert client.get(path).status_code == 401
    assert client.get(path, headers=other_headers).status_code == 404
    before = copy.deepcopy(job.result)
    response = client.get(path, headers=headers)
    assert response.status_code == 200
    assert response.json() == describe_validation(before)
    db.refresh(job)
    assert job.result == before
    assert client.get("/v1/jobs/missing/validation-diagnosis", headers=headers).status_code == 404
