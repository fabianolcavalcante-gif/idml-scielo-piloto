from lxml import etree

from idml_foundation.domain.canonical import (
    CanonicalArticle,
    FieldState,
    InlineKind,
    InlineNode,
    Reference,
    RichText,
    SourcedText,
)
from idml_foundation.pipeline.citation_resolver import (
    find_citations,
    reference_signatures,
    resolve_citations,
)
from idml_foundation.pipeline.crossref_evaluation import evaluate_cross_references
from idml_foundation.pipeline.idml_parser import IdmlParser
from idml_foundation.pipeline.jats_builder import JatsBuilder
from tests.domain_helpers import canonical_article
from tests.phase3_helpers import synthetic_idml


def _present(value: str) -> SourcedText:
    return SourcedText(value=value, state=FieldState.PRESENT)


def _reference(target_id: str, value: str) -> Reference:
    return Reference(id=target_id, mixed_citation=RichText(plain=_present(value)))


def test_reference_signatures_handle_unicode_monomyms_pages_and_access_dates() -> None:
    references = (
        _reference(
            "ref-1",
            "DRÓŻDŻ, Danuta; MALINSKA, Krystyna; POSTAWA, Przemyslaw. "
            "Title. Journal, p. 2005-2017, 2020. https://doi.org/example",
        ),
        _reference(
            "ref-2",
            "EFFENDI, Hefni; WIDYATMOKO; UTOMO, Bagus; PRATIWI, Niken. Title. Journal, 2018.",
        ),
        _reference(
            "ref-3",
            "SERVIÇO AUTÔNOMO DE ÁGUA E ESGOTO (SAAE). Mananciais. SAAE, 2020. "
            "Available at: https://example.test. Accessed on: Feb. 22, 2024.",
        ),
    )

    signatures = reference_signatures(references)

    assert signatures[0].authors[0] == "DRÓŻDŻ"
    assert signatures[0].year == "2020"
    assert signatures[1].authors == ("EFFENDI", "WIDYATMOKO", "UTOMO", "PRATIWI")
    assert signatures[2].authors == ("SAAE",)
    assert signatures[2].year == "2020"


def test_find_citations_resolves_parenthetical_and_narrative_and_rejects_ambiguity() -> None:
    multi = _reference(
        "ref-multi",
        "ALVES, Paulo; SILVA, Pedro; FERREIRA, Ana; SOUZA, Rui. Title. 2019.",
    )
    pair = _reference("ref-pair", "MELCHING, Charles; FLORES, Hala. Title. 1999.")
    text = "Prior work (ALVES et al., 2019) and Melching and Flores (1999) agree."

    matches, ambiguous = find_citations(text, (multi, pair))

    assert not ambiguous
    assert [(text[item.start : item.end], item.target_id) for item in matches] == [
        ("ALVES et al., 2019", "ref-multi"),
        ("1999", "ref-pair"),
    ]

    duplicate = _reference("ref-duplicate", "ALVES, A.; BETA, B.; C, C.; D, D. 2019.")
    matches, ambiguous = find_citations("(ALVES et al., 2019)", (multi, duplicate))
    assert not matches
    assert ambiguous == ((1, 19),)


def test_find_citations_accepts_et_al_for_three_author_reference() -> None:
    reference = _reference(
        "ref-three",
        "LAGHDAF, Sid; EL BARAA, Ahmed; MOHAMED, Alia. Title. Journal, 2022.",
    )
    text = "Laghdaf et al. (2022) reported the regional cluster."

    matches, ambiguous = find_citations(text, (reference,))

    assert not ambiguous
    assert [(text[item.start : item.end], item.target_id) for item in matches] == [
        ("2022", "ref-three")
    ]


def test_resolution_preserves_text_and_styles_while_adding_bibr_target() -> None:
    reference = _reference(
        "ref-1",
        "ALVES, Paulo; SILVA, Pedro; FERREIRA, Ana; SOUZA, Rui. Title. 2019.",
    )
    text = "See (ALVES et al., 2019)."
    rich = RichText(
        plain=_present(text),
        inlines=(
            InlineNode(id="i-1", kind=InlineKind.TEXT, text="See (ALVES "),
            InlineNode(id="i-2", kind=InlineKind.EMPHASIS, text="et al."),
            InlineNode(id="i-3", kind=InlineKind.TEXT, text=", 2019)."),
        ),
    )

    resolution = resolve_citations(
        rich,
        (reference,),
        article_id="article-1",
        paragraph_id="paragraph-1",
    )

    assert "".join(item.text for item in resolution.content.inlines) == text
    citation = next(
        item for item in resolution.content.inlines if item.kind == InlineKind.CROSS_REFERENCE
    )
    assert citation.text == "ALVES et al., 2019"
    assert citation.target_id == reference.id
    assert citation.attributes == {"ref-type": "bibr"}
    assert resolution.cross_references[0].reference_type == "reference"
    assert not resolution.review_reasons


def test_calendar_date_is_not_classified_as_unresolved_citation() -> None:
    rich = RichText(plain=_present("Data collection took place on February 19, 2021."))

    resolution = resolve_citations(
        rich,
        (),
        article_id="article-1",
        paragraph_id="paragraph-1",
    )

    assert not resolution.review_reasons


def test_jats_builder_emits_bibliographic_ref_type() -> None:
    reference = _reference("reference-1", "ALVES, Paulo. Title. 2019.")
    payload = canonical_article().model_dump(mode="json")
    payload["back"]["references"] = [reference.model_dump(mode="json")]
    paragraph = payload["body"][0]["blocks"][0]
    paragraph["content"] = {
        "plain": _present("ALVES, 2019").model_dump(mode="json"),
        "inlines": [
            InlineNode(
                id="inline-bibr",
                kind=InlineKind.CROSS_REFERENCE,
                text="ALVES, 2019",
                target_id=reference.id,
                attributes={"ref-type": "bibr"},
            ).model_dump(mode="json")
        ],
    }
    paragraph["cross_references"] = [{"target_id": reference.id, "reference_type": "reference"}]
    article = CanonicalArticle.model_validate(payload)

    root = etree.fromstring(JatsBuilder().build(article))
    xref = root.xpath("//body//xref")[0]
    assert xref.get("ref-type") == "bibr"
    assert xref.get("rid") == root.xpath("//ref/@id")[0]


def test_table_cell_runs_are_bound_by_stable_cell_key() -> None:
    raw = IdmlParser().parse(
        synthetic_idml(include_table=True), logical_name="ESA_2024001_AOP.idml"
    )
    runs = {run.id: run.text for story in raw.stories for run in story.runs}

    assert len(raw.tables) == 1
    assert ["".join(runs[item] for item in cell.text_run_ids) for cell in raw.tables[0].cells] == [
        "Alpha",
        "Beta",
    ]


def test_cross_reference_evaluation_preserves_order_and_reports_target_deltas() -> None:
    expected = etree.fromstring(
        b"<article><body><p><xref ref-type='bibr' rid='B1'>a</xref>"
        b"<xref ref-type='bibr' rid='B2'>b</xref></p></body>"
        b"<back><ref-list><ref id='B1'/><ref id='B2'/></ref-list></back></article>"
    )
    actual = etree.fromstring(
        b"<article><body><p><xref ref-type='bibr' rid='R1'>a</xref>"
        b"<xref ref-type='bibr' rid='R1'>b</xref></p></body>"
        b"<back><ref-list><ref id='R1'/><ref id='R2'/></ref-list></back></article>"
    )

    result = evaluate_cross_references(expected, actual)

    assert result.matched_targets == 1
    assert result.precision == result.recall == result.f1 == 0.5
    assert result.expected_target_deficits[0].reference_ordinal == 2
    assert result.actual_target_surpluses[0].reference_ordinal == 1
    assert result.decision == "needs_review"
