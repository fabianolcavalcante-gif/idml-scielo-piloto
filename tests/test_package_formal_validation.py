import hashlib
import json

import pytest

from idml_foundation.release.validation_engine import (
    IssueCategory,
    IssueSeverity,
    UnifiedIssue,
    ValidatorRun,
    ValidatorStatus,
)
from idml_foundation.services.package_validation import assess_package


def completed(candidate, specification):
    return ValidatorRun(
        name=specification.name,
        version=specification.version,
        status=ValidatorStatus.COMPLETED,
        candidate_sha256=hashlib.sha256(candidate).hexdigest(),
        tool_sha256=specification.tool_sha256,
        profile_id=specification.profile_id,
        adapter_contract=specification.adapter_contract,
        sanitized_output_sha256="a" * 64,
    )


def test_unconfigured_validators_never_pass():
    result = assess_package(xml=b"<article/>", package=b"package")
    assert result["state"] == "validation-unavailable"
    assert len(result["external_runs"]) == 2
    assert all(r["status"] == "unavailable" for r in result["external_runs"])
    assert not result["ready_for_scielo"] and not result["complete"]


def test_distinct_inputs_are_bound_and_success_does_not_bypass_xpm():
    seen = []

    def execute(candidate, specification):
        seen.append((specification.name, candidate))
        return completed(candidate, specification)

    result = assess_package(xml=b"xml", package=b"zip", executor=execute)
    assert seen == [("packtools", b"xml"), ("spsvalidator", b"zip")]
    assert all(r["passed"] for r in result["external_runs"])
    assert result["reasons"] == ["xpm-executor-not-configured"]
    assert not result["production_activation_authorized"]
    assert not result["ready_for_scielo"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("candidate_sha256", "b" * 64),
        ("tool_sha256", "b" * 64),
        ("version", "wrong"),
        ("profile_id", "wrong"),
        ("adapter_contract", "wrong"),
        ("name", "wrong"),
        ("sanitized_output_sha256", None),
    ],
)
def test_mismatched_external_evidence_is_unavailable(field, value):
    def execute(candidate, specification):
        return completed(candidate, specification).model_copy(update={field: value})

    result = assess_package(xml=b"xml", package=b"zip", executor=execute)
    assert all(r["status"] == "unavailable" for r in result["external_runs"])
    assert not result["ready_for_scielo"]


def test_errors_remain_visible_without_disclosing_content():
    def execute(candidate, specification):
        run = completed(candidate, specification)
        return run.model_copy(
            update={
                "issues": (
                    UnifiedIssue(
                        validator=specification.name,
                        severity=IssueSeverity.ERROR,
                        category=IssueCategory.SEMANTIC,
                        code="private-code",
                        message="private-article-text",
                    ),
                )
            }
        )

    result = assess_package(xml=b"xml", package=b"zip", executor=execute)
    assert result["state"] == "blocked"
    assert result["external_runs"][0]["counts"]["error"] == 1
    assert "private" not in json.dumps(result)


def test_executor_exception_does_not_leak():
    def execute(candidate, specification):
        raise TimeoutError("private credentials")

    result = assess_package(xml=b"xml", package=b"zip", executor=execute)
    assert result["state"] == "validation-unavailable"
    assert "private" not in json.dumps(result)


def test_missing_registry_fails_closed(monkeypatch):
    def unavailable(path):
        raise FileNotFoundError("private path")

    monkeypatch.setattr(
        "idml_foundation.services.package_validation.load_validator_registry", unavailable
    )
    result = assess_package(xml=b"xml", package=b"zip")
    assert result["reasons"] == ["validator-registry-unavailable"]
    assert not result["complete"]
