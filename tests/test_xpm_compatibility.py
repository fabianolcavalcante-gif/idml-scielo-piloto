import hashlib
import json
from datetime import UTC, datetime, timedelta
from io import BytesIO
from uuid import uuid4
from zipfile import ZipFile, ZipInfo

import pytest

from idml_foundation.release.xpm import XpmAttestation
from idml_foundation.release.xpm_compatibility import (
    IMAGE,
    TOOL_SHA256,
    VENDOR_COMPARISON_SHA256,
    XpmCompatibilityEvidence,
    assess_xpm_compatibility,
)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def zip_xml(xml):
    stream = BytesIO()
    with ZipFile(stream, "w") as archive:
        archive.writestr(ZipInfo("article.xml", (2000, 1, 1, 0, 0, 0)), xml)
    return stream.getvalue()


def row(owner, index):
    return (
        '<tr class="error"><td class="td_label">doi <a>[?]</a></td>'
        f'<td class="td_status">[ERROR] [E{index}]</td>'
        '<td class="td_message">10.1590/synthetic is registered as belonging to '
        f'{owner}. </td><td class="td_xml"></td></tr>'
    )


@pytest.fixture
def inputs():
    now = datetime.now(UTC)
    xml = b"""<article specific-use="sps-1.10" dtd-version="1.3"><front><journal-meta>
    <journal-title-group><journal-title>Exact journal</journal-title></journal-title-group>
    <issn>1111-1111</issn></journal-meta><article-meta>
    <article-id pub-id-type="doi">10.1590/synthetic</article-id>
    <title-group><article-title>Exact article</article-title></title-group>
    </article-meta></front></article>"""
    package = zip_xml(xml)
    report = (
        "<html><body><!-- 4.0.096 22/04/2019 -->"
        "Total of blocking errors: 1 Total of fatal errors: 1 "
        "Total of errors: 3 Total of warnings: 1 <table>"
        + row("Exact journal", 1)
        + row("Exact article", 2)
        + '<tr class="error"><td>Unknown real error</td></tr></table></body></html>'
    ).encode()
    crossref = json.dumps(
        {
            "status": "ok",
            "message": {
                "DOI": "10.1590/synthetic",
                "ISSN": ["1111-1111"],
                "container-title": ["Exact journal"],
                "title": ["Exact article"],
            },
        }
    ).encode()
    scope = {
        "organization_id": str(uuid4()),
        "resource_id": str(uuid4()),
        "source_idml_sha256": "a" * 64,
        "journal_profile_id": "esa-aop-1.1.0",
        "xml_sha256": sha(xml),
        "package_sha256": sha(package),
    }
    trusted = XpmCompatibilityEvidence(
        contract_version="xpm-compatibility-evidence-1.0",
        scope=scope,
        attestation=XpmAttestation(
            candidate_package_sha256=sha(package),
            report_sha256=sha(report),
            tool_sha256=TOOL_SHA256,
            xpm_version="4.0.096",
            command_id="synthetic",
            environment="synthetic-no-native-execution",
        ),
        image=IMAGE,
        vendor_comparison_sha256=VENDOR_COMPARISON_SHA256,
        crossref_sha256=sha(crossref),
        crossref_retrieved_at=now,
        required_queries_complete=True,
    )
    return dict(
        xml=xml,
        package=package,
        report=report,
        crossref=crossref,
        trusted=trusted,
        expected_scope=scope,
        now=now,
    )


def rebind(inputs):
    """Synthetic trusted executor helper; never a client-controlled production path."""
    inputs["package"] = zip_xml(inputs["xml"])
    scope = {
        **inputs["expected_scope"],
        "xml_sha256": sha(inputs["xml"]),
        "package_sha256": sha(inputs["package"]),
    }
    trusted = inputs["trusted"].model_dump(mode="json")
    trusted.update(scope=scope, crossref_sha256=sha(inputs["crossref"]))
    trusted["attestation"].update(
        candidate_package_sha256=scope["package_sha256"], report_sha256=sha(inputs["report"])
    )
    inputs.update(expected_scope=scope, trusted=XpmCompatibilityEvidence.model_validate(trusted))


def test_exact_matches_classified_but_raw_errors_and_release_remain(inputs):
    result = assess_xpm_compatibility(**inputs)
    assert len(result.exceptions) == 2
    assert result.original.errors == 3 and not result.original.passed
    assert result.unresolved_counts == {
        "blocking_errors": 1,
        "fatal_errors": 1,
        "errors": 1,
        "warnings": 1,
    }
    assert not result.release_approved and not result.homologation_ready
    assert "unresolved-xpm-findings" in result.reasons


@pytest.mark.parametrize("field", ["xml", "package", "report", "crossref"])
def test_untrusted_bytes_tampered_rejected(inputs, field):
    inputs[field] += b"tampered"
    with pytest.raises(ValueError):
        assess_xpm_compatibility(**inputs)


@pytest.mark.parametrize(
    "field", ["organization_id", "resource_id", "source_idml_sha256", "journal_profile_id"]
)
def test_cross_scope_reuse_rejected(inputs, field):
    inputs["expected_scope"] = {**inputs["expected_scope"], field: str(uuid4())}
    with pytest.raises(ValueError):
        assess_xpm_compatibility(**inputs)


@pytest.mark.parametrize("field", ["image", "vendor_comparison_sha256"])
def test_unqualified_runtime_rejected(inputs, field):
    inputs["trusted"] = inputs["trusted"].model_copy(update={field: "a" * 64})
    with pytest.raises(ValueError, match="unqualified_tool"):
        assess_xpm_compatibility(**inputs)


@pytest.mark.parametrize("days", [-1, 8])
def test_stale_or_future_authority_rejected(inputs, days):
    inputs["now"] += timedelta(days=days)
    with pytest.raises(ValueError):
        assess_xpm_compatibility(**inputs)


@pytest.mark.parametrize("replacement", ["Exact journals", "Other journal", "exact journal"])
def test_near_matches_are_not_exceptions(inputs, replacement):
    inputs["xml"] = inputs["xml"].replace(b"Exact journal", replacement.encode())
    rebind(inputs)
    result = assess_xpm_compatibility(**inputs)
    assert [x.rule_id for x in result.exceptions] == ["xpm-doi-article-exact-1.0"]
    assert result.unresolved_counts["errors"] == 2


@pytest.mark.parametrize("change", ["duplicate", "hidden", "status", "message", "label"])
def test_unknown_or_ambiguous_report_row_not_accepted(inputs, change):
    original = row("Exact journal", 1).encode()
    if change == "duplicate":
        replacement = original * 2
    elif change == "hidden":
        replacement = original.replace(b"Exact journal", b"<script>Exact journal</script>")
    elif change == "status":
        replacement = original.replace(b"[ERROR]", b"[FATAL ERROR]")
    elif change == "label":
        replacement = original.replace(b"doi <", b"publisher <")
    else:
        replacement = original.replace(b"belonging", b"NOT belonging")
    inputs["report"] = inputs["report"].replace(original, replacement)
    rebind(inputs)
    result = assess_xpm_compatibility(**inputs)
    assert all(x.rule_id != "xpm-doi-journal-exact-1.0" for x in result.exceptions)


def test_missing_queries_never_become_success(inputs):
    inputs["trusted"] = inputs["trusted"].model_copy(update={"required_queries_complete": False})
    result = assess_xpm_compatibility(**inputs)
    assert "required-queries-incomplete" in result.reasons and not result.homologation_ready


@pytest.mark.parametrize("field", ["DOI", "ISSN"])
def test_other_doi_or_journal_record_refused(inputs, field):
    source = json.loads(inputs["crossref"])
    source["message"][field] = "wrong" if field == "DOI" else ["9999-9999"]
    inputs["crossref"] = json.dumps(source).encode()
    rebind(inputs)
    with pytest.raises(ValueError):
        assess_xpm_compatibility(**inputs)


def test_xml_is_really_inside_bound_package(inputs):
    inputs["package"] = zip_xml(b"<article/>")
    scope = {**inputs["expected_scope"], "package_sha256": sha(inputs["package"])}
    trusted = inputs["trusted"].model_dump(mode="json")
    trusted["scope"] = scope
    trusted["attestation"]["candidate_package_sha256"] = scope["package_sha256"]
    inputs.update(trusted=XpmCompatibilityEvidence.model_validate(trusted), expected_scope=scope)
    with pytest.raises(ValueError, match="package_xml_mismatch"):
        assess_xpm_compatibility(**inputs)
