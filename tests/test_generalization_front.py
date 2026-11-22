from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

from lxml import etree

from idml_foundation.pipeline.profile import load_profile
from idml_foundation.pipeline.service import DeterministicPipeline

_PKG = "http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging"
_STYLES = (
    "zp.Título",
    "zp.Resumo_titulo",
    "zp.resumo",
    "zp.SUB1",
    "zp.Texto",
    "zp.refs",
    "zp.tabela_texto",
)


def _para(style: str, *lines: str) -> str:
    content = "<Br/>".join(f"<Content>{line}</Content>" for line in lines)
    return (
        f'<ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/{style}">'
        f'<CharacterStyleRange AppliedCharacterStyle="CharacterStyle/none">{content}'
        "</CharacterStyleRange></ParagraphStyleRange>"
    )


def _cell(name: str, body: str) -> str:
    return f'<Cell Name="{name}">{body}</Cell>'


def _rbepid_idml() -> bytes:
    # The abstract sits in a one-column layout table, as in the RBEPID template.
    box = (
        '<Table Self="t1" BodyRowCount="2" ColumnCount="2">'
        + _cell("0:0", _para("zp.Resumo_titulo", "ABSTRACT"))
        + _cell("1:0", _para("zp.Resumo_titulo", ""))
        + _cell(
            "0:1",
            _para(
                "zp.resumo",
                "Objective: To measure things.",
                "Methods: Cohort study.",
                "Keywords: Time series studies. Comorbidity. Mortality.",
            ),
        )
        + "</Table>"
    )
    u1 = _para("zp.Título", "A measured title") + (
        '<ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/zp.Texto">'
        f'<CharacterStyleRange AppliedCharacterStyle="CharacterStyle/none">{box}'
        "</CharacterStyleRange></ParagraphStyleRange>"
    )
    u2 = (
        _para("zp.SUB1", "INTRODUCTION")
        + _para("zp.Texto", "Body text.")
        + _para("zp.SUB1", "REFERENCES")
        + _para("zp.refs", "1. Silva A. A source. J Ex. 2020;1(1):1-2.")
    )

    def story(sid: str, body: str) -> str:
        return f'<idPkg:Story xmlns:idPkg="{_PKG}"><Story Self="{sid}">{body}</Story></idPkg:Story>'

    styles = (
        f'<idPkg:Styles xmlns:idPkg="{_PKG}"><RootParagraphStyleGroup>'
        + "".join(f'<ParagraphStyle Self="ParagraphStyle/{s}" Name="{s}"/>' for s in _STYLES)
        + "</RootParagraphStyleGroup><RootCharacterStyleGroup>"
        '<CharacterStyle Self="CharacterStyle/none" Name="none"/>'
        "</RootCharacterStyleGroup></idPkg:Styles>"
    )
    frames = "".join(
        f'<TextFrame Self="f{i}" ParentStory="u{i}" PreviousTextFrame="n" NextTextFrame="n" '
        f'ItemTransform="1 0 0 1 10 {i * 300}"><Properties><PathGeometry><GeometryPathType>'
        '<PathPointArray><PathPointType Anchor="0 0"/><PathPointType Anchor="100 200"/>'
        "</PathPointArray></GeometryPathType></PathGeometry></Properties></TextFrame>"
        for i in (1, 2)
    )
    spread = (
        f'<idPkg:Spread xmlns:idPkg="{_PKG}"><Spread Self="s1"><Page Self="p1"/>'
        f"{frames}</Spread></idPkg:Spread>"
    )
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:

        def write(name: str, value: str, compression: int = ZIP_DEFLATED) -> None:
            info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = compression
            archive.writestr(info, value)

        write("mimetype", "application/vnd.adobe.indesign-idml-package", ZIP_STORED)
        write("designmap.xml", '<Document Self="d" DOMVersion="20.0" StoryList="u1 u2"/>')
        write("Resources/Styles.xml", styles)
        write("Spreads/Spread_s1.xml", spread)
        write("Stories/Story_u1.xml", story("u1", u1))
        write("Stories/Story_u2.xml", story("u2", u2))
    return buffer.getvalue()


def _article() -> etree._Element:
    profile = load_profile(Path("profiles/rbepid-aop-1.0.json"))
    result = DeterministicPipeline(profile=profile).run(
        _rbepid_idml(), logical_name="RBEPID_2024001_IN_AOP.idml"
    )
    parser = etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True)
    return etree.fromstring(result.xml, parser=parser)


def test_abstract_in_layout_table_becomes_structured_abstract_not_a_table() -> None:
    article = _article()
    assert article.xpath("count(//table-wrap)") == 0
    sections = article.xpath("//abstract/sec")
    assert [s.findtext("title") for s in sections] == ["Objective:", "Methods:"]
    assert sections[1].findtext("p") == "Cohort study."
    assert "Keywords" not in "".join(article.xpath("//abstract//text()"))


def test_keywords_line_inside_abstract_and_dot_separator() -> None:
    article = _article()
    assert article.xpath("//kwd-group[@xml:lang='en']/kwd/text()") == [
        "Time series studies",
        "Comorbidity",
        "Mortality",
    ]


def test_reference_heading_set_as_section_is_not_a_body_section() -> None:
    article = _article()
    assert article.xpath("//body/sec/title/text()") == ["INTRODUCTION"]


def test_abstract_language_comes_from_its_heading_even_with_empty_heading_cells() -> None:
    article = _article()
    assert article.xpath("//abstract/@xml:lang") == ["en"]


def test_superscript_roman_markers_split_authors_and_attach_dangling_markers() -> None:
    from idml_foundation.pipeline.canonical_mapper import _marker_index, _split_marked_authors

    runs = [
        ("Marina Exemplo Costa Lima", False),
        ("I", True),
        (", Paula Ficticia Ramos Duarte", False),
        ("II", True),
        (",", True),
        ("III", True),
        (", Li Wei", False),  # 'Li' is a valid roman numeral but is part of the name here
        ("IV", True),
        ("*", False),
    ]
    assert _split_marked_authors(runs) == [
        ("Marina Exemplo Costa Lima", ["I"]),
        ("Paula Ficticia Ramos Duarte", ["II", "III"]),
        ("Li Wei", ["IV", "*"]),
    ]
    assert [_marker_index(t) for t in ("1", "IV", "IX", "XII", "*")] == [1, 4, 9, 12, None]


def test_labelled_history_dates_follow_profile_order_unless_unambiguous() -> None:
    from idml_foundation.pipeline.canonical_mapper import _HISTORY_LABELLED, _history_iso_date

    line = "Received on: 09/13/2024 Reviewed on: 03/04/2025 Accepted on: 03/27/2025"
    found = [(m.group("label"), m.group("date")) for m in _HISTORY_LABELLED.finditer(line)]
    assert [label for label, _ in found] == ["Received on", "Reviewed on", "Accepted on"]
    assert _history_iso_date("09/13/2024", "dmy") == "2024-09-13"  # unambiguous: m/d
    assert _history_iso_date("03/04/2025", "mdy") == "2025-03-04"
    assert _history_iso_date("03/04/2025", "dmy") == "2025-04-03"
    assert _history_iso_date("31/02/2025", "dmy") is None


def test_doi_typed_without_slash_still_gives_doi_and_profile_article_id() -> None:
    from idml_foundation.pipeline.canonical_mapper import _doi_in_text

    assert _doi_in_text("https://doi.org10.1590/1980-549720250032") == "10.1590/1980-549720250032"
    assert _doi_in_text("https://doi.org 10.1590/1980-549720250034.") == "10.1590/1980-549720250034"
    rbepid = load_profile(Path("profiles/rbepid-aop-1.0.json"))
    assert rbepid.article_id_for_doi("10.1590/1980-549720250033.2") == "e250033"
    assert load_profile(Path("profiles/esa-aop-1.1.json")).article_id_for_doi("10.1590/x") is None


def test_credit_roles_by_initials_and_contribution_line() -> None:
    from idml_foundation.domain.canonical import FieldState, SourcedText
    from idml_foundation.pipeline.canonical_mapper import (
        _CONTRIBUTIONS_LINE,
        _credit_roles,
        _name_initials,
    )

    statement = SourcedText(
        value="ABCD: Conceptualization, Writing \u2013 review & editing. EF: Validation.",
        state=FieldState.PRESENT,
        confidence=1.0,
    )
    assert _credit_roles(statement) == {
        "abcd": ("Conceptualization", "Writing \u2013 review & editing"),
        "ef": ("Validation",),
    }
    assert "pf" in _name_initials("Pedro de Faria") and "pdf" in _name_initials("Pedro de Faria")
    assert "egl" in _name_initials("Eva Gomes La-Rocha")
    assert _CONTRIBUTIONS_LINE.match("AUTHORS\u2019 CONTRIBUTIONS: ABCD: Conceptualization.")
    assert _CONTRIBUTIONS_LINE.match("Contribuições dos autores: AB: Validação.")
