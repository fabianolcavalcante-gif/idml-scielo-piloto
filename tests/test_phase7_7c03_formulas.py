from __future__ import annotations

from collections.abc import Callable
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from lxml import etree

from idml_foundation.asset_identity import equation_asset_placement, inline_equation_asset_number
from idml_foundation.domain.canonical import FormulaRepresentation, InlineKind
from idml_foundation.domain.raw import AnchoredPlacement
from idml_foundation.pipeline.service import DeterministicPipeline
from tests.phase3_helpers import synthetic_idml


def _mutate_story(source: bytes, story_name: str, transform: Callable[[bytes], bytes]) -> bytes:
    output = BytesIO()
    with ZipFile(BytesIO(source)) as original, ZipFile(output, "w", ZIP_DEFLATED) as updated:
        for name in original.namelist():
            data = original.read(name)
            if name == story_name:
                data = transform(data)
            updated.writestr(name, data)
    return output.getvalue()


def _add_story(source: bytes, story_name: str, data: bytes) -> bytes:
    output = BytesIO()
    with ZipFile(BytesIO(source)) as original, ZipFile(output, "w", ZIP_DEFLATED) as updated:
        for name in original.namelist():
            updated.writestr(name, original.read(name))
        updated.writestr(story_name, data)
    return output.getvalue()


def test_equation_asset_placement_is_explicit_and_conservative() -> None:
    assert equation_asset_placement("Article_Eq-txt-01.pdf") == "inline"
    assert equation_asset_placement("ARTICLE-EQ-TXT-007.PDF") == "inline"
    assert equation_asset_placement("Article_Eq03.pdf") == "block"
    assert equation_asset_placement("Equations-inline.pdf") is None
    assert equation_asset_placement("A.pdf") is None
    assert equation_asset_placement("Article_Fig03.pdf") is None
    assert inline_equation_asset_number("Article_Eq-txt-007.pdf") == 7
    assert inline_equation_asset_number("Article_Eq07.pdf") is None


def test_eq_txt_asset_overrides_line_break_heuristic_as_inline() -> None:
    source = synthetic_idml(include_formula=True)
    source = _mutate_story(
        source,
        "Stories/Story_u2.xml",
        lambda data: data.replace(b"Equations.pdf", b"Article_Eq-txt-01.pdf"),
    )
    result = DeterministicPipeline().run(source, logical_name="ESA_2024994_AOP.idml")
    anchored = next(
        item
        for item in result.raw.anchored_objects
        if item.anchor_run_id is not None and item.asset_ids
    )
    inline_formulas = [
        inline
        for section in result.canonical.body
        for block in section.blocks
        if block.kind == "paragraph"
        for inline in block.content.inlines
        if inline.kind == InlineKind.INLINE_FORMULA
    ]

    assert anchored.placement == AnchoredPlacement.INLINE
    assert len(inline_formulas) == 1
    assert not any(block.kind == "formula" for block in result.canonical.body[0].blocks)


def test_native_labeled_formula_is_split_from_surrounding_prose() -> None:
    native = (
        b'<ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/05.0.text">'
        b'<CharacterStyleRange AppliedCharacterStyle="CharacterStyle/none">'
        b"<Content>Before.\n</Content>"
        b"<Content>N_k = L - k + 1(1)\n</Content>"
        b"<Content>After.</Content>"
        b"</CharacterStyleRange></ParagraphStyleRange>"
    )
    source = _mutate_story(
        synthetic_idml(),
        "Stories/Story_u2.xml",
        lambda data: data.replace(b"</Story>", native + b"</Story>"),
    )
    result = DeterministicPipeline().run(source, logical_name="ESA_2024993_AOP.idml")
    root = etree.fromstring(result.xml)
    blocks = result.canonical.body[0].blocks
    formula = next(block for block in blocks if block.kind == "formula")
    formula_position = blocks.index(formula)

    assert formula.representation == FormulaRepresentation.TEXT
    assert formula.source.value == "N_k = L - k + 1"
    assert formula.label is not None and formula.label.value == "(1)"
    assert blocks[formula_position - 1].content.plain.value == "Before.\n"
    assert blocks[formula_position + 1].content.plain.value == "\nAfter."
    assert root.xpath("string(body//disp-formula/label)") == "(1)"
    assert root.xpath("string(body//disp-formula/tex-math)") == "N_k = L - k + 1"
    assert any(
        reason.startswith("native_formula_requires_mathml_transcription:")
        for reason in result.canonical.review_reasons
    )


def test_embedded_story_with_subscript_is_an_inline_formula_not_body_duplication() -> None:
    anchor = (
        b'<ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/05.0.text">'
        b'<CharacterStyleRange AppliedCharacterStyle="CharacterStyle/none">'
        b'<Content>Centroid </Content><TextFrame Self="embedded-frame" '
        b'ParentStory="embedded-formula"/><Content> is used.</Content>'
        b"</CharacterStyleRange></ParagraphStyleRange>"
    )
    source = _mutate_story(
        synthetic_idml(),
        "Stories/Story_u2.xml",
        lambda data: data.replace(b"</Story>", anchor + b"</Story>"),
    )
    source = _add_story(
        source,
        "Stories/Story_embedded-formula.xml",
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<idPkg:Story xmlns:idPkg="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging">'
        b'<Story Self="embedded-formula">'
        b'<ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/05.0.text">'
        b'<CharacterStyleRange AppliedCharacterStyle="CharacterStyle/italico">'
        b"<Content>x</Content></CharacterStyleRange>"
        b'<CharacterStyleRange AppliedCharacterStyle="CharacterStyle/none" Position="Subscript">'
        b"<Content>A</Content></CharacterStyleRange>"
        b"</ParagraphStyleRange></Story></idPkg:Story>",
    )
    result = DeterministicPipeline().run(source, logical_name="ESA_2024992_AOP.idml")
    root = etree.fromstring(result.xml)

    assert root.xpath("count(body//inline-formula)") == 1.0
    assert root.xpath("string(body//inline-formula/tex-math)") == "xA"
    assert root.xpath("string(body)").count("xA") == 1
    assert not root.xpath("body//p[normalize-space(.)='xA']")


def test_three_glyph_assets_in_one_pseudocode_expression_are_grouped() -> None:
    def linked_glyph(link_id: str, name: str) -> bytes:
        return (
            f'<Rectangle Self="{link_id}-rectangle"><PDF><Link Self="{link_id}" '
            f'LinkResourceURI="file:C:/private/source/{name}.pdf" '
            'LinkResourceFormat="$ID/Adobe Portable Document Format (PDF)"/>'
            "</PDF></Rectangle>"
        ).encode()

    paragraph = (
        b'<ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/05.0.text">'
        b'<CharacterStyleRange AppliedCharacterStyle="CharacterStyle/none">'
        b"<Content>4: </Content>"
        + linked_glyph("glyph-x-1", "X")
        + b"<Content> \xe2\x86\x90 </Content>"
        + linked_glyph("glyph-x-2", "X")
        + b"<Content> </Content>"
        + linked_glyph("glyph-union", "U")
        + b"<Content> {x_i}</Content></CharacterStyleRange></ParagraphStyleRange>"
    )
    source = _mutate_story(
        synthetic_idml(),
        "Stories/Story_u2.xml",
        lambda data: data.replace(b"</Story>", paragraph + b"</Story>"),
    )
    result = DeterministicPipeline().run(source, logical_name="ESA_2024991_AOP.idml")
    root = etree.fromstring(result.xml)

    assert root.xpath("count(body//inline-formula)") == 1.0
    assert root.xpath("string(body//inline-formula/tex-math)") == "X \u2190 X U {x_i}"
    assert root.xpath("string(body//inline-formula/parent::p/text()[1])") == "4: "


def test_native_double_assignment_line_is_marked_as_one_inline_formula() -> None:
    paragraph = (
        b'<ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/05.0.text">'
        b'<CharacterStyleRange AppliedCharacterStyle="CharacterStyle/none">'
        b"<Content>Z = XVm, Vm = [v1, v2]\nFollowing prose.</Content>"
        b"</CharacterStyleRange></ParagraphStyleRange>"
    )
    source = _mutate_story(
        synthetic_idml(),
        "Stories/Story_u2.xml",
        lambda data: data.replace(b"</Story>", paragraph + b"</Story>"),
    )
    result = DeterministicPipeline().run(source, logical_name="ESA_2024990_AOP.idml")
    root = etree.fromstring(result.xml)

    assert root.xpath("count(body//inline-formula)") == 1.0
    assert root.xpath("string(body//inline-formula/tex-math)") == "Z = XVm, Vm = [v1, v2]"
    assert any(
        reason.startswith("inline_formula_requires_mathml_transcription:")
        for reason in result.canonical.review_reasons
    )


def test_non_monotonic_duplicate_eq_txt_asset_is_suppressed() -> None:
    def linked_formula(link_id: str, number: int) -> bytes:
        return (
            f'<Rectangle Self="{link_id}-rectangle"><PDF><Link Self="{link_id}" '
            f'LinkResourceURI="file:C:/private/source/Article_Eq-txt-{number:02}.pdf" '
            'LinkResourceFormat="$ID/Adobe Portable Document Format (PDF)"/>'
            "</PDF></Rectangle>"
        ).encode()

    paragraph = (
        b'<ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/05.0.text">'
        b'<CharacterStyleRange AppliedCharacterStyle="CharacterStyle/none">'
        b"<Content>Equations </Content>"
        + linked_formula("formula-7-first", 7)
        + b"<Content>, </Content>"
        + linked_formula("formula-8", 8)
        + b"<Content>, duplicate </Content>"
        + linked_formula("formula-7-duplicate", 7)
        + b"<Content>.</Content></CharacterStyleRange></ParagraphStyleRange>"
    )
    source = _mutate_story(
        synthetic_idml(),
        "Stories/Story_u2.xml",
        lambda data: data.replace(b"</Story>", paragraph + b"</Story>"),
    )
    result = DeterministicPipeline().run(source, logical_name="ESA_2024989_AOP.idml")
    root = etree.fromstring(result.xml)

    assert root.xpath("count(body//inline-formula)") == 2.0
