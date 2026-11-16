import pytest
from lxml import etree

from idml_foundation.pipeline.autocorrection_evidence import _affiliation_lines
from idml_foundation.services.autocorrection_sources import _literal_text


@pytest.mark.parametrize(
    "label,style,expected",
    [
        ("1", "sobrescrito", "Example University"),
        ("7", "sobrescrito", "7Example University"),
        ("1", "normal", "1Example University"),
    ],
)
def test_affiliation_marker_requires_exact_number_and_separate_superscript_run(
    label, style, expected
):
    root = etree.fromstring(
        (
            "<ParagraphStyleRange><CharacterStyleRange "
            f'AppliedCharacterStyle="CharacterStyle/{style}"><Content>{label}</Content>'
            "</CharacterStyleRange><CharacterStyleRange><Content>Example University</Content>"
            "<Br/></CharacterStyleRange></ParagraphStyleRange>"
        ).encode()
    )
    raw = _literal_text(root)
    [(start, value)] = _affiliation_lines(root, raw)
    assert value == expected and raw[start : start + len(value)] == expected


@pytest.mark.parametrize("drift", [False, True])
def test_recovered_hierarchy_requires_matching_parent_locator(drift):
    import hashlib

    from idml_foundation.domain.common import Evidence, EvidenceLocator
    from idml_foundation.pipeline.affiliation_hierarchy import institution_divisions
    from tests.test_affiliation_hierarchy import affiliation

    aff = affiliation()
    original = aff.original_text.model_copy(
        update={"transformation": "affiliation-original-literal", "evidence_ids": ("exact",)}
    )
    aff = aff.model_copy(update={"original_text": original, "evidence_ids": ("source-1", "exact")})
    loc = EvidenceLocator(
        artifact_sha256="a" * 64, logical_path="Stories/Story_u1.xml", element_id="u1:paragraph:0"
    )
    base = Evidence(id="source-1", source_kind="idml", locator=loc, description="Source paragraph")
    exact = base.model_copy(
        update={
            "id": "exact",
            "content_sha256": hashlib.sha256(original.value.encode()).hexdigest(),
            "locator": loc.model_copy(
                update={
                    "element_id": "u1:paragraph:1" if drift else loc.element_id,
                    "start_offset": 2,
                    "end_offset": 2 + len(original.value),
                }
            ),
        }
    )
    assert len(institution_divisions(aff, (base, exact))) == (1 if drift else 2)
