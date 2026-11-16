"""Explicit IDML run position wins over a misleading applied style name."""

import pytest
from lxml import etree

from idml_foundation.pipeline.idml_parser import IdmlParser, _direct_character_style_name
from idml_foundation.pipeline.service import DeterministicPipeline
from tests.test_idml_fidelity_v03 import fidelity_idml
from tests.test_phase7_7c03_formulas import _mutate_story


@pytest.mark.parametrize(
    "name", ["subscrito", "superscript", "italico-sobrescrito", "bold subscript"]
)
@pytest.mark.parametrize("position", ["Normal", "Subscript", "Superscript"])
def test_explicit_position_replaces_conflicting_name_hint(name, position):
    result = _direct_character_style_name(name + " " + position, position)
    assert ("subscript" in result) == (position == "Subscript")
    assert ("superscript" in result) == (position == "Superscript")
    assert "subscrito" not in result and "sobrescrito" not in result
    assert ("italico" in result) == ("italico" in name)
    assert ("bold" in result) == ("bold" in name)


@pytest.mark.parametrize("position", [None, "", "OTSuperscript", "Unsupported"])
def test_unrecognized_or_missing_position_does_not_guess(position):
    assert _direct_character_style_name("Subscrito", position) == "subscrito"


@pytest.mark.parametrize(
    "style,position,tag",
    [
        ("subscrito", "Normal", None),
        ("sobrescrito", "Normal", None),
        ("italico-subscrito", "Normal", "italic"),
        ("bold subscript", "Normal", "bold"),
        ("subscrito", "Superscript", "sup"),
        ("sobrescrito", "Subscript", "sub"),
        ("none", "Subscript", "sub"),
        ("none", "Superscript", "sup"),
    ],
)
def test_source_properties_evidence_and_text_survive_full_pipeline(style, position, tag):
    text = "SYMBOL \u2190 \u2124 \u0404 \u00d8"

    def mutate(data):
        root = etree.fromstring(data)
        paragraph = etree.SubElement(
            root.find("Story"),
            "ParagraphStyleRange",
            AppliedParagraphStyle="ParagraphStyle/05.0.text",
        )
        run = etree.SubElement(
            paragraph,
            "CharacterStyleRange",
            AppliedCharacterStyle="CharacterStyle/" + style,
            Position=position,
        )
        etree.SubElement(run, "Content").text = text
        return etree.tostring(root)

    source = _mutate_story(fidelity_idml(), "Stories/Story_u-main.xml", mutate)
    raw = IdmlParser().parse(source, logical_name="ESA_2024999_AOP.idml")
    run = next(r for s in raw.stories for r in s.runs if r.text == text)
    raw_style = next(s for s in raw.styles if s.id == run.character_style_id)
    assert raw_style.properties["Position"] == position
    assert raw_style.parent_style_id and run.evidence_ids
    pipeline = DeterministicPipeline()
    result = pipeline.run(source, logical_name="ESA_2024999_AOP.idml")
    assert result.xml == pipeline.run(source, logical_name="ESA_2024999_AOP.idml").xml
    root = etree.fromstring(result.xml)
    nodes = root.xpath(".//*[text()=$text]", text=text)
    if tag:
        assert any(n.tag == tag for n in nodes)
    else:
        assert text in "".join(root.itertext())
        assert not root.xpath(".//sub[contains(.,'SYMBOL')] | .//sup[contains(.,'SYMBOL')]")
    assert result.validation.valid
