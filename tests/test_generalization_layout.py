import json
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

from idml_foundation.domain.common import content_digest
from idml_foundation.pipeline.idml_parser import IdmlParser
from idml_foundation.pipeline.profile import JournalProfile, load_profile

_PKG = "http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging"
_BOX = (
    "<Properties><PathGeometry><GeometryPathType><PathPointArray>"
    '<PathPointType Anchor="0 0"/><PathPointType Anchor="200 100"/>'
    "</PathPointArray></GeometryPathType></PathGeometry></Properties>"
)


def _frame(story: str, x: float, y: float) -> str:
    return (
        f'<TextFrame Self="f-{story}" ParentStory="{story}" PreviousTextFrame="n" '
        f'NextTextFrame="n" ItemTransform="1 0 0 1 {x} {y}">{_BOX}</TextFrame>'
    )


def _idml(page_bounds: bool = True) -> bytes:
    bounds = ' GeometricBounds="0 0 800 600" ItemTransform="1 0 0 1 0 -400"' if page_bounds else ""
    frames = (
        _frame("u1", 50, -300)  # on the page
        + _frame("u2", 900, -300)  # pasteboard leftover (right of the page)
        # Group moves an off-page-looking frame back onto the page.
        + '<Group Self="g1" ItemTransform="1 0 0 1 -800 0">'
        + _frame("u3", 900, -200)
        + "</Group>"
    )
    spread = (
        f'<idPkg:Spread xmlns:idPkg="{_PKG}"><Spread Self="s1">'
        f'<Page Self="p1"{bounds}/>{frames}</Spread></idPkg:Spread>'
    )

    def story(sid: str, text: str) -> str:
        return (
            f'<idPkg:Story xmlns:idPkg="{_PKG}"><Story Self="{sid}">'
            '<ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/05.0.text">'
            '<CharacterStyleRange AppliedCharacterStyle="CharacterStyle/none">'
            f"<Content>{text}</Content></CharacterStyleRange></ParagraphStyleRange></Story></idPkg:Story>"
        )

    styles = (
        f'<idPkg:Styles xmlns:idPkg="{_PKG}"><RootParagraphStyleGroup>'
        '<ParagraphStyle Self="ParagraphStyle/05.0.text" Name="05.0.text"/>'
        "</RootParagraphStyleGroup>"
        '<RootCharacterStyleGroup><CharacterStyle Self="CharacterStyle/none" Name="none"/>'
        "</RootCharacterStyleGroup></idPkg:Styles>"
    )
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:

        def write(name: str, value: str, compression: int = ZIP_DEFLATED) -> None:
            info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = compression
            archive.writestr(info, value)

        write("mimetype", "application/vnd.adobe.indesign-idml-package", ZIP_STORED)
        write("designmap.xml", '<Document Self="d" DOMVersion="20.0" StoryList="u1 u2 u3"/>')
        write("Resources/Styles.xml", styles)
        write("Spreads/Spread_s1.xml", spread)
        write("Stories/Story_u1.xml", story("u1", "Printed body text"))
        write("Stories/Story_u2.xml", story("u2", "Leftover from another article"))
        write("Stories/Story_u3.xml", story("u3", "Grouped printed text"))
    return buffer.getvalue()


def _texts(data: bytes) -> tuple[set[str], list[str]]:
    raw = IdmlParser().parse(data, logical_name="RBEPID_2024001_AOP.idml")
    texts = {"".join(run.text for run in story.runs) for story in raw.stories}
    excluded = [
        i.details["source_story_id"]
        for i in raw.reading_order_issues
        if i.code == "pasteboard_story_excluded"
    ]
    return texts, excluded  # type: ignore[return-value]


def test_pasteboard_story_is_excluded_but_grouped_frame_on_page_is_kept() -> None:
    texts, excluded = _texts(_idml())
    assert excluded == ["u2"]
    assert texts == {"Printed body text", "Grouped printed text"}


def test_without_page_bounds_nothing_is_excluded() -> None:
    texts, excluded = _texts(_idml(page_bounds=False))
    assert excluded == []
    assert "Leftover from another article" in texts


def test_name_based_roles_take_precedence_and_keep_legacy_digest() -> None:
    esa = load_profile(Path("profiles/esa-aop-1.1.json"))
    assert "style_name_roles" not in json.loads(esa.model_dump_json())
    data = json.loads(Path("profiles/esa-aop-1.1.json").read_text(encoding="utf-8"))
    assert content_digest(JournalProfile.model_validate(data)) == content_digest(esa)
    named = JournalProfile.model_validate(
        {**data, "style_name_roles": {"zp.Texto": "paragraph", "05.0.text": "abstract"}}
    )
    assert named.role_for_style("zp.Texto", None) == "paragraph"
    assert named.role_for_style("05.0.text", "05.0") == "abstract"
    assert named.role_for_style("05.1.list", "05.1") == "list-level-1"
    rbepid = load_profile(Path("profiles/rbepid-aop-1.0.json"))
    assert rbepid.role_for_style("zp.titulação", None) == "affiliations"


def test_leading_header_styled_rows_become_thead_and_th() -> None:
    from io import BytesIO as _BytesIO
    from zipfile import ZipFile as _ZipFile

    from idml_foundation.pipeline.service import DeterministicPipeline
    from tests.phase3_helpers import synthetic_idml

    source = _ZipFile(_BytesIO(synthetic_idml(include_table=True, include_styled_table=True)))
    buffer = _BytesIO()
    with _ZipFile(buffer, "w") as target:
        for info in source.infolist():
            data = source.read(info.filename)
            if info.filename == "Resources/Styles.xml":
                data = data.replace(
                    b"</RootParagraphStyleGroup>",
                    b'<ParagraphStyle Self="ParagraphStyle/07.1.head" Name="07.1.head"/>'
                    b"</RootParagraphStyleGroup>",
                )
            if info.filename == "Stories/Story_u2.xml":
                data = data.replace(
                    b'<Cell Name="0:0"><ParagraphStyleRange '
                    b'AppliedParagraphStyle="ParagraphStyle/05.0.text">',
                    b'<Cell Name="0:0"><ParagraphStyleRange '
                    b'AppliedParagraphStyle="ParagraphStyle/07.1.head">',
                )
                data = data.replace(
                    b'BodyRowCount="1" ColumnCount="2"', b'BodyRowCount="2" ColumnCount="1"'
                )
                data = data.replace(b'<Cell Name="1:0">', b'<Cell Name="0:1">')
            target.writestr(info, data)
    profile = load_profile(Path("profiles/esa-aop-1.1.json"))
    xml = (
        DeterministicPipeline(profile=profile)
        .run(buffer.getvalue(), logical_name="ESA_2024001_AOP.idml")
        .xml
    )
    assert b"<thead><tr><th>kgO<sub>2</sub>/h</th></tr></thead>" in xml
    assert b"<tbody><tr><td>Beta</td></tr></tbody>" in xml
