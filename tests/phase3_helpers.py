from io import BytesIO
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo


def synthetic_idml(
    *,
    include_table: bool = False,
    include_subsection: bool = False,
    include_formula: bool = False,
    include_inline_formula: bool = False,
    include_inline_formula_gap: bool = False,
    include_correspondence: bool = False,
    include_back_matter: bool = False,
    include_graphic_mention: bool = False,
    include_styled_table: bool = False,
) -> bytes:
    design = b"""<?xml version="1.0" encoding="UTF-8"?>
<Document Self="doc" DOMVersion="20.3" StoryList="u1 u2 u3 u4"/>"""
    styles = b"""<?xml version="1.0" encoding="UTF-8"?>
<idPkg:Styles xmlns:idPkg="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging">
  <RootParagraphStyleGroup>
    <ParagraphStyle Self="ParagraphStyle/01.0.title" Name="01.0.title"/>
    <ParagraphStyle Self="ParagraphStyle/02.0.author" Name="02.0.author"/>
    <ParagraphStyle Self="ParagraphStyle/03.5.correspondence" Name="03.5.correspondence"/>
    <ParagraphStyle Self="ParagraphStyle/04.0.section" Name="04.0.section"/>
    <ParagraphStyle Self="ParagraphStyle/04.1.subsection" Name="04.1.subsection"/>
    <ParagraphStyle Self="ParagraphStyle/05.0.text" Name="05.0.text"/>
    <ParagraphStyle Self="ParagraphStyle/06.1.references" Name="06.1.references"/>
    <ParagraphStyle Self="ParagraphStyle/07.0.caption" Name="07.0.caption"/>
  </RootParagraphStyleGroup>
  <RootCharacterStyleGroup>
    <CharacterStyle Self="CharacterStyle/none" Name="none"/>
    <CharacterStyle Self="CharacterStyle/italico" Name="italico"/>
    <CharacterStyle Self="CharacterStyle/subscrito" Name="subscrito"/>
  </RootCharacterStyleGroup>
</idPkg:Styles>"""

    def story(story_id: str, paragraphs: str, extra: str = "") -> bytes:
        return f'''<?xml version="1.0" encoding="UTF-8"?>
<idPkg:Story xmlns:idPkg="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging">
  <Story Self="{story_id}">{paragraphs}{extra}</Story>
</idPkg:Story>'''.encode()

    def paragraph(style: str, text: str, character: str = "none") -> str:
        return (
            f'<ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/{style}">'
            f'<CharacterStyleRange AppliedCharacterStyle="CharacterStyle/{character}">'
            f"<Content>{text}</Content></CharacterStyleRange></ParagraphStyleRange>"
        )

    first_table_cell = (
        '<CharacterStyleRange AppliedCharacterStyle="CharacterStyle/none">'
        "<Content>kgO</Content></CharacterStyleRange>"
        '<CharacterStyleRange AppliedCharacterStyle="CharacterStyle/subscrito">'
        "<Content>2</Content></CharacterStyleRange>"
        '<CharacterStyleRange AppliedCharacterStyle="CharacterStyle/none">'
        "<Content>/h</Content></CharacterStyleRange>"
        if include_styled_table
        else '<CharacterStyleRange AppliedCharacterStyle="CharacterStyle/none">'
        "<Content>Alpha</Content></CharacterStyleRange>"
    )
    table = (
        '<Table Self="table-1" BodyRowCount="1" ColumnCount="2">'
        '<Cell Name="0:0"><ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/05.0.text">'
        f"{first_table_cell}</ParagraphStyleRange></Cell>"
        '<Cell Name="1:0"><ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/05.0.text">'
        '<CharacterStyleRange AppliedCharacterStyle="CharacterStyle/none">'
        "<Content>Beta</Content></CharacterStyleRange></ParagraphStyleRange></Cell>"
        "</Table>"
        if include_table
        else ""
    )
    formula = (
        '<ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/05.0.text">'
        '<CharacterStyleRange AppliedCharacterStyle="CharacterStyle/none"><Br/>'
        '<Rectangle Self="formula-rectangle"><PDF><Link Self="formula-link" '
        'LinkResourceURI="file:C:/private/source/Equations.pdf" '
        'LinkResourceFormat="$ID/Adobe Portable Document Format (PDF)"/>'
        '</PDF></Rectangle><TextVariableInstance ResultText="(1)"/><Br/>'
        "<Content>Where: terms.</Content></CharacterStyleRange></ParagraphStyleRange>"
        if include_formula
        else ""
    )
    inline_formula = (
        '<ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/05.0.text">'
        '<CharacterStyleRange AppliedCharacterStyle="CharacterStyle/none">'
        '<Content>Rate </Content><Rectangle Self="inline-formula-rectangle"><PDF>'
        '<Link Self="inline-formula-link" '
        'LinkResourceURI="file:C:/private/source/Equations-inline.pdf" '
        'LinkResourceFormat="$ID/Adobe Portable Document Format (PDF)"/>'
        "</PDF></Rectangle><Content>: measured.</Content>"
        "</CharacterStyleRange></ParagraphStyleRange>"
        if include_inline_formula
        else ""
    )
    inline_formula_gap = (
        paragraph("05.0.text", "\n: the source-visible term definition.")
        if include_inline_formula_gap
        else ""
    )
    correspondence = (
        paragraph(
            "03.5.correspondence",
            "*Corresponding author: ana@example.org\n"
            "Conflicts of interest: The authors declare no conflicts.\n"
            "Funding: Foundation Alpha, grant 123.\n"
            "Received on: 01/02/2024 - Accepted on: 03/04/2024\n"
            "Associate editor: Bruno Costa\n"
            "Scientific editor: Carla Souza",
        )
        if include_correspondence
        else ""
    )
    graphic_mention = (
        paragraph("05.0.text", "See Figure 1 and Table 1 for the measured values.")
        if include_graphic_mention
        else ""
    )
    back_matter = (
        paragraph("04.0.section", "AUTHORS\u2019 CONTRIBUTIONS")
        + paragraph("05.0.text", "Ana Silva: Conceptualization and writing.")
        + paragraph("04.0.section", "DATA AVAILABILITY STATEMENT")
        + paragraph("05.0.text", "All data were generated in this study.")
        if include_back_matter
        else ""
    )
    stories = {
        "Stories/Story_u1.xml": story(
            "u1",
            paragraph("01.0.title", "Deterministic conversion")
            + paragraph("02.0.author", "Ana Silva*" if include_correspondence else "Ana Silva")
            + correspondence,
        ),
        "Stories/Story_u2.xml": story(
            "u2",
            paragraph("04.0.section", "Introduction")
            + paragraph("05.0.text", "Plain ")
            + paragraph("05.0.text", "emphasis", "italico")
            + graphic_mention
            + (
                paragraph("04.1.subsection", "Nested method details")
                + paragraph("05.0.text", "Nested content")
                if include_subsection
                else ""
            )
            + formula
            + inline_formula
            + inline_formula_gap
            + back_matter,
            table,
        ),
        "Stories/Story_u3.xml": story(
            "u3",
            '<ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/06.1.references">'
            '<CharacterStyleRange AppliedCharacterStyle="CharacterStyle/none">'
            "<Content>Reference one.</Content><Br/><Content>Reference two.</Content>"
            "</CharacterStyleRange></ParagraphStyleRange>",
        ),
        "Stories/Story_u4.xml": story(
            "u4",
            paragraph("07.0.caption", "Figure 1. Figure caption")
            + (paragraph("07.0.caption", "Table 1. Table caption") if include_styled_table else ""),
            '<Rectangle Self="rectangle-1"><Image><Link Self="link-1" '
            'LinkResourceURI="file:C:/private/source/Figure%201.jpg" '
            'LinkResourceFormat="$ID/JPEG"/></Image></Rectangle>',
        ),
    }
    frames = "".join(
        f"""<TextFrame Self="f{index}" ParentStory="u{index}" PreviousTextFrame="n"
        NextTextFrame="n" ItemTransform="1 0 0 1 {index * 10} {index * 20}">
        <Properties><PathGeometry><GeometryPathType><PathPointArray>
        <PathPointType Anchor="0 0"/><PathPointType Anchor="100 200"/>
        </PathPointArray></GeometryPathType></PathGeometry></Properties></TextFrame>"""
        for index in range(1, 5)
    )
    spread = f"""<?xml version="1.0" encoding="UTF-8"?>
<idPkg:Spread xmlns:idPkg="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging">
  <Spread Self="spread-1"><Page Self="page-1" Name="1"/>{frames}</Spread>
</idPkg:Spread>""".encode()

    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:

        def write(name: str, value: str | bytes, compression: int) -> None:
            info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = compression
            info.external_attr = 0o600 << 16
            archive.writestr(info, value)

        write("mimetype", "application/vnd.adobe.indesign-idml-package", ZIP_STORED)
        write("designmap.xml", design, ZIP_DEFLATED)
        write("Resources/Styles.xml", styles, ZIP_DEFLATED)
        write("Spreads/Spread_spread-1.xml", spread, ZIP_DEFLATED)
        for name, value in stories.items():
            write(name, value, ZIP_DEFLATED)
    return buffer.getvalue()
