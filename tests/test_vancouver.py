from idml_foundation.pipeline.vancouver import numeric_citation_spans, parse_vancouver


def test_journal_reference_with_supplement_and_elocation() -> None:
    ref = parse_vancouver(
        "2. Gomes CS, Souza RPF, Silva AG, et al. Fatores associados: pesquisa, 2019. "
        "Rev Bras Epidemiol. 2021;24(Supl. 2):e210013. https://doi.org/10.1590/x"
    )
    assert ref.label == 2
    assert ref.authors == ("Gomes, CS", "Souza, RPF", "Silva, AG") and ref.et_al
    assert ref.title == "Fatores associados: pesquisa, 2019"
    assert (ref.source, ref.year, ref.volume, ref.issue) == (
        "Rev Bras Epidemiol",
        "2021",
        "24",
        "Supl. 2",
    )
    assert ref.elocation_id == "e210013" and ref.publication_type == "journal"


def test_source_without_period_spaced_pages_and_abbreviated_last_page() -> None:
    ref = parse_vancouver("7. Karasek RA. Job demands. Adm Sci Q 1979; 24(2): 285-308.")
    assert (ref.source, ref.volume, ref.issue, ref.first_page, ref.last_page) == (
        "Adm Sci Q",
        "24",
        "2",
        "285",
        "308",
    )
    assert parse_vancouver("1. Lima AB. T. J Ex. 2020;12:100-5.").last_page == "105"


def test_group_author_webpage_keeps_only_certain_fields() -> None:
    ref = parse_vancouver(
        "1. World Health Organization. Cardiovascular diseases [Internet]. "
        "World Health Organization [accessed on Apr 24, 2024]. Available at: https://x"
    )
    assert ref.collab and ref.authors == ("World Health Organization",)
    assert ref.publication_type == "webpage" and ref.source is None


def test_numeric_citation_spans() -> None:
    assert numeric_citation_spans("1") == [(0, 1, 1)]
    assert [n for _, _, n in numeric_citation_spans("2,3")] == [2, 3]
    assert [n for _, _, n in numeric_citation_spans("4-6")] == [4, 6]
    assert numeric_citation_spans("a") == [] and numeric_citation_spans("2b") == []


def test_superscript_numbers_become_bibr_xrefs_but_not_exponents() -> None:
    from idml_foundation.domain.canonical import (
        FieldState,
        InlineKind,
        InlineNode,
        Reference,
        RichText,
        SourcedText,
    )
    from idml_foundation.pipeline.citation_resolver import resolve_citations

    def text(value: str) -> SourcedText:
        return SourcedText(value=value, state=FieldState.PRESENT, confidence=1.0)

    references = tuple(
        Reference(
            id=f"r{n}", mixed_citation=RichText(plain=text(f"{n}. Silva A. T. J. 2020;1:{n}."))
        )
        for n in (1, 2, 3)
    )
    parts = [
        ("Deaths worldwide", InlineKind.TEXT),
        ("1,3", InlineKind.SUPERSCRIPT),
        (" with R", InlineKind.TEXT),
        ("2", InlineKind.SUPERSCRIPT),
        (" and 10", InlineKind.TEXT),
        ("2", InlineKind.SUPERSCRIPT),
        (".", InlineKind.TEXT),
    ]
    rich = RichText(
        plain=text("".join(value for value, _ in parts)),
        inlines=tuple(
            InlineNode(id=f"i{n}", kind=kind, text=value) for n, (value, kind) in enumerate(parts)
        ),
    )
    resolved = resolve_citations(rich, references, article_id="a", paragraph_id="p")
    xrefs = [i for i in resolved.content.inlines if i.kind == InlineKind.CROSS_REFERENCE]
    assert [(i.text, i.target_id) for i in xrefs] == [("1", "r1"), ("3", "r3")]
    assert all(i.attributes.get("source-position") == "superscript" for i in xrefs)
