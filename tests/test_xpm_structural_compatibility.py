"""Legacy exceptions require exact diagnostics and independent valid XML."""
# ruff: noqa: F811 -- imported pytest fixtures

import json
from html import escape
from io import BytesIO
from zipfile import ZipFile

import pytest
from lxml import etree

from idml_foundation.pipeline.jats_builder import JATS_DTD_NAME, JATS_PUBLIC_ID, JatsBuilder
from idml_foundation.release.xpm_structural_compatibility import (
    FN_MESSAGE,
    ROOT_MESSAGE,
    assess_xpm_structural_compatibility,
    structural_occurrences,
)
from ops.v05_fixture import complete_article
from tests.test_xpm_compatibility import inputs as doi_inputs  # noqa: F401
from tests.test_xpm_compatibility import rebind, sha
from tests.test_xpm_composed import current
from tests.test_xpm_sps_compatibility import bind_modern
from tests.test_xpm_sps_compatibility import data as sps_inputs  # noqa: F401


def block(xml, filename="article.xml"):
    root = etree.fromstring(xml)
    prefix = (
        "Summary-------[FATAL ERROR] [F1] XML file has DTD errors.........DTD errors----------"
        f'Found: <!DOCTYPE article PUBLIC "{JATS_PUBLIC_ID}" "{JATS_DTD_NAME}">'
        f"Unknown PUBLIC ID: {JATS_PUBLIC_ID}"
    )
    for node in [root, *root.xpath('.//fn[@fn-type="coi-statement"]')]:
        prefix += (
            "Error: Public ID: null "
            f"System ID: file:/work/SciELO_XPM/xml/./{filename} "
            f"Line number: {node.sourceline} Column number: 33 Message: "
            + (ROOT_MESSAGE if node is root else FN_MESSAGE)
        )
    style = (
        f"Something went wrong while working on /work/input_xpm/scielo_package/{filename}: "
        'version "sps-1.10" is not currently supported.'
    )
    return (
        '<table><tr><td class="reports-hidden-block">'
        f'<div class="report-block-xmlrep" id="xmlrep{filename[:-4]}">'
        + escape(prefix)
        + "<br/>Parse/validation finished<br/>"
        + "<p></p><h1>Packtools Style Checker (2.4.2)</h1>"
        + '<div class="error">Total of errors = 1</div><code>'
        + escape(style)
        + "</code></div></td></tr></table>"
    ).encode()


def bind(data):
    rebind(data)
    stream = BytesIO()
    with ZipFile(stream, "w") as archive:
        archive.writestr("article.xml", data["xml"])
        for asset in complete_article().assets:
            archive.writestr(asset.logical_name, b"synthetic fixture asset")
    data["package"] = stream.getvalue()
    data["expected_scope"]["package_sha256"] = sha(data["package"])
    trusted = data["trusted"].model_dump(mode="python")
    trusted["scope"] = data["expected_scope"]
    trusted["attestation"]["candidate_package_sha256"] = sha(data["package"])
    data["trusted"] = type(data["trusted"]).model_validate(trusted)
    bind_modern(data)
    current(data)


@pytest.fixture
def valid(sps_inputs):
    data = sps_inputs
    data["xml"] = JatsBuilder().build(complete_article())
    root = etree.fromstring(data["xml"])
    journal = root.findtext("front/journal-meta/journal-title-group/journal-title")
    title = root.findtext("front/article-meta/title-group/article-title")
    doi = root.findtext('front/article-meta/article-id[@pub-id-type="doi"]')
    data["crossref"] = json.dumps(
        dict(
            status="ok",
            message={
                "DOI": doi,
                "ISSN": [n.text for n in root.findall("front/journal-meta/issn")],
                "container-title": [journal],
                "title": [title],
            },
        )
    ).encode()
    for old, new in (
        ("Exact journal", journal),
        ("Exact article", title),
        ("10.1590/synthetic", doi),
    ):
        data["report"] = data["report"].replace(old.encode(), escape(new).encode())
    data["report"] = data["report"].replace(b"</body>", block(data["xml"]) + b"</body>")
    bind(data)
    return data


def test_valid_independent_xml_allows_only_two_legacy_occurrences(valid):
    result = assess_xpm_structural_compatibility(**valid)
    assert len(result.exceptions) == 2
    assert result.unresolved_counts["fatal_errors"] == 0
    assert result.base.base.original.fatal_errors == 1
    # Other unrelated fixture findings remain; nothing here approves a release.
    assert not result.technical_errors_resolved
    assert not result.release_approved and not result.homologation_ready


@pytest.mark.parametrize(
    "old,new",
    [
        (b'dtd-version="1.3"', b'dtd-version="1.1"'),
        (b'fn-type="coi-statement"', b'fn-type="invented"'),
        (b"with MathML3 v1.3", b"v1.3"),
        (b"<journal-title>", b"<invalid-journal-title>"),
    ],
)
def test_real_xml_errors_never_waived_even_with_clean_modern_receipts(valid, old, new):
    valid["xml"] = valid["xml"].replace(old, new)
    bind(valid)
    with pytest.raises((ValueError, etree.XMLSyntaxError)):
        assess_xpm_structural_compatibility(**valid)


@pytest.mark.parametrize(
    "old,new",
    [
        ("1.1&quot;.", "1.2&quot;."),
        ("[F1]", "[F2]"),
        ("article.xml", "other.xml"),
        ("2.4.2", "2.4.3"),
        ("Total of errors = 1", "Total of errors = 2"),
        ("Parse/validation finished", "Error: another real error Parse/validation finished"),
        ("<code>", '<code hidden="hidden">'),
        ("<h1>", '<h1 style="display:none">'),
        ("<code>", "<code><script>"),
        ("</code>", "</code><code>extra error</code>"),
        ("sps-1.10", "sps-1.9"),
        ("Line number: 3", "Line number: 0"),
        ('class="reports-hidden-block"', 'class="other"'),
    ],
)
def test_unknown_duplicate_hidden_or_unbound_diagnostics_rejected(old, new):
    xml = JatsBuilder().build(complete_article())
    report = block(xml)
    assert old.encode() in report
    with pytest.raises(ValueError):
        structural_occurrences(
            report.replace(old.encode(), new.encode()), etree.fromstring(xml), "article.xml"
        )


def test_duplicate_report_and_embedded_article_text_are_not_diagnostics():
    xml = JatsBuilder().build(complete_article())
    report = block(xml)
    with pytest.raises(ValueError):
        structural_occurrences(report + report, etree.fromstring(xml), "article.xml")
    with pytest.raises(ValueError):
        structural_occurrences(
            b"<pre>" + escape(report.decode()).encode() + b"</pre>",
            etree.fromstring(xml),
            "article.xml",
        )


@pytest.mark.parametrize("field", ["xml", "package", "report", "crossref"])
def test_exact_input_binding_required(valid, field):
    valid[field] += b"altered"
    with pytest.raises(ValueError):
        assess_xpm_structural_compatibility(**valid)


def test_stale_receipt_rejected(valid):
    from datetime import timedelta

    valid["now"] += timedelta(hours=25)
    with pytest.raises(ValueError):
        assess_xpm_structural_compatibility(**valid)


@pytest.mark.parametrize("change", ["error", "missing", "hash", "version", "scope", "image"])
def test_independent_or_trusted_evidence_mismatch_rejected(valid, change):
    from idml_foundation.release.validation_engine import UnifiedIssue
    from idml_foundation.release.xpm_sps_compatibility import bind_runtime_runs

    evidence = valid["sps_evidence"]
    if change == "scope":
        valid["expected_scope"] = {**valid["expected_scope"], "source_idml_sha256": "f" * 64}
    elif change == "image":
        valid["trusted"] = valid["trusted"].model_copy(update={"image": "unknown"})
    elif change == "missing":
        valid["sps_evidence"] = evidence.model_copy(update={"runs": ()})
    else:
        update = {
            "error": {
                "issues": (
                    UnifiedIssue(
                        validator="packtools",
                        category="deterministic",
                        severity="error",
                        code="native-error",
                        message="error",
                    ),
                )
            },
            "hash": {"candidate_sha256": "f" * 64},
            "version": {"version": "unqualified"},
        }[change]
        valid["sps_evidence"] = bind_runtime_runs(
            evidence.scope,
            evidence.xpm_report_sha256,
            (evidence.runs[0].model_copy(update=update), evidence.runs[1]),
            valid["now"],
        )
    with pytest.raises(ValueError):
        assess_xpm_structural_compatibility(**valid)


def test_missing_journal_title_rejected(valid):
    import re

    valid["xml"] = re.sub(rb"<journal-title>.*?</journal-title>", b"", valid["xml"])
    bind(valid)
    with pytest.raises(ValueError):
        assess_xpm_structural_compatibility(**valid)


def test_vendor_space_markers_are_supported_without_stripping_arbitrary_markup():
    xml = JatsBuilder().build(complete_article())
    original = block(xml)
    report = original.replace(
        b"Something went", b'Something<font color="#F56991">&#183;</font>went'
    )
    assert structural_occurrences(
        report, etree.fromstring(xml), "article.xml"
    ) == structural_occurrences(original, etree.fromstring(xml), "article.xml")
    with pytest.raises(ValueError):
        structural_occurrences(
            report.replace(b"#F56991", b"#FFFFFF"), etree.fromstring(xml), "article.xml"
        )
