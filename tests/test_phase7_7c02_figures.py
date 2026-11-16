from __future__ import annotations

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from lxml import etree

from idml_foundation.asset_identity import figure_asset_number
from idml_foundation.domain.raw import RawObjectKind
from idml_foundation.pipeline.service import DeterministicPipeline
from idml_foundation.release.package_builder import AssetPayload, PackageBuilder
from tests.phase3_helpers import synthetic_idml


def test_figure_asset_identity_is_conservative_and_format_independent() -> None:
    assert figure_asset_number("Article%20Fig01.pdf") is None
    assert figure_asset_number("Article Fig01.pdf") == 1
    assert figure_asset_number("ARTICLE_FIGURE003.EPS") == 3
    assert figure_asset_number("journal-article-gf07.jpg") == 7
    assert figure_asset_number("configuration01.pdf") is None
    assert figure_asset_number("Article_Eq01.pdf") is None


def _pdf_figure_idml() -> bytes:
    source = synthetic_idml()
    output = BytesIO()
    with ZipFile(BytesIO(source)) as original, ZipFile(output, "w", ZIP_DEFLATED) as updated:
        for name in original.namelist():
            data = original.read(name)
            if name == "Stories/Story_u2.xml":
                mention = (
                    b'<ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/05.0.text">'
                    b'<CharacterStyleRange AppliedCharacterStyle="CharacterStyle/none">'
                    b"<Content>See Figure 3.</Content></CharacterStyleRange>"
                    b"</ParagraphStyleRange>"
                )
                data = data.replace(b"</Story>", mention + b"</Story>")
            elif name == "Stories/Story_u4.xml":
                data = data.replace(
                    b"file:C:/private/source/Figure%201.jpg",
                    b"file:C:/private/source/Article%20Fig01.pdf",
                ).replace(b"$ID/JPEG", b"$ID/Adobe Portable Document Format (PDF)")
                additional = (
                    b'<ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/07.0.caption">'
                    b'<CharacterStyleRange AppliedCharacterStyle="CharacterStyle/none">'
                    b"<Content>Figure 3. Third caption</Content></CharacterStyleRange>"
                    b"</ParagraphStyleRange>"
                    b'<ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/07.0.caption">'
                    b'<CharacterStyleRange AppliedCharacterStyle="CharacterStyle/none">'
                    b"<Content>Figure 2. Second caption</Content></CharacterStyleRange>"
                    b"</ParagraphStyleRange>"
                    b'<Rectangle Self="rectangle-2"><PDF><Link Self="link-2" '
                    b'LinkResourceURI="file:C:/private/source/Article_Fig02.pdf" '
                    b'LinkResourceFormat="$ID/Adobe Portable Document Format (PDF)"/>'
                    b"</PDF></Rectangle>"
                    b'<Rectangle Self="rectangle-3"><PDF><Link Self="link-3" '
                    b'LinkResourceURI="file:C:/private/source/Article-Figure003.pdf" '
                    b'LinkResourceFormat="$ID/Adobe Portable Document Format (PDF)"/>'
                    b"</PDF></Rectangle>"
                )
                data = data.replace(b"</Story>", additional + b"</Story>")
            updated.writestr(name, data)
    return output.getvalue()


def test_pdf_figures_are_classified_linked_and_ordered_without_artificial_section() -> None:
    result = DeterministicPipeline().run(
        _pdf_figure_idml(),
        logical_name="ESA_2024995_AOP.idml",
    )
    root = etree.fromstring(result.xml)
    figure_assets = {
        asset_id
        for anchored in result.raw.anchored_objects
        if anchored.kind == RawObjectKind.FIGURE
        for asset_id in anchored.asset_ids
    }

    assert len(figure_assets) == 3
    assert root.xpath("//body//fig/label/text()") == ["Figure 1", "Figure 2", "Figure 3"]
    assert root.xpath("count(//body//fig/graphic)") == 3.0
    assert root.xpath(
        "//body//fig/graphic/@xlink:href", namespaces={"xlink": "http://www.w3.org/1999/xlink"}
    ) == [
        "Article Fig01.pdf",
        "Article_Fig02.pdf",
        "Article-Figure003.pdf",
    ]
    assert not root.xpath("//body//sec[title='Elementos gráficos']")
    assert not any(
        reason.startswith("unmatched_figure_asset:") for reason in result.canonical.review_reasons
    )


def test_package_builder_resolves_figure_ordinal_and_uses_payload_extension() -> None:
    xml = b"""<?xml version="1.0"?><article xmlns:xlink="http://www.w3.org/1999/xlink">
    <body><fig><graphic xlink:href="Article_Fig01.pdf"/></fig></body></article>"""
    files = PackageBuilder().scielo_files(
        package_stem="article",
        xml=xml,
        pdf=b"pdf",
        assets=(AssetPayload(source_name="journal-article-gf01.jpg", data=b"jpeg"),),
    )

    assert files[2].name == "article-gf01.jpg"
    assert b"article-gf01.jpg" in files[0].data


def test_package_builder_rejects_ambiguous_figure_ordinals() -> None:
    xml = b"""<?xml version="1.0"?><article xmlns:xlink="http://www.w3.org/1999/xlink">
    <body><fig><graphic xlink:href="Article_Fig01.pdf"/></fig></body></article>"""
    with pytest.raises(ValueError, match="ambiguous package figure asset"):
        PackageBuilder().scielo_files(
            package_stem="article",
            xml=xml,
            pdf=b"pdf",
            assets=(
                AssetPayload(source_name="article-gf01.jpg", data=b"jpeg"),
                AssetPayload(source_name="copy-figure01.png", data=b"png"),
            ),
        )
