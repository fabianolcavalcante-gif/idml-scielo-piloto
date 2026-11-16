from pathlib import Path

import pytest
from lxml import etree

from idml_foundation.domain.canonical import (
    BackMatter,
    CanonicalArticle,
    FieldState,
    SourcedText,
    TableBlock,
    TableCellSpan,
)
from idml_foundation.pipeline.jats_builder import XLINK_NS, JatsBuilder
from idml_foundation.pipeline.validation import OfflineJatsValidator, ValidationSeverity
from ops.v05_fixture import complete_article, rich
from tests.domain_helpers import canonical_article, sourced

VENDOR = Path(__file__).parents[1] / "vendor" / "jats" / "1.3"


def test_builder_emits_complete_dtd_valid_and_deterministic_jats() -> None:
    article = CanonicalArticle.model_validate(complete_article().model_dump(mode="json"))
    first = JatsBuilder().build(article)
    second = JatsBuilder().build(article)
    report = OfflineJatsValidator(VENDOR).validate(
        first,
        asset_names={asset.logical_name for asset in article.assets},
    )
    root = etree.fromstring(first)

    assert first == second
    assert report.valid, report.issues
    assert root.xpath("string(front/article-meta/contrib-group/contrib/contrib-id)").endswith(
        "0000-0002-1825-0097"
    )
    assert root.xpath("string(front/article-meta/pub-date/@iso-8601-date)") == "2026-09-08"
    assert root.xpath("string(front/journal-meta/publisher/publisher-name)") == "Example Publisher"
    assert root.xpath("count(front/article-meta/history/date)") == 5.0
    assert set(root.xpath("front/article-meta/history/date/@date-type")) == {
        "received",
        "rev-request",
        "rev-recd",
        "accepted",
        "pub",
    }
    assert root.xpath("string(front/article-meta/volume)") == "31"
    assert root.xpath("string(front/article-meta/issue)") == "1"
    assert root.xpath("string(front/article-meta/elocation-id)") == "e20260001"
    assert root.xpath("count(front/article-meta/permissions/license/license-p)") == 1.0
    assert (
        root.xpath(
            "string(front/article-meta/permissions/license/@xlink:href)",
            namespaces={"xlink": XLINK_NS},
        )
        == "https://creativecommons.org/licenses/by/4.0/"
    )
    assert (
        root.xpath("string(front/article-meta/aff/institution[@content-type='orgname'])")
        == "Example University"
    )
    assert root.xpath(
        "string(front/article-meta/contrib-group/contrib/role[1]/@content-type)"
    ).startswith("https://credit.niso.org/contributor-roles/")
    assert root.xpath("string(back/sec[@sec-type='data-availability']/@specific-use)") == (
        "data-available"
    )
    assert root.xpath("count(front/article-meta/funding-group/award-group)") == 1.0
    assert root.xpath("count(back/ack)") == 1.0
    assert root.xpath("count(back/sec)") == 2.0
    assert root.xpath("count(front/article-meta/author-notes/fn[@fn-type='coi-statement'])") == 1.0
    assert root.xpath("count(back/ref-list/ref/element-citation/pub-id)") == 1.0
    assert root.xpath("starts-with(string(body//disp-formula/@id), 'e-')")


def test_builder_preserves_table_spans_and_infers_every_xref_type() -> None:
    xml = JatsBuilder().build(complete_article())
    root = etree.fromstring(xml)

    assert root.xpath("string(body//table-wrap/table/tbody/tr[1]/td/@colspan)") == "2"
    assert root.xpath("count(body//table-wrap/table/tbody/tr[1]/td)") == 1.0
    assert set(root.xpath("body//xref/@ref-type")) >= {
        "fig",
        "table",
        "disp-formula",
        "fn",
        "bibr",
    }


def test_builder_marks_reference_urls_with_accessible_external_links() -> None:
    article = complete_article()
    reference = article.back.references[0]
    citation = reference.mixed_citation.model_copy(
        update={
            "plain": reference.mixed_citation.plain.model_copy(
                update={
                    "value": (
                        "Silva A. Water treatment. Example Journal. 2025. "
                        "https://doi.org/10.1234/example.1"
                    )
                }
            )
        }
    )
    article = article.model_copy(
        update={
            "back": article.back.model_copy(
                update={"references": (reference.model_copy(update={"mixed_citation": citation}),)}
            )
        }
    )

    root = etree.fromstring(JatsBuilder().build(article))

    assert root.xpath("count(back/ref-list/ref/element-citation/ext-link)") == 1.0
    assert (
        root.xpath(
            "string(back/ref-list/ref/element-citation/ext-link/@xlink:title)",
            namespaces={"xlink": XLINK_NS},
        )
        == "External reference"
    )


@pytest.mark.parametrize(
    ("mutation", "code"),
    (
        (lambda xml: xml.replace(b" encoding='UTF-8'", b"", 1), "invalid-xml-declaration"),
        (lambda xml: xml.replace(b"sps-1.10", b"sps-9.99", 1), "unsupported-sps-version"),
        (lambda xml: xml.replace(b"1234-5678", b"invalid"), "invalid-issn"),
        (
            lambda xml: xml.replace(b"https://example.org", b"javascript:alert(1)", 1),
            "unsafe-external-link",
        ),
        (
            lambda xml: xml.replace(b"article-gf01.jpg", b"../escape.jpg", 1),
            "unsafe-asset-reference",
        ),
        (lambda xml: xml.replace(b'rid="figure-1"', b'rid="missing"', 1), "orphan-rid"),
        (
            lambda xml: xml.replace(b"Synthetic title", "Synthetic\u200b title".encode(), 1),
            "forbidden-invisible-character",
        ),
    ),
)
def test_validator_rejects_invalid_xml_contracts(mutation: object, code: str) -> None:
    article = complete_article()
    xml = JatsBuilder().build(article)
    if code == "unsafe-external-link":
        xml = xml.replace(
            b"</p>",
            (
                b'<ext-link xmlns:xlink="http://www.w3.org/1999/xlink" '
                b'ext-link-type="uri" xlink:href="https://example.org">link</ext-link></p>'
            ),
            1,
        )
    report = OfflineJatsValidator(VENDOR).validate(
        mutation(xml),  # type: ignore[operator]
        asset_names={asset.logical_name for asset in article.assets},
    )

    assert not report.valid
    assert any(
        issue.code == code and issue.severity == ValidationSeverity.ERROR for issue in report.issues
    )


def test_builder_rejects_an_unimplemented_sps_contract() -> None:
    with pytest.raises(ValueError, match=r"only SPS 1\.10"):
        JatsBuilder(sps_version="sps-2.0")


def test_validator_checks_inline_assets_too() -> None:
    article = complete_article()
    xml = (
        JatsBuilder()
        .build(article)
        .replace(
            b"</p>",
            (f'<inline-graphic xmlns:xlink="{XLINK_NS}" xlink:href="unknown.png"/></p>'.encode()),
            1,
        )
    )
    report = OfflineJatsValidator(VENDOR).validate(
        xml,
        asset_names={asset.logical_name for asset in article.assets},
    )

    assert any(issue.code == "unknown-asset-reference" for issue in report.issues)


def test_table_span_contract_rejects_overlap_and_out_of_bounds() -> None:
    rows = ((rich("a", "A"), rich("b", "B")), (rich("c", "C"), rich("d", "D")))
    with pytest.raises(ValueError, match="overlap"):
        TableBlock(
            id="table-overlap",
            label=sourced("Table"),
            caption=rich("caption-overlap", "Caption"),
            rows=rows,
            cell_spans=(
                TableCellSpan(row=0, column=0, column_span=2),
                TableCellSpan(row=0, column=1, row_span=2),
            ),
        )
    with pytest.raises(ValueError, match="exceeds"):
        TableBlock(
            id="table-bounds",
            label=sourced("Table"),
            caption=rich("caption-bounds", "Caption"),
            rows=rows,
            cell_spans=(TableCellSpan(row=1, column=0, row_span=2),),
        )
    with pytest.raises(ValueError, match="covered"):
        TableBlock(
            id="table-covered-content",
            label=sourced("Table"),
            caption=rich("caption-covered", "Caption"),
            rows=rows,
            cell_spans=(TableCellSpan(row=0, column=0, column_span=2),),
        )


def test_non_present_back_fields_do_not_create_an_empty_back() -> None:
    base = canonical_article()
    missing = SourcedText(state=FieldState.MISSING)
    article = base.model_copy(
        update={
            "back": BackMatter(
                contribution_statement=missing,
                data_availability=missing,
                conflicts=missing,
            )
        }
    )

    assert etree.fromstring(JatsBuilder().build(article)).find("back") is None
