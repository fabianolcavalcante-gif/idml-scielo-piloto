# ruff: noqa: RUF001 - literal dash variants are the test subjects
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from lxml import etree

from idml_foundation.domain.canonical import ArticleHistoryDate
from idml_foundation.pipeline.jats_builder import JatsBuilder
from idml_foundation.pipeline.metadata_normalization import (
    normalize_credit_writing_role,
    split_explicit_brazil_state,
)
from idml_foundation.pipeline.profile import load_profile
from idml_foundation.pipeline.service import DeterministicPipeline
from idml_foundation.pipeline.validation import OfflineJatsValidator
from ops.qualify_vh1_metadata import verify_delta
from ops.v05_fixture import complete_article
from tests.domain_helpers import canonical_article, sourced
from tests.phase3_helpers import synthetic_idml

ROOT = Path(__file__).resolve().parents[1]


def delta_fixture():
    before = (
        "<article><front><article-meta><contrib-group><contrib>"
        "<role>Writing—original draft</role></contrib></contrib-group>"
        '<aff><institution content-type="original">'
        "Institution – São Carlos (SP), Brazil.</institution>"
        '<addr-line><named-content content-type="city">São Carlos (SP)</named-content></addr-line>'
        "<country>Brazil</country></aff>"
        '<pub-date date-type="pub"><year>2025</year></pub-date><history/>'
        "</article-meta></front><body><p>Unchanged science</p></body></article>"
    )
    after = before.replace(
        "<role>Writing—original draft</role>",
        '<role content-type="https://credit.niso.org/contributor-roles/writing-original-draft/">'
        "Writing – original draft</role>",
    ).replace(
        ">São Carlos (SP)</named-content>",
        '>São Carlos</named-content><named-content content-type="state">SP</named-content>',
    )
    return before.encode(), after.encode()


def test_complete_xml_delta_accepts_only_the_expected_representation_changes():
    assert verify_delta(*delta_fixture()) == {
        "states_extracted": 1,
        "credit_roles_normalized": 1,
        "publication_year_added": 0,
    }


@pytest.mark.parametrize(
    "before,after",
    [
        (b"Unchanged science", b"Changed science"),
        (b">SP<", b">RJ<"),
        (b"<history/>", b'<history><date date-type="pub"><year>2025</year></date></history>'),
        (b"writing-original-draft/", b"supervision/"),
        (b"<country>Brazil</country>", b"<country>India</country>"),
    ],
)
def test_complete_xml_delta_rejects_unrelated_changes(before, after):
    baseline, candidate = delta_fixture()
    assert before in candidate
    with pytest.raises(ValueError, match="unexpected_metadata_delta"):
        verify_delta(baseline, candidate.replace(before, after))


@pytest.mark.parametrize("country", ["Brazil", "Brasil"])
def test_explicit_state_is_extracted_with_original_evidence(country):
    line = f"University Example, Department Example – São Carlos (SP), {country}."
    target = BytesIO()
    with ZipFile(BytesIO(synthetic_idml())) as source, ZipFile(target, "w", ZIP_DEFLATED) as out:
        for name in source.namelist():
            data = source.read(name)
            if name == "Stories/Story_u1.xml":
                paragraph = (
                    '<ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/03.4.aff">'
                    '<CharacterStyleRange AppliedCharacterStyle="CharacterStyle/none">'
                    f"<Content>1{escape(line)}</Content>"
                    "</CharacterStyleRange></ParagraphStyleRange>"
                ).encode()
                data = data.replace(b"</Story>", paragraph + b"</Story>")
            out.writestr(name, data)
    result = DeterministicPipeline(profile=load_profile(ROOT / "profiles/esa-aop-1.1.json")).run(
        target.getvalue(), logical_name="ESA_2024001_AOP.idml"
    )
    aff = result.canonical.front.affiliations[0]
    assert aff.original_text.value == line
    assert aff.city.value == "São Carlos"
    assert aff.state_or_province.value == "SP"
    assert aff.state_or_province.evidence_ids == aff.original_text.evidence_ids
    assert aff.state_or_province.transformation == "explicit-affiliation-parenthesized-uf"
    assert result.validation.valid
    root = etree.fromstring(result.xml)
    assert root.xpath('string(//aff/addr-line/named-content[@content-type="state"])') == "SP"


@pytest.mark.parametrize(
    "city,country",
    [
        ("São Carlos", "Brazil"),
        ("São Carlos (XX)", "Brazil"),
        ("City (SP)", "India"),
        ("City (SP)", "Unknown"),
        ("City (sp)", "Brazil"),
        ("City (SP/RJ)", "Brazil"),
        ("City (SP) (RJ)", "Brazil"),
        ("(SP)", "Brazil"),
        ("Tokyo", "Japan"),
    ],
)
def test_state_is_never_guessed_or_taken_from_ambiguous_notation(city, country):
    assert split_explicit_brazil_state(city, country) == (city, None)


@pytest.mark.parametrize(
    "source,canonical,slug",
    [
        ("Writing—original draft", "Writing – original draft", "writing-original-draft"),
        ("Writing-original draft", "Writing – original draft", "writing-original-draft"),
        ("Writing – original draft", "Writing – original draft", "writing-original-draft"),
        ("Writing—review and editing", "Writing – review & editing", "writing-review-editing"),
        ("Writing – review & editing", "Writing – review & editing", "writing-review-editing"),
    ],
)
def test_credit_normalizes_representation_not_author_assignment(source, canonical, slug):
    article = canonical_article()
    authors = article.front.contributors
    changed = article.model_copy(
        update={
            "front": article.front.model_copy(
                update={
                    "contributors": (
                        authors[0].model_copy(update={"roles": (source,)}),
                        *authors[1:],
                    )
                }
            )
        }
    )
    root = etree.fromstring(JatsBuilder().build(changed))
    role = root.find("front/article-meta/contrib-group/contrib/role")
    assert role.text == canonical
    assert role.get("content-type") == f"https://credit.niso.org/contributor-roles/{slug}/"
    assert changed.front.contributors[0].roles == (source,)
    assert normalize_credit_writing_role(canonical) == canonical


@pytest.mark.parametrize(
    "role",
    [
        "Writing",
        "Writing—original draft (supporting)",
        "Review and editing",
        "Writing—original draft; Supervision",
        "Writing—review or editing",
        "Unknown role",
    ],
)
def test_credit_unknown_or_combined_role_is_not_classified(role):
    assert normalize_credit_writing_role(role) == role


@pytest.mark.parametrize(
    "publication,expected_year,complete",
    [
        ("2025", "2025", False),
        ("2025-09-03", "2025", True),
        ("unknown", None, False),
    ],
)
def test_publication_history_preserves_precision_and_never_creates_revision_dates(
    publication, expected_year, complete
):
    article = complete_article()
    article = article.model_copy(
        update={
            "front": article.front.model_copy(
                update={
                    "publication_date": sourced(publication),
                    "history_dates": (
                        ArticleHistoryDate(date_type="received", date=sourced("2024-01-02")),
                        ArticleHistoryDate(date_type="accepted", date=sourced("2025-06-03")),
                    ),
                }
            )
        }
    )
    xml = JatsBuilder().build(article)
    root = etree.fromstring(xml)
    pubs = root.xpath('front/article-meta/history/date[@date-type="pub"]')
    assert len(pubs) == (1 if complete else 0)
    if expected_year:
        publication_node = root.find('front/article-meta/pub-date[@date-type="pub"]')
        assert publication_node.findtext("year") == expected_year
        assert (publication_node.find("day") is not None) == complete
        assert (publication_node.find("month") is not None) == complete
    if pubs:
        assert pubs[0].findtext("year") == expected_year
        assert (pubs[0].find("day") is not None) == complete
        assert (pubs[0].find("month") is not None) == complete
        assert (pubs[0].get("iso-8601-date") is not None) == complete
    assert not root.xpath('front/article-meta/history/date[starts-with(@date-type,"rev-")]')
    if expected_year:
        assert (
            OfflineJatsValidator(ROOT / "vendor/jats/1.3")
            .validate(xml, asset_names={asset.logical_name for asset in article.assets})
            .valid
        )
