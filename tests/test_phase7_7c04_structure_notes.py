from __future__ import annotations

from collections.abc import Callable
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from lxml import etree

from idml_foundation.pipeline.service import DeterministicPipeline
from tests.phase3_helpers import synthetic_idml


def _mutate(source: bytes, transforms: dict[str, Callable[[bytes], bytes]]) -> bytes:
    output = BytesIO()
    with ZipFile(BytesIO(source)) as original, ZipFile(output, "w", ZIP_DEFLATED) as updated:
        for name in original.namelist():
            data = original.read(name)
            if transform := transforms.get(name):
                data = transform(data)
            updated.writestr(name, data)
    return output.getvalue()


def test_profile_reconstructs_third_level_sections_and_standard_section_type() -> None:
    source = synthetic_idml(include_subsection=True)
    level_three = (
        b'<ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/04.2.detail">'
        b'<CharacterStyleRange AppliedCharacterStyle="CharacterStyle/none">'
        b"<Content>Deep method detail</Content></CharacterStyleRange>"
        b"</ParagraphStyleRange>"
        b'<ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/05.0.text">'
        b'<CharacterStyleRange AppliedCharacterStyle="CharacterStyle/none">'
        b"<Content>Deep content</Content></CharacterStyleRange></ParagraphStyleRange>"
    )
    source = _mutate(
        source,
        {
            "Resources/Styles.xml": lambda data: data.replace(
                b"</RootParagraphStyleGroup>",
                b'<ParagraphStyle Self="ParagraphStyle/04.2.detail" Name="04.2.detail"/>'
                b"</RootParagraphStyleGroup>",
            ),
            "Stories/Story_u2.xml": lambda data: data.replace(
                b"</Story>", level_three + b"</Story>"
            ),
        },
    )

    result = DeterministicPipeline().run(source, logical_name="ESA_2024001_AOP.idml")
    root = etree.fromstring(result.xml)
    top = result.canonical.body[0]

    assert top.title.value == "INTRODUCTION"
    assert top.section_type == "intro"
    assert top.children[0].children[0].level == 3
    assert top.children[0].children[0].title.value == "Deep method detail"
    assert root.xpath("count(body/sec[@sec-type='intro']/sec/sec)") == 1.0


def test_table_footnote_keeps_one_fn_and_splits_source_lines_into_paragraphs() -> None:
    source = synthetic_idml(include_table=True, include_styled_table=True)
    footnote = (
        b'<ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/07.3.table-note">'
        b'<CharacterStyleRange AppliedCharacterStyle="CharacterStyle/none">'
        b"<Content>First note line\nSecond note line</Content>"
        b"</CharacterStyleRange></ParagraphStyleRange>"
    )
    source = _mutate(
        source,
        {
            "Resources/Styles.xml": lambda data: data.replace(
                b"</RootParagraphStyleGroup>",
                b'<ParagraphStyle Self="ParagraphStyle/07.3.table-note" '
                b'Name="07.3.table-note"/></RootParagraphStyleGroup>',
            ),
            "Stories/Story_u4.xml": lambda data: data.replace(b"</Story>", footnote + b"</Story>"),
        },
    )

    result = DeterministicPipeline().run(source, logical_name="ESA_2024001_AOP.idml")
    root = etree.fromstring(result.xml)
    table = next(
        block
        for section in result.canonical.body
        for block in section.blocks
        if block.kind == "table"
    )

    assert len(table.footnotes) == 1
    assert root.xpath("count(body//table-wrap-foot/fn)") == 1.0
    assert root.xpath("count(body//table-wrap-foot/fn/p)") == 2.0
    assert root.xpath("body//table-wrap-foot/fn/p/text()") == [
        "First note line",
        "Second note line",
    ]


def test_page_item_hyperlink_supplies_editor_orcid_from_authenticated_idml() -> None:
    source = synthetic_idml(include_correspondence=True)
    destination = b"https://orcid.org/0000-0002-1825-0097"

    def design(data: bytes) -> bytes:
        return data.replace(
            b"/>",
            b">"
            b'<HyperlinkURLDestination Self="editor-destination" DestinationUniqueKey="91" '
            b'DestinationURL="https://orcid.org/0000-0002-1825-0097"/>'
            b'<HyperlinkPageItemSource Self="editor-source" SourcePageItem="editor-icon"/>'
            b'<Hyperlink Self="editor-link" Source="editor-source" DestinationUniqueKey="91"/>'
            b"</Document>",
            1,
        )

    def story(data: bytes) -> bytes:
        data = data.replace(
            b"Associate editor: Bruno Costa\nScientific editor: Carla Souza",
            b"Editor: Bruno Costa",
        )
        return data.replace(
            b"Editor: Bruno Costa</Content>",
            b'Editor: Bruno Costa</Content><Rectangle Self="editor-icon"/>',
        )

    source = _mutate(
        source,
        {
            "designmap.xml": design,
            "Stories/Story_u1.xml": story,
        },
    )

    result = DeterministicPipeline().run(source, logical_name="ESA_2024001_AOP.idml")
    root = etree.fromstring(result.xml)
    editor = next(note for note in result.canonical.back.notes if note.note_type == "edited-by")

    assert destination.decode() in (editor.content.plain.value or "")
    assert root.xpath(
        "string(front/article-meta/author-notes/fn[@fn-type='edited-by']/p)"
    ).endswith(destination.decode())
    assert not any(
        "editor_orcid_requires_enrichment" in reason for reason in result.canonical.review_reasons
    )


def test_paragraph_scoped_orcid_is_not_assigned_to_multiple_editors() -> None:
    source = synthetic_idml(include_correspondence=True)

    def design(data: bytes) -> bytes:
        return data.replace(
            b"/>",
            b">"
            b'<HyperlinkURLDestination Self="editor-destination" DestinationUniqueKey="91" '
            b'DestinationURL="https://orcid.org/0000-0002-1825-0097"/>'
            b'<HyperlinkPageItemSource Self="editor-source" SourcePageItem="editor-icon"/>'
            b'<Hyperlink Self="editor-link" Source="editor-source" DestinationUniqueKey="91"/>'
            b"</Document>",
            1,
        )

    def story(data: bytes) -> bytes:
        return data.replace(
            b"Scientific editor: Carla Souza</Content>",
            b'Scientific editor: Carla Souza</Content><Rectangle Self="editor-icon"/>',
        )

    source = _mutate(
        source,
        {
            "designmap.xml": design,
            "Stories/Story_u1.xml": story,
        },
    )

    result = DeterministicPipeline().run(source, logical_name="ESA_2024001_AOP.idml")
    editorial_notes = tuple(
        note
        for note in result.canonical.back.notes
        if note.note_type in {"associate-editor", "scientific-editor"}
    )

    assert len(editorial_notes) == 2
    assert all("orcid.org" not in (note.content.plain.value or "") for note in editorial_notes)
    assert "ambiguous_editor_orcid_hyperlinks" in result.canonical.review_reasons
    assert "associate_editor_orcid_requires_enrichment" in result.canonical.review_reasons
    assert "scientific_editor_orcid_requires_enrichment" in result.canonical.review_reasons


def test_profile_converts_numbered_paragraphs_to_lists_without_duplicate_markers() -> None:
    source = synthetic_idml(include_subsection=True)
    numbered_items = (
        b'<ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/05.1.steps">'
        b'<CharacterStyleRange AppliedCharacterStyle="CharacterStyle/none">'
        b"<Content>1. First step</Content></CharacterStyleRange>"
        b"</ParagraphStyleRange>"
        b'<ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/05.1.steps">'
        b'<CharacterStyleRange AppliedCharacterStyle="CharacterStyle/none">'
        b"<Content>2. Second step</Content></CharacterStyleRange>"
        b"</ParagraphStyleRange>"
    )
    source = _mutate(
        source,
        {
            "Resources/Styles.xml": lambda data: data.replace(
                b"</RootParagraphStyleGroup>",
                b'<ParagraphStyle Self="ParagraphStyle/05.1.steps" Name="05.1.steps"/>'
                b"</RootParagraphStyleGroup>",
            ),
            "Stories/Story_u2.xml": lambda data: data.replace(
                b"</Story>", numbered_items + b"</Story>"
            ),
        },
    )

    result = DeterministicPipeline().run(source, logical_name="ESA_2024001_AOP.idml")
    root = etree.fromstring(result.xml)

    assert root.xpath("body//list[@list-type='order']/list-item/p/text()") == [
        "First step",
        "Second step",
    ]


def test_profile_splits_multiple_numbered_lines_in_one_paragraph() -> None:
    source = synthetic_idml(include_subsection=True)
    numbered_items = (
        b'<ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/05.1.steps">'
        b'<CharacterStyleRange AppliedCharacterStyle="CharacterStyle/none">'
        b"<Content>1. First step\n2. Second step</Content></CharacterStyleRange>"
        b"</ParagraphStyleRange>"
    )
    source = _mutate(
        source,
        {
            "Resources/Styles.xml": lambda data: data.replace(
                b"</RootParagraphStyleGroup>",
                b'<ParagraphStyle Self="ParagraphStyle/05.1.steps" Name="05.1.steps"/>'
                b"</RootParagraphStyleGroup>",
            ),
            "Stories/Story_u2.xml": lambda data: data.replace(
                b"</Story>", numbered_items + b"</Story>"
            ),
        },
    )

    result = DeterministicPipeline().run(source, logical_name="ESA_2024001_AOP.idml")
    root = etree.fromstring(result.xml)

    assert root.xpath("body//list[@list-type='order']/list-item/p/text()") == [
        "First step\n",
        "Second step",
    ]


def test_numbered_list_item_preserves_anchored_inline_formula() -> None:
    source = synthetic_idml(include_inline_formula=True)

    def story(data: bytes) -> bytes:
        return data.replace(
            b'AppliedParagraphStyle="ParagraphStyle/05.0.text">'
            b'<CharacterStyleRange AppliedCharacterStyle="CharacterStyle/none">'
            b"<Content>Rate ",
            b'AppliedParagraphStyle="ParagraphStyle/05.1.steps">'
            b'<CharacterStyleRange AppliedCharacterStyle="CharacterStyle/none">'
            b"<Content>1. Rate ",
            1,
        )

    source = _mutate(
        source,
        {
            "Resources/Styles.xml": lambda data: data.replace(
                b"</RootParagraphStyleGroup>",
                b'<ParagraphStyle Self="ParagraphStyle/05.1.steps" Name="05.1.steps"/>'
                b"</RootParagraphStyleGroup>",
            ),
            "Stories/Story_u2.xml": story,
        },
    )

    result = DeterministicPipeline().run(source, logical_name="ESA_2024001_AOP.idml")
    root = etree.fromstring(result.xml)

    assert root.xpath("count(body//p/inline-formula)") == 1.0
    assert root.xpath("normalize-space(string(body//p[inline-formula]))").startswith("Rate")
    assert "1." not in root.xpath("string(body//list/list-item/p)")
