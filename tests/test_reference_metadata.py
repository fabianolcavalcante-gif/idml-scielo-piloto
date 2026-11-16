import copy

import pytest
from lxml import etree

from idml_foundation.domain.canonical import CanonicalArticle
from idml_foundation.domain.schema_migrations import migrate_payload
from idml_foundation.pipeline.canonical_mapper import _reference_parts
from idml_foundation.pipeline.reference_metadata import access_date, reference_metadata
from idml_foundation.pipeline.service import DeterministicPipeline
from tests.test_reference_boundaries import reference_idml


@pytest.mark.parametrize(
    "month",
    [
        "Jan.",
        "February",
        "Mar",
        "Apr.",
        "May",
        "Jun",
        "July",
        "Aug",
        "Sep",
        "Sept.",
        "October",
        "NOV",
        "Dec.",
    ],
)
def test_literal_access_date(month):
    text = f"Accessed on: {month} 15, 2024"
    assert access_date("Citation. " + text + ".") == (text, ())


@pytest.mark.parametrize(
    "date", ["Feb. 30, 2024", "Feb. 29, 2023", "Xxx 15, 2024", "Jan 0, 2024", "Jan 1, 0000"]
)
def test_invalid_calendar_is_not_marked(date):
    assert access_date("Accessed on: " + date)[0] is None
    assert access_date("Accessed on: " + date)[1] == ("invalid_reference_access_date",)


@pytest.mark.parametrize(
    "date", ["03/04/2020", "2020-01-01", "May 2020", "", "May 5, 2020. Extra text"]
)
def test_ambiguous_or_unsupported_access_is_flagged(date):
    result, reasons = access_date("Accessed on: " + date)
    assert result is None and reasons


def test_repeated_access_date_is_not_silently_selected():
    assert access_date("Accessed on: May 1, 2020. Accessed on: May 1, 2020.") == (
        None,
        ("ambiguous_reference_access_date",),
    )
    assert access_date("No access marker. 2020.") == (None, ())
    assert access_date("Accessed on: Feb. 29, 2024.")[0] == "Accessed on: Feb. 29, 2024"


def parse(value):
    _, title, source = _reference_parts(value)
    return reference_metadata(value, title, source)


@pytest.mark.parametrize("edition", ["2. ed", "2nd ed", "3rd ed", "5th ed", "1st ed"])
def test_book_edition_is_not_part_of_title(edition):
    parsed = parse(f"DOE, Ana. Literal book title. {edition}. City: Press, 2000.")
    assert parsed.publication_type == "book"
    assert parsed.fields == {
        "title": "",
        "source": "Literal book title",
        "edition": edition,
        "publisher_location": "City",
        "publisher_name": "Press",
        "year": "2000",
    }


def test_book_chapter_preserves_authors_and_separates_editors():
    value = "DOE, Ana. Chapter. In: ROE, Jane; DOE, Jon (Org.). Book. City: Press, 2000. p. 3-15."
    parsed = parse(value)
    assert parsed.publication_type == "book"
    assert parsed.editors == ("ROE, Jane", "DOE, Jon")
    assert parsed.fields["part_title"] == "Chapter"
    assert parsed.fields["source"] == "Book"
    assert (parsed.fields["first_page"], parsed.fields["last_page"]) == ("3", "15")


@pytest.mark.parametrize("role", ["Org.", "Ed.", "Eds."])
def test_institutional_organizer_is_not_a_person(role):
    parsed = parse(f"DOE, Ana. Chapter. In: ORGANIZATION ({role}). Book. Publisher, 2000. p. 3-15.")
    assert parsed.editors == ()
    assert parsed.fields["publication_description"] == f"ORGANIZATION ({role})"


@pytest.mark.parametrize("dash", ["-", "\u2013", "\u2014"])
def test_explicit_thesis_type_and_access_date(dash):
    parsed = parse(
        f"DOE, Ana. Thesis. Doctoral (dissertation) {dash} University, City, 2000."
        " Accessed on: May 5, 2020."
    )
    assert parsed.publication_type == "thesis"
    assert parsed.fields["source"] == "Thesis"
    assert parsed.fields["publisher_name"] == "University"
    assert parsed.fields["publisher_location"] == "City"
    assert parsed.fields["year"] == "2000"
    assert parsed.fields["access_date"] == "Accessed on: May 5, 2020"


@pytest.mark.parametrize(
    "suffix",
    [
        "",
        " Available at: https://example.org/page.",
        " Available at: https://example.org/report.pdf.",
    ],
)
def test_url_alone_never_justifies_a_publication_type(suffix):
    parsed = parse("ORGANIZATION. Title. Publisher, 2000." + suffix)
    assert parsed.publication_type == "other"
    assert "reference_type_unresolved" in parsed.review_reasons


@pytest.mark.parametrize("marker", ["v. 4", "n. 2", "p. 10-20"])
def test_serial_layout_keeps_journal_title(marker):
    parsed = parse("DOE, Ana. Article. Journal, " + marker + ", 2000.")
    assert parsed.publication_type == "journal"
    assert "source" not in parsed.fields


def test_colon_in_journal_name_is_not_a_publisher_boundary():
    assert (
        parse("DOE, Ana. Article. Journal: Research, v. 3, p. 1-4, 2000.").publication_type
        == "journal"
    )
    assert parse("DOE, Ana. Book. City: Press, p. 1-4, 2000.").publication_type == "other"


@pytest.mark.parametrize(
    "citation, expected",
    [
        ("DOE, Ana. Book. 2nd ed. City: Press, 2000.", "book"),
        ("DOE, Ana. Chapter. In: ROE, Jane (Org.). Book. City: Press, 2000. p. 3-15.", "book"),
        (
            "DOE, Ana. Thesis. Doctoral (dissertation) - University, City, 2000."
            " Accessed on: May 5, 2020.",
            "thesis",
        ),
        ("ORGANIZATION. Title. Publisher, 2000. Accessed on: May 5, 2020.", "other"),
    ],
)
def test_complete_conversion_retains_source_and_provenance(citation, expected):
    pipeline = DeterministicPipeline()
    data = reference_idml(citation)
    result = pipeline.run(data, logical_name="ESA_2024001_AOP.idml")
    assert result.validation.valid
    assert result.xml == pipeline.run(data, logical_name="ESA_2024001_AOP.idml").xml
    ref = result.canonical.back.references[0]
    assert ref.mixed_citation.plain.value == citation
    for field in (
        ref.part_title,
        *ref.editors,
        ref.source,
        ref.publisher_name,
        ref.publisher_location,
        ref.edition,
        ref.access_date,
    ):
        if field:
            assert field.value in citation
            assert field.evidence_ids == ref.evidence_ids
    xml = etree.fromstring(result.xml).find(".//ref/element-citation")
    assert xml.get("publication-type") == expected
    assert xml.find("chapter-title") is None
    if expected in {"book", "thesis"}:
        assert xml.find("article-title") is None
    if ref.access_date:
        assert xml.find("date-in-citation").attrib == {"content-type": "access-date"}
    if expected == "other":
        assert f"reference_type_unresolved:{ref.id}" in result.canonical.review_reasons


def test_legacy_migration_is_pure_and_does_not_invent_metadata():
    result = DeterministicPipeline().run(
        reference_idml("DOE, Ana. Book. City: Press, 2000."), logical_name="ESA_2024001_AOP.idml"
    )
    old = result.canonical.model_dump(mode="json")
    old["schema_version"] = "1.4.0"
    for field in (
        "publication_type",
        "part_title",
        "editors",
        "publisher_name",
        "publisher_location",
        "edition",
        "publication_description",
        "access_date",
        "review_reasons",
    ):
        old["back"]["references"][0].pop(field)
    original = copy.deepcopy(old)
    migrated = CanonicalArticle.model_validate(migrate_payload("canonical", old))
    assert old == original
    assert migrated.schema_version == "1.6.0"
    assert migrated.back.references[0].publication_type is None
    assert migrated.back.references[0].access_date is None


def test_unstructured_reference_does_not_emit_empty_element_citation():
    result = DeterministicPipeline().run(
        reference_idml("Unstructured reference."), logical_name="ESA_2024001_AOP.idml"
    )
    assert result.validation.valid
    assert etree.fromstring(result.xml).find(".//ref/element-citation") is None
    assert result.canonical.back.references[0].review_reasons == ("reference_type_unresolved",)
