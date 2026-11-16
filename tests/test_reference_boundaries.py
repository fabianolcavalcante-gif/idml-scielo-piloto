from io import BytesIO
from zipfile import ZipFile

import pytest
from lxml import etree

from idml_foundation.pipeline.canonical_mapper import _reference_parts
from idml_foundation.pipeline.service import DeterministicPipeline
from tests.phase3_helpers import synthetic_idml


@pytest.mark.parametrize(
    ("tail", "source"),
    [
        ("Example Journal, p. 40-41, 2010.", "Example Journal"),
        ("Example Journal, n. 94, 2001.", "Example Journal"),
        ("Example Journal, n. 2, p. 40-41, 2010.", "Example Journal"),
        ("Example Journal, 2010.", "Example Journal"),
        ("City: Example Press, 2010.", "City: Example Press"),
        ("Example Journal, v. 2, p. 40-41, 2010.", "Example Journal"),
    ],
)
@pytest.mark.parametrize(
    "suffix",
    [
        "",
        " Available at: https://example.org/document.pdf. Accessed on: Feb. 15, 2024.",
        " https://doi.org/10.1234/example.2024.1",
    ],
)
def test_reference_extent_and_access_date_do_not_become_source(tail, source, suffix):
    assert _reference_parts("DOE, Ana; ROE, Jane. Example title. " + tail + suffix) == (
        ("DOE, Ana", "ROE, Jane"),
        "Example title",
        source,
    )


@pytest.mark.parametrize("given", ["H. J.", "S. R.", "L.", "Ana M.", "Ana"])
def test_no_volume_author_initials_are_not_displaced(given):
    assert _reference_parts(f"DOE, {given.rstrip('.')}. Example title. Source, 2000.") == (
        ("DOE, " + given,),
        "Example title",
        "Source",
    )


@pytest.mark.parametrize(
    "title",
    [
        "Example title; another clause",
        "Example title. A second sentence",
        "Trends, 2010. Follow-up in 2020",
        "Chapter title. In: EDITOR, Ana; EDITOR, Jane (Org.). Book title",
    ],
)
def test_title_semicolons_and_chapter_editors_do_not_become_authors(title):
    assert _reference_parts(f"DOE, Ana; ROE, Jane. {title}. Source, 2000.") == (
        ("DOE, Ana", "ROE, Jane"),
        title,
        "Source",
    )


@pytest.mark.parametrize("value", ["", "Unstructured citation", "Unstructured, 2000."])
def test_unrecognized_layout_does_not_invent_fields(value):
    assert _reference_parts(value) == ((), None, None)


def reference_idml(value):
    output = BytesIO()
    with ZipFile(BytesIO(synthetic_idml())) as source, ZipFile(output, "w") as target:
        for name in source.namelist():
            data = source.read(name)
            if name == "Stories/Story_u3.xml":
                tree = etree.fromstring(data)
                run = tree.find(".//CharacterStyleRange")
                assert run is not None
                for child in list(run):
                    run.remove(child)
                etree.SubElement(run, "Content").text = value
                data = etree.tostring(tree)
            target.writestr(name, data)
    return output.getvalue()


@pytest.mark.parametrize("marker", ["p. 40-41", "n. 2, p. 40-41"])
def test_full_pipeline_preserves_literal_citation_and_field_evidence(marker):
    value = (
        "DOE, H. J.; ROE, S. R. Example title. Example Journal, "
        + marker
        + ", 2010. Available at: https://example.org/article. Accessed on: Feb. 15, 2024."
    )
    data = reference_idml(value)
    pipeline = DeterministicPipeline()
    result = pipeline.run(data, logical_name="ESA_2024001_AOP.idml")
    reference = result.canonical.back.references[0]
    assert result.xml == pipeline.run(data, logical_name="ESA_2024001_AOP.idml").xml
    assert result.validation.valid
    assert reference.mixed_citation.plain.value == value
    assert [a.value for a in reference.authors] == ["DOE, H. J.", "ROE, S. R."]
    assert reference.title.value == "Example title"
    assert reference.source.value == "Example Journal"
    assert reference.year.value == "2010"
    assert (reference.first_page.value, reference.last_page.value) == ("40", "41")
    for field in (*reference.authors, reference.title, reference.source):
        assert field.evidence_ids == reference.mixed_citation.plain.evidence_ids
    tree = etree.fromstring(result.xml)
    citation = tree.find(".//ref/element-citation")
    assert citation.findtext("article-title") == "Example title"
    assert citation.findtext("source") == "Example Journal"
    assert citation.findall("person-group/name")[1].findtext("given-names") == "S. R."
