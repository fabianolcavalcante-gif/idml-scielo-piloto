from io import BytesIO
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

from lxml import etree

from idml_foundation.domain.canonical import InlineKind, Paragraph
from idml_foundation.pipeline.idml_parser import IdmlParser
from idml_foundation.pipeline.service import DeterministicPipeline


def fidelity_idml() -> bytes:
    design = b"""<Document Self="doc" DOMVersion="20.3"
      StoryList="u-main u-left u-right u-later">
      <HyperlinkURLDestination Self="destination" DestinationUniqueKey="key-1"
        DestinationURL="https://example.org/article" Hidden="false"/>
      <HyperlinkURLDestination Self="unsafe-destination" DestinationUniqueKey="key-unsafe"
        DestinationURL="javascript:alert(1)" Hidden="false"/>
      <Hyperlink Self="hyperlink" Source="source-1" DestinationUniqueKey="key-1"/>
      <Hyperlink Self="unsafe-hyperlink" Source="source-unsafe"
        DestinationUniqueKey="key-unsafe"/>
      <idPkg:Spread xmlns:idPkg="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging"
        src="Spreads/Spread_z_first.xml"/>
      <idPkg:Spread xmlns:idPkg="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging"
        src="Spreads/Spread_a_second.xml"/>
    </Document>"""
    styles = b"""<idPkg:Styles
      xmlns:idPkg="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging">
      <RootParagraphStyleGroup>
        <ParagraphStyle Self="ParagraphStyle/01.0.title" Name="01.0.title"/>
        <ParagraphStyle Self="ParagraphStyle/04.0.section" Name="04.0.section"/>
        <ParagraphStyle Self="ParagraphStyle/05.0.text" Name="05.0.text"/>
      </RootParagraphStyleGroup>
      <RootCharacterStyleGroup>
        <CharacterStyle Self="CharacterStyle/none" Name="none"/>
        <CharacterStyle Self="CharacterStyle/italico" Name="italico"/>
      </RootCharacterStyleGroup>
    </idPkg:Styles>"""
    main_story = """<idPkg:Story
      xmlns:idPkg="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging">
      <Story Self="u-main">
        <ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/01.0.title">
          <CharacterStyleRange AppliedCharacterStyle="CharacterStyle/none">
            <Content>Fidelity test</Content>
          </CharacterStyleRange>
        </ParagraphStyleRange>
        <ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/04.0.section">
          <CharacterStyleRange AppliedCharacterStyle="CharacterStyle/none">
            <Content>Section</Content>
          </CharacterStyleRange>
        </ParagraphStyleRange>
        <ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/05.0.text">
          <CharacterStyleRange AppliedCharacterStyle="CharacterStyle/none">
            <Content>Alpha\u00a0soft\u00adhyphen	</Content><Br/><Content>line </Content>
            <Footnote><ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/05.0.text">
              <CharacterStyleRange AppliedCharacterStyle="CharacterStyle/none">
                <Content><?ACE 4?>	Footnote\u00a0text</Content>
              </CharacterStyleRange>
            </ParagraphStyleRange></Footnote>
          </CharacterStyleRange>
          <CharacterStyleRange AppliedCharacterStyle="CharacterStyle/none" FontStyle="Bold">
            <Content>bold </Content>
          </CharacterStyleRange>
          <CharacterStyleRange AppliedCharacterStyle="CharacterStyle/italico">
            <Content>italic </Content>
          </CharacterStyleRange>
          <CharacterStyleRange AppliedCharacterStyle="CharacterStyle/none"
            FontStyle="Bold Italic"><Content>combined </Content></CharacterStyleRange>
          <CharacterStyleRange AppliedCharacterStyle="CharacterStyle/none"
            Position="Superscript"><Content>sup </Content></CharacterStyleRange>
          <CharacterStyleRange AppliedCharacterStyle="CharacterStyle/none"
            Position="Subscript"><Content>sub </Content></CharacterStyleRange>
          <CharacterStyleRange AppliedCharacterStyle="CharacterStyle/none">
            <HyperlinkTextSource Self="source-1"><Content>linked</Content></HyperlinkTextSource>
          </CharacterStyleRange>
          <CharacterStyleRange AppliedCharacterStyle="CharacterStyle/unknown">
            <Content>unknown </Content>
          </CharacterStyleRange>
          <CharacterStyleRange><Content>missing </Content></CharacterStyleRange>
          <HyperlinkTextSource Self="source-unsafe" AppliedCharacterStyle="CharacterStyle/none">
            <CharacterStyleRange AppliedCharacterStyle="CharacterStyle/none">
              <Content>unsafe</Content>
            </CharacterStyleRange>
          </HyperlinkTextSource>
        </ParagraphStyleRange>
        <ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/05.0.text">
          <CharacterStyleRange AppliedCharacterStyle="CharacterStyle/none">
            <Content/>
          </CharacterStyleRange>
        </ParagraphStyleRange>
        <ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/05.0.text"
          BulletsAndNumberingListType="BulletList">
          <CharacterStyleRange AppliedCharacterStyle="CharacterStyle/none">
            <Content>list item</Content>
          </CharacterStyleRange>
        </ParagraphStyleRange>
        <Table Self="table-1" BodyRowCount="2" ColumnCount="2">
          <Cell Name="0:0" ColumnSpan="2"><ParagraphStyleRange
            AppliedParagraphStyle="ParagraphStyle/05.0.text"><CharacterStyleRange
            AppliedCharacterStyle="CharacterStyle/none"><Content>wide</Content>
            </CharacterStyleRange></ParagraphStyleRange></Cell>
          <Cell Name="0:1"><ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/05.0.text">
            <CharacterStyleRange AppliedCharacterStyle="CharacterStyle/none"><Content/>
            </CharacterStyleRange></ParagraphStyleRange></Cell>
          <Cell Name="1:1"><ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/05.0.text">
            <CharacterStyleRange AppliedCharacterStyle="CharacterStyle/none"><Content>cell</Content>
            </CharacterStyleRange></ParagraphStyleRange></Cell>
        </Table>
      </Story>
    </idPkg:Story>""".encode()

    def story(story_id: str, text: str) -> bytes:
        return f"""<idPkg:Story
          xmlns:idPkg="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging">
          <Story Self="{story_id}"><ParagraphStyleRange
            AppliedParagraphStyle="ParagraphStyle/05.0.text"><CharacterStyleRange
            AppliedCharacterStyle="CharacterStyle/none"><Content>{text}</Content>
            </CharacterStyleRange></ParagraphStyleRange></Story>
        </idPkg:Story>""".encode()

    def frame(frame_id: str, story_id: str, x: int) -> str:
        return f"""<TextFrame Self="{frame_id}" ParentStory="{story_id}"
          PreviousTextFrame="n" NextTextFrame="n" ItemTransform="1 0 0 1 {x} 20">
          <Properties><PathGeometry><GeometryPathType><PathPointArray>
            <PathPointType Anchor="0 0"/><PathPointType Anchor="100 100"/>
          </PathPointArray></GeometryPathType></PathGeometry></Properties>
        </TextFrame>"""

    first_spread = f"""<idPkg:Spread
      xmlns:idPkg="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging">
      <Spread Self="spread-first">
        <Page Self="page-1" Name="1" GeometricBounds="0 0 800 600"
          ItemTransform="1 0 0 1 -600 0"/>
        <Page Self="page-2" Name="2" GeometricBounds="0 0 800 600"
          ItemTransform="1 0 0 1 0 0"/>
        {frame("frame-main", "u-main", -550)}
        {frame("frame-left", "u-left", 40)}
        {frame("frame-right", "u-right", 350)}
      </Spread>
    </idPkg:Spread>""".encode()
    second_spread = f"""<idPkg:Spread
      xmlns:idPkg="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging">
      <Spread Self="spread-second">
        <Page Self="page-3" Name="3" GeometricBounds="0 0 800 600"
          ItemTransform="1 0 0 1 0 0"/>
        {frame("frame-later", "u-later", 40)}
      </Spread>
    </idPkg:Spread>""".encode()

    output = BytesIO()
    with ZipFile(output, "w") as archive:

        def write(name: str, value: str | bytes, compression: int) -> None:
            info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = compression
            info.external_attr = 0o600 << 16
            archive.writestr(info, value)

        write("mimetype", "application/vnd.adobe.indesign-idml-package", ZIP_STORED)
        write("designmap.xml", design, ZIP_DEFLATED)
        write("Resources/Styles.xml", styles, ZIP_DEFLATED)
        write("Stories/Story_u-main.xml", main_story, ZIP_DEFLATED)
        write("Stories/Story_u-left.xml", story("u-left", "left"), ZIP_DEFLATED)
        write("Stories/Story_u-right.xml", story("u-right", "right"), ZIP_DEFLATED)
        write("Stories/Story_u-later.xml", story("u-later", "later"), ZIP_DEFLATED)
        write("Spreads/Spread_a_second.xml", second_spread, ZIP_DEFLATED)
        write("Spreads/Spread_z_first.xml", first_spread, ZIP_DEFLATED)
    return output.getvalue()


def test_v03_raw_text_styles_notes_tables_links_and_empty_paragraphs_are_loss_aware() -> None:
    raw = IdmlParser().parse(fidelity_idml(), logical_name="ESA_2024999_AOP.idml")
    main = next(story for story in raw.stories if story.source_self_id == "u-main")
    run_by_text = {run.text.strip(): run for run in main.runs if run.text.strip()}
    styles = {style.id: style for style in raw.styles}

    assert "Alpha\u00a0soft\u00adhyphen	\nline " in "".join(run.text for run in main.runs)
    bold_style_id = run_by_text["bold"].character_style_id
    combined_style_id = run_by_text["combined"].character_style_id
    sup_style_id = run_by_text["sup"].character_style_id
    sub_style_id = run_by_text["sub"].character_style_id
    assert bold_style_id and styles[bold_style_id].properties["FontStyle"] == "Bold"
    assert combined_style_id and styles[combined_style_id].properties["FontStyle"] == (
        "Bold Italic"
    )
    assert sup_style_id and styles[sup_style_id].properties["Position"] == "Superscript"
    assert sub_style_id and styles[sub_style_id].properties["Position"] == "Subscript"
    assert run_by_text["unknown"].character_style_id is not None
    assert run_by_text["missing"].character_style_id is None
    assert any(not paragraph.text_run_ids for paragraph in main.paragraphs)
    list_paragraph = next(
        paragraph
        for paragraph in main.paragraphs
        if any(
            run_by_text.get("list item") and run_by_text["list item"].id == run_id
            for run_id in paragraph.text_run_ids
        )
    )
    assert list_paragraph.paragraph_style_id
    assert (
        styles[list_paragraph.paragraph_style_id].properties["BulletsAndNumberingListType"]
        == "BulletList"
    )

    note = raw.notes[0]
    assert main.note_ids == (note.id,)
    assert "".join(run.text for run in main.runs if run.id in note.text_run_ids) == (
        "\tFootnote\u00a0text"
    )
    assert len(raw.tables) == 1
    assert raw.tables[0].cells[0].column_span == 2
    assert raw.tables[0].cells[1].text_run_ids == ()

    hyperlinks = [link for link in raw.links if link.relationship == "external-hyperlink"]
    hyperlink = next(link for link in hyperlinks if link.target.startswith("https://"))
    assert hyperlink.target == "https://example.org/article"
    assert next(run for run in main.runs if run.id == hyperlink.source_id).text == "linked"
    assert any(link.target == "javascript:alert(1)" for link in hyperlinks)


def test_v03_reading_order_uses_designmap_pages_and_columns() -> None:
    raw = IdmlParser().parse(fidelity_idml(), logical_name="ESA_2024999_AOP.idml")
    source_by_id = {story.id: story.source_self_id for story in raw.stories}

    assert [spread.source_self_id for spread in raw.spreads] == ["spread-first", "spread-second"]
    assert [spread.page_indices for spread in raw.spreads] == [(0, 1), (2,)]
    assert [source_by_id[story_id] for story_id in raw.reading_order] == [
        "u-main",
        "u-left",
        "u-right",
        "u-later",
    ]
    frame_by_story = {
        source_by_id[frame.parent_story_id]: (frame.page_index, frame.column_index)
        for frame in raw.frames
    }
    assert frame_by_story == {
        "u-main": (0, 0),
        "u-left": (1, 0),
        "u-right": (1, 1),
        "u-later": (2, 0),
    }


def test_v03_canonical_and_jats_preserve_inline_roles_hyperlink_and_footnote() -> None:
    result = DeterministicPipeline().run(fidelity_idml(), logical_name="ESA_2024999_AOP.idml")
    paragraph = result.canonical.body[0].blocks[0]
    assert isinstance(paragraph, Paragraph)
    kinds_by_text = {inline.text.strip(): inline for inline in paragraph.content.inlines}
    root = etree.fromstring(result.xml)

    assert kinds_by_text["bold"].kind == InlineKind.STRONG
    assert kinds_by_text["italic"].kind == InlineKind.EMPHASIS
    assert kinds_by_text["combined"].attributes["source-emphasis"] == "bold italic"
    assert kinds_by_text["sup"].kind == InlineKind.SUPERSCRIPT
    assert kinds_by_text["sub"].kind == InlineKind.SUBSCRIPT
    assert kinds_by_text["linked"].kind == InlineKind.EXTERNAL_LINK
    assert kinds_by_text["linked"].href == "https://example.org/article"
    assert kinds_by_text["unsafe"].kind == InlineKind.TEXT
    assert any(
        reason.startswith("unsafe_external_hyperlink:")
        for reason in result.canonical.review_reasons
    )
    assert result.canonical.back.notes[0].content.plain.value == "\tFootnote\u00a0text"
    assert root.xpath("string(back/fn-group/fn/p)") == "\tFootnote\u00a0text"
    assert root.xpath("string(body//ext-link/@href)") == ""
    assert (
        root.xpath(
            "string(body//ext-link/@xlink:href)",
            namespaces={"xlink": "http://www.w3.org/1999/xlink"},
        )
        == "https://example.org/article"
    )
    assert result.validation.valid
    assert root.xpath("string(body//bold/italic)") == "combined "
    assert root.xpath("string(body//p[normalize-space(.)='list item'])") == "list item"
    assert not root.xpath(
        "body//ext-link[starts-with(@xlink:href, 'javascript:')]",
        namespaces={"xlink": "http://www.w3.org/1999/xlink"},
    )
