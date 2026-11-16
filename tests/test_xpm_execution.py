"""Synthetic execution evidence; these tests do not run XPM or approve real XML."""

import hashlib
import json
from io import BytesIO
from uuid import uuid4
from zipfile import ZipFile

import pytest

from idml_foundation.release.xpm import XpmAttestation
from idml_foundation.release.xpm_compatibility import IMAGE, TOOL_SHA256
from idml_foundation.services.package_validation import assess_package
from idml_foundation.services.xpm_execution import XpmExecutionEvidence, assess_xpm_execution
from tests.test_package_formal_validation import completed


def sha(data):
    return hashlib.sha256(data).hexdigest()


def execution(package, scope, *, errors=0, warnings=0, queries=True):
    report = (
        "<html><body><!-- 4.0.096 01/01/2026 -->"
        "<p>Total of blocking errors: 0</p><p>Total of fatal errors: 0</p>"
        f"<p>Total of errors: {errors}</p><p>Total of warnings: {warnings}</p>"
        "</body></html>"
    ).encode()
    return XpmExecutionEvidence(
        scope=scope,
        report=report,
        image=IMAGE,
        required_queries_complete=queries,
        attestation=XpmAttestation(
            candidate_package_sha256=sha(package),
            report_sha256=sha(report),
            tool_sha256=TOOL_SHA256,
            xpm_version="4.0.096",
            command_id="synthetic-only",
            environment="synthetic-only",
        ),
    )


@pytest.fixture
def inputs():
    xml = b"<article/>"
    stream = BytesIO()
    with ZipFile(stream, "w") as archive:
        archive.writestr("article.xml", xml)
    package = stream.getvalue()
    scope = {
        "organization_id": str(uuid4()),
        "resource_id": str(uuid4()),
        "source_idml_sha256": "a" * 64,
        "journal_profile_id": "esa-aop-1.1.0",
        "xml_sha256": sha(xml),
        "package_sha256": sha(package),
    }
    return dict(xml=xml, package=package, expected_scope=scope)


@pytest.mark.parametrize(
    "errors,warnings,queries", [(0, 0, True), (1, 0, True), (0, 1, True), (0, 0, False)]
)
def test_execution_diagnostics_never_grant_promotion(inputs, errors, warnings, queries):
    def run(package, scope):
        return execution(package, scope, errors=errors, warnings=warnings, queries=queries)

    result = assess_package(**inputs, executor=completed, xpm_executor=run)
    assert result["xpm"]["status"] == "completed"
    assert result["xpm"]["counts"]["errors"] == errors
    assert result["xpm"]["counts"]["warnings"] == warnings
    assert result["xpm"]["required_queries_complete"] == queries
    assert (result["state"] == "blocked") == bool(errors)
    assert ("xpm-warnings-pending" in result["reasons"]) == bool(warnings)
    assert ("xpm-required-queries-incomplete" in result["reasons"]) == (not queries)
    assert not result["complete"] and not result["ready_for_scielo"]
    assert "synthetic-only" not in json.dumps(result)  # No environment/command text exposed.


@pytest.mark.parametrize(
    "field",
    [
        "organization_id",
        "resource_id",
        "source_idml_sha256",
        "journal_profile_id",
        "xml_sha256",
        "package_sha256",
    ],
)
def test_wrong_execution_scope_rejected(inputs, field):
    def run(package, scope):
        scope[field] = str(uuid4()) if field.endswith("_id") else "b" * 64
        return execution(package, scope)

    result = assess_xpm_execution(**inputs, executor=run)
    assert result["status"] == "unavailable"


@pytest.mark.parametrize(
    "field,value",
    [
        ("candidate_package_sha256", "b" * 64),
        ("report_sha256", "b" * 64),
        ("tool_sha256", "b" * 64),
        ("xpm_version", "4.0.097"),
        ("contract_version", "2.0.0"),
    ],
)
def test_wrong_attestation_rejected(inputs, field, value):
    def run(package, scope):
        row = execution(package, scope)
        row.attestation = row.attestation.model_copy(update={field: value})
        return row

    assert assess_xpm_execution(**inputs, executor=run)["status"] == "unavailable"


@pytest.mark.parametrize("kind", ["image", "report", "exception", "queries_type"])
def test_untrusted_or_failed_execution_is_sanitized(inputs, kind, recwarn):
    def run(package, scope):
        if kind == "exception":
            raise TimeoutError("private-token-and-article")
        row = execution(package, scope)
        if kind == "image":
            row.image = "private-wrong-image"
        elif kind == "report":
            row.report = b"private-malformed-report"
            row.attestation.report_sha256 = sha(row.report)
        else:
            row = row.model_copy(update={"required_queries_complete": "private-token"})
        return row

    result = assess_xpm_execution(**inputs, executor=run)
    assert result["status"] == "unavailable"
    assert "private" not in json.dumps(result)
    assert not recwarn.list


@pytest.mark.parametrize("kind", ["scope", "xml", "zip", "duplicate", "different_xml", "path"])
def test_bad_inputs_do_not_dispatch(inputs, kind):
    def forbidden(*args):
        pytest.fail("invalid input reached executor")

    if kind == "scope":
        inputs["expected_scope"] = None
    elif kind == "xml":
        inputs["xml"] = b"changed"
    elif kind == "zip":
        inputs["package"] = b"not zip"
        inputs["expected_scope"]["package_sha256"] = sha(inputs["package"])
    else:
        stream = BytesIO()
        with ZipFile(stream, "w") as archive:
            archive.writestr(
                "../article.xml" if kind == "path" else "article.xml",
                b"changed" if kind == "different_xml" else inputs["xml"],
            )
            if kind == "duplicate":
                archive.writestr("ARTICLE.XML", inputs["xml"])
        inputs["package"] = stream.getvalue()
        inputs["expected_scope"]["package_sha256"] = sha(inputs["package"])
    assert assess_xpm_execution(**inputs, executor=forbidden)["status"] == "unavailable"


def test_registry_failure_does_not_dispatch_xpm(inputs, tmp_path):
    def forbidden(*args):
        pytest.fail("invalid registry reached executor")

    result = assess_package(
        **inputs, registry_path=tmp_path / "missing.json", xpm_executor=forbidden
    )
    assert result["reasons"] == ["validator-registry-unavailable"]
