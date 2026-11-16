import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "ops"))
from external_verification import PREFIX, unavailable_dependency
from validator_adapter_common import sanitize_validator_result

from idml_foundation.release.validation_engine import IssueCategory, IssueSeverity, ValidationEngine
from idml_foundation.services.package_validation import assess_package


def orcid(status="unknown"):
    return {
        "title": "Registered ORCID",
        "item": "contrib-id",
        "validation_type": "registered",
        "response": "WARNING",
        "got_value": status,
        "data": {"status": status},
        "message": "PRIVATE",
        "advice": "PRIVATE",
    }


@pytest.mark.parametrize("wrapped", [False, True])
def test_unavailable_orcid_is_additive_and_private_content_is_removed(wrapped):
    row = orcid()
    raw = {"status": "WARNING", "subject": "contrib", "data": row} if wrapped else row
    result = sanitize_validator_result([raw, raw])
    assert result["summary"] == {"warning": 2, "blocking": 1}
    assert sum(f["code"] == PREFIX + "orcid-registry" for f in result["findings"]) == 1
    assert "PRIVATE" not in json.dumps(result)


@pytest.mark.parametrize("status", ["registered", "not-registered", "invalid", "", None])
def test_unknown_is_not_inferred_from_rule_title(status):
    assert unavailable_dependency(orcid(status)) is None


@pytest.mark.parametrize(
    "exception,expected",
    [
        ("ConnectionError", "doi-registry"),
        ("TimeoutError", "doi-registry"),
        ("HTTPError", None),
        ("ValueError", None),
        ("", None),
    ],
)
def test_doi_requires_explicit_transport_failure(exception, expected):
    row = {
        "title": "registered DOI",
        "item": "article-id",
        "validation_type": "registered",
        "response": "WARNING",
        "data": {"exception_type": exception},
    }
    assert unavailable_dependency(row) == expected
    row["data"]["registered"] = {"title": "different article"}
    assert unavailable_dependency(row) is None


def test_missing_journal_context_is_not_xml_missing_subject():
    row = {
        "title": "table of contents section",
        "item": "subj-group",
        "validation_type": "value in list",
        "response": "WARNING",
        "got_value": "PRIVATE",
        "expected_value": "one of {}",
        "advice": "Unable to check PRIVATE",
    }
    assert unavailable_dependency(row) == "journal-sections"
    row["expected_value"] = ["another section"]
    assert unavailable_dependency(row) is None
    row.update(expected_value="one of {}", got_value=None, validation_type="exist")
    assert unavailable_dependency(row) is None


def test_issue_mismatch_with_known_registry_is_not_unavailability():
    row = {
        "title": "registered issue",
        "item": "volume, number, supplement",
        "validation_type": "value in list",
        "response": "WARNING",
        "advice": "Unable to check if issue is registered",
    }
    assert unavailable_dependency(row) == "journal-issues"
    row["advice"] = "Replace issue with a known value"
    assert unavailable_dependency(row) is None


def test_completed_execution_with_unverified_checks_cannot_pass():
    result = sanitize_validator_result([orcid()])
    run = ValidationEngine().external_run(
        b"xml", result, name="packtools", version="test", tool_sha256="a" * 64
    )
    assert run.status.value == "completed"
    assert not run.passed
    blocker = next(i for i in run.issues if i.severity == IssueSeverity.BLOCKING)
    assert blocker.category == IssueCategory.SYSTEM
    accepted = tuple(
        issue.model_copy(
            update={
                "warning_acceptance_id": "synthetic-acceptance",
                "warning_justification": "Synthetic test of explicit acceptance",
            }
        )
        if issue.severity == IssueSeverity.WARNING
        else issue
        for issue in run.issues
    )
    assert not run.model_copy(update={"issues": accepted}).passed


def test_package_diagnostic_preserves_external_blocker_and_reason():
    def execute(candidate, spec):
        return ValidationEngine().external_run(
            candidate,
            sanitize_validator_result([orcid()]),
            name=spec.name,
            version=spec.version,
            tool_sha256=spec.tool_sha256,
            profile_id=spec.profile_id,
            adapter_contract=spec.adapter_contract,
            sanitized_output_sha256="b" * 64,
        )

    report = assess_package(xml=b"xml", package=b"zip", executor=execute)
    assert report["state"] == "blocked"
    assert "external-verification-unavailable" in report["reasons"]
    assert report["external_runs"][0]["unavailable_external_checks"] == ["orcid-registry"]
    assert not report["ready_for_scielo"]


def test_native_article_data_never_enters_public_rule_identity():
    row = {
        "response": "ERROR",
        "title": "section",
        "item": "sec",
        "validation_type": "exist",
        "data": {"subject": "PRIVATE TITLE"},
    }
    assert "private-title" not in json.dumps(sanitize_validator_result([row]))


def test_exact_native_retry_exhaustion_is_unavailable_not_generic_retry_text():
    rule = {
        "response": "WARNING",
        "title": "registered DOI",
        "item": "article-id",
        "validation_type": "registered",
        "data": {"exception_type": "<class 'tenacity.RetryError'>"},
    }
    assert unavailable_dependency(rule) == "doi-registry"
    rule["data"]["exception_type"] = "some-other-RetryError"
    assert unavailable_dependency(rule) is None
