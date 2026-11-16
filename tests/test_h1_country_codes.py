from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from lxml import etree

from idml_foundation.pipeline.profile import load_profile
from idml_foundation.pipeline.service import DeterministicPipeline
from ops.qualify_h1_country_codes import validate_profile_migration, verify_country_only_delta
from tests.phase3_helpers import synthetic_idml

ROOT = Path(__file__).resolve().parents[1]


def candidate_profile():
    return load_profile(ROOT / "profiles/esa-aop-1.1.json")


@pytest.mark.parametrize(
    "country,expected",
    [
        ("Brazil", "BR"),
        ("Brasil", "BR"),
        ("Japan", "JP"),
        ("India", "IN"),
        ("Unknown", None),
        ("Brazil / Japan", None),
    ],
)
def test_country_mapping_from_source_without_guessing(country, expected):
    target = BytesIO()
    with ZipFile(BytesIO(synthetic_idml())) as source, ZipFile(target, "w", ZIP_DEFLATED) as out:
        for name in source.namelist():
            data = source.read(name)
            if name == "Stories/Story_u1.xml":
                paragraph = (
                    '<ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/03.4.aff">'
                    '<CharacterStyleRange AppliedCharacterStyle="CharacterStyle/none">'
                    "<Content>1University Example, Department Example \u2013 "
                    f"City, {country}.</Content>"
                    "</CharacterStyleRange></ParagraphStyleRange>"
                ).encode()
                data = data.replace(b"</Story>", paragraph + b"</Story>")
            out.writestr(name, data)
    result = DeterministicPipeline(profile=candidate_profile()).run(
        target.getvalue(), logical_name="ESA_2024001_AOP.idml"
    )
    assert len(result.canonical.front.affiliations) == 1
    aff = result.canonical.front.affiliations[0]
    assert aff.country.value == country
    assert (aff.country_code.value if aff.country_code else None) == expected
    if expected:
        assert aff.country_code.evidence_ids == aff.country.evidence_ids
    node = etree.fromstring(result.xml).find("front/article-meta/aff/country")
    assert node.text == country
    assert node.get("country") == expected
    assert result.validation.valid


def test_candidate_profile_does_not_replace_active_profile():
    old, new = load_profile(), candidate_profile()
    validate_profile_migration(old, new)
    assert old.profile_id == "esa-aop-1.0.0"
    assert old.country_codes == {"India": "IN"}


@pytest.mark.parametrize(
    "update",
    [
        {"subject_category": "changed"},
        {"country_codes": {"India": "BR"}},
        {"profile_id": "unrelated"},
    ],
)
def test_migration_rejects_unrelated_changes(update):
    with pytest.raises(ValueError):
        validate_profile_migration(load_profile(), candidate_profile().model_copy(update=update))


def xml(country):
    return (
        f"<article><front><article-meta><aff>{country}</aff></article-meta></front></article>"
    ).encode()


def test_delta_guard_accepts_only_country_attribute_addition():
    assert (
        verify_country_only_delta(
            xml("<country>Brazil</country>"), xml('<country country="BR">Brazil</country>')
        )
        == 1
    )


@pytest.mark.parametrize(
    "before,after",
    [
        ('<country country="JP">Brazil</country>', '<country country="BR">Brazil</country>'),
        ("<country>Unknown</country>", '<country country="BR">Unknown</country>'),
        ("<country>Brazil</country>", '<country country="BR">Brasil</country>'),
        (
            "<country>Brazil</country>",
            '<country country="BR">Brazil</country><label>invented</label>',
        ),
        ("<country>Brazil</country>", ""),
    ],
)
def test_delta_guard_rejects_overwrite_inference_or_other_changes(before, after):
    with pytest.raises(ValueError):
        verify_country_only_delta(xml(before), xml(after))
