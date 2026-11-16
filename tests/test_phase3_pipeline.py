import hashlib
import json
from pathlib import Path

import pytest
from lxml import etree

from idml_foundation.domain.canonical import CanonicalArticle, FormulaRepresentation, InlineKind
from idml_foundation.domain.common import canonical_bytes
from idml_foundation.pipeline.canonical_mapper import CanonicalMapper
from idml_foundation.pipeline.idml_parser import IdmlParser, style_prefix
from idml_foundation.pipeline.jats_builder import IdRegistry, IdRegistryError, JatsBuilder
from idml_foundation.pipeline.profile import load_profile
from idml_foundation.pipeline.service import DeterministicPipeline
from idml_foundation.pipeline.validation import OfflineJatsValidator, ValidationSeverity
from tests.phase3_helpers import synthetic_idml


def test_parser_reconstructs_raw_graph_and_sanitizes_external_paths() -> None:
    raw = IdmlParser().parse(synthetic_idml(), logical_name="ESA_2024001_AOP.idml")

    assert len(raw.stories) == 4
    assert len(raw.frames) == 4
    assert len(raw.reading_order) == 4
    assert not raw.reading_order_issues
    assert raw.assets[0].logical_path == "Figure 1.jpg"
    assert "private" not in canonical_bytes(raw).decode()
    assert style_prefix("05.0.texto") == "05.0"
    assert style_prefix("0.1.doi") == "0.1"
    assert style_prefix("unknown") is None


def test_mapper_records_missing_and_ambiguities_without_using_gold_xml() -> None:
    raw = IdmlParser().parse(synthetic_idml(), logical_name="ESA_2024001_AOP.idml")
    article = CanonicalMapper(load_profile()).map(raw)

    assert article.article_id == "e20240001"
    assert article.front.publication_date.value is None
    assert len(article.front.contributors) == 1
    assert len(article.back.references) == 2
    figure = next(
        block for section in article.body for block in section.blocks if block.kind == "figure"
    )
    assert figure.label.value == "Figure 1"
    assert figure.caption.plain.value == "Figure caption"
    assert "external_assets_require_package_resolution" in article.review_reasons


def test_pipeline_structures_labeled_correspondence_without_inference() -> None:
    result = DeterministicPipeline().run(
        synthetic_idml(include_correspondence=True),
        logical_name="ESA_2024001_AOP.idml",
    )
    article = result.canonical
    root = etree.fromstring(result.xml)

    contributor = article.front.contributors[0]
    assert contributor.corresponding is True
    assert contributor.email is not None
    assert contributor.email.value == "ana@example.org"
    assert [(item.date_type, item.date.value) for item in article.front.history_dates] == [
        ("received", "2024-02-01"),
        ("accepted", "2024-04-03"),
    ]
    assert len(article.front.funding) == 1
    assert article.front.funding[0].agency.value == "Foundation Alpha"
    assert article.front.funding[0].statement is not None
    assert article.front.funding[0].statement.value == "Foundation Alpha, grant 123."
    assert article.back.conflicts is not None
    assert article.back.conflicts.value == "The authors declare no conflicts."
    assert [note.note_type for note in article.back.notes] == [
        "associate-editor",
        "scientific-editor",
    ]
    assert root.xpath("string(front/article-meta/author-notes/corresp/email)") == (
        "ana@example.org"
    )
    assert root.xpath("count(front/article-meta/history/date)") == 2.0
    assert root.xpath("count(front/article-meta/funding-group/funding-statement)") == 1.0
    assert root.xpath("count(front/article-meta/author-notes/fn[@fn-type='coi-statement'])") == 1.0
    assert (
        root.xpath(
            "count(front/article-meta/author-notes/fn[@fn-type='edited-by']"
            "[label='Associate editor:'])"
        )
        == 1.0
    )
    assert (
        root.xpath(
            "count(front/article-meta/author-notes/fn[@fn-type='edited-by']"
            "[label='Scientific editor:'])"
        )
        == 1.0
    )
    assert root.xpath("count(back/fn-group/fn[@fn-type='financial-disclosure'])") == 1.0
    assert "associate_editor_orcid_requires_enrichment" in article.review_reasons
    assert "scientific_editor_orcid_requires_enrichment" in article.review_reasons
    assert result.validation.valid


def test_pipeline_moves_labeled_back_matter_and_preserves_styled_table_cells() -> None:
    result = DeterministicPipeline().run(
        synthetic_idml(
            include_table=True,
            include_styled_table=True,
            include_back_matter=True,
            include_graphic_mention=True,
        ),
        logical_name="ESA_2024001_AOP.idml",
    )
    article = result.canonical
    root = etree.fromstring(result.xml)

    assert len(article.body) == 1
    assert article.body[0].title.value == "INTRODUCTION"
    assert {block.kind for block in article.body[0].blocks} >= {"figure", "table"}
    assert article.back.contribution_statement is not None
    assert article.back.contribution_statement.value == (
        "Ana Silva: Conceptualization and writing."
    )
    assert article.back.data_availability is not None
    assert article.back.data_availability.value == "All data were generated in this study."
    table = next(block for block in article.body[0].blocks if block.kind == "table")
    assert table.rows[0][0].plain.value == "kgO2/h"
    assert [item.kind for item in table.rows[0][0].inlines] == [
        InlineKind.TEXT,
        InlineKind.SUBSCRIPT,
        InlineKind.TEXT,
    ]
    assert root.xpath("string(body//table-wrap/table/tbody/tr[1]/td)") == "kgO2/h"
    assert root.xpath("string(body//table-wrap/table/tbody/tr[1]/td/sub)") == "2"
    assert root.xpath("count(back/sec[title='Author contributions'])") == 1.0
    assert root.xpath("count(back/sec[title='DATA AVAILABILITY STATEMENT'])") == 1.0
    assert result.validation.valid


def test_mapper_nests_level_two_sections_under_the_preceding_level_one() -> None:
    raw = IdmlParser().parse(
        synthetic_idml(include_subsection=True),
        logical_name="ESA_2024001_AOP.idml",
    )
    article = CanonicalMapper(load_profile()).map(raw)

    assert len(article.body) == 1
    introduction = article.body[0]
    assert introduction.title.value == "INTRODUCTION"
    assert len(introduction.children) == 1
    assert introduction.children[0].level == 2
    assert introduction.children[0].title.value == "Nested method details"
    assert introduction.children[0].blocks[0].content.plain.value == "Nested content"


def test_pipeline_preserves_anchored_pdf_formula_as_reviewable_image() -> None:
    result = DeterministicPipeline().run(
        synthetic_idml(include_formula=True),
        logical_name="ESA_2024001_AOP.idml",
    )
    root = etree.fromstring(result.xml)

    formula = next(block for block in result.canonical.body[0].blocks if block.kind == "formula")
    assert formula.kind == "formula"
    assert formula.representation == "image"
    assert formula.source.value == "Equations.pdf"
    assert formula.label is not None and formula.label.value == "(1)"
    assert result.canonical.body[0].blocks.index(formula) < next(
        index
        for index, block in enumerate(result.canonical.body[0].blocks)
        if block.kind == "paragraph" and block.content.plain.value == "\nWhere: terms."
    )
    assert any(
        reason.startswith("formula_requires_mathml_transcription:")
        for reason in result.canonical.review_reasons
    )
    assert root.xpath("count(body//disp-formula/graphic)") == 1.0
    assert root.xpath("string(body//disp-formula/label)") == "(1)"
    assert result.validation.valid


def test_pipeline_maps_inline_pdf_formula_without_losing_text_order() -> None:
    result = DeterministicPipeline().run(
        synthetic_idml(include_inline_formula=True),
        logical_name="ESA_2024001_AOP.idml",
    )
    root = etree.fromstring(result.xml)
    paragraph = next(
        block
        for block in result.canonical.body[0].blocks
        if block.kind == "paragraph" and block.content.plain.value == "Rate : measured."
    )
    inline = next(
        item for item in paragraph.content.inlines if item.kind == InlineKind.INLINE_FORMULA
    )

    assert inline.formula_representation == FormulaRepresentation.IMAGE
    assert inline.formula_source is not None
    assert inline.formula_source.value == "Equations-inline.pdf"
    assert root.xpath("count(body//p/inline-formula/inline-graphic)") == 1.0
    assert result.validation.valid


def test_pipeline_structures_inline_formula_gap_without_inventing_xml() -> None:
    result = DeterministicPipeline().run(
        synthetic_idml(include_inline_formula_gap=True),
        logical_name="ESA_2024001_AOP.idml",
    )
    root = etree.fromstring(result.xml)
    paragraph = next(
        block
        for block in result.canonical.body[0].blocks
        if block.kind == "paragraph"
        and block.content.plain.value == "\n: the source-visible term definition."
    )
    formula = next(
        inline for inline in paragraph.content.inlines if inline.kind == InlineKind.INLINE_FORMULA
    )

    assert formula.text == ""
    assert formula.formula_representation == FormulaRepresentation.UNKNOWN
    assert formula.formula_source is not None
    assert formula.formula_source.value is None
    assert formula.formula_source.state.value == "needs_review"
    assert (
        "".join(inline.text for inline in paragraph.content.inlines)
        == paragraph.content.plain.value
    )
    assert any(
        reason.startswith("possible_missing_inline_formula:")
        for reason in result.canonical.review_reasons
    )
    assert root.xpath("count(body//inline-formula)") == 0.0
    assert ": the source-visible term definition." in root.xpath("string(body)")
    assert result.validation.valid


def test_builder_emits_valid_mathml_for_display_and_inline_formulas() -> None:
    result = DeterministicPipeline().run(
        synthetic_idml(include_formula=True, include_inline_formula=True),
        logical_name="ESA_2024001_AOP.idml",
    )
    payload = result.canonical.model_dump(mode="json")
    display = next(block for block in payload["body"][0]["blocks"] if block["kind"] == "formula")
    display["representation"] = "mathml"
    display["source"]["value"] = (
        '<mml:math xmlns:mml="http://www.w3.org/1998/Math/MathML" display="block">'
        "<mml:mrow><mml:mi>x</mml:mi><mml:mo>=</mml:mo><mml:mn>1</mml:mn>"
        "</mml:mrow></mml:math>"
    )
    paragraph = next(
        block
        for block in payload["body"][0]["blocks"]
        if block["kind"] == "paragraph" and block["content"]["plain"]["value"] == "Rate : measured."
    )
    inline = next(
        item for item in paragraph["content"]["inlines"] if item["kind"] == "inline_formula"
    )
    inline["text"] = "y"
    inline["formula_representation"] = "mathml"
    inline["formula_source"]["value"] = (
        '<mml:math xmlns:mml="http://www.w3.org/1998/Math/MathML" display="inline">'
        "<mml:mi>y</mml:mi></mml:math>"
    )
    paragraph["content"]["plain"]["value"] = "Rate y: measured."
    article = CanonicalArticle.model_validate(payload)
    xml = JatsBuilder().build(article)
    validation = OfflineJatsValidator(
        Path(__file__).parents[1] / "vendor" / "jats" / "1.3"
    ).validate(
        xml,
        asset_names={asset.logical_name for asset in article.assets},
    )
    root = etree.fromstring(xml)

    assert (
        root.xpath(
            "count(body//disp-formula/mml:math)",
            namespaces={"mml": "http://www.w3.org/1998/Math/MathML"},
        )
        == 1.0
    )
    assert (
        root.xpath(
            "count(body//inline-formula/mml:math)",
            namespaces={"mml": "http://www.w3.org/1998/Math/MathML"},
        )
        == 1.0
    )
    assert validation.valid


def test_pipeline_is_byte_deterministic_and_offline_dtd_valid() -> None:
    pipeline = DeterministicPipeline()
    first = pipeline.run(synthetic_idml(), logical_name="ESA_2024001_AOP.idml")
    second = pipeline.run(synthetic_idml(), logical_name="ESA_2024001_AOP.idml")

    assert first.xml == second.xml
    assert canonical_bytes(first.raw) == canonical_bytes(second.raw)
    assert canonical_bytes(first.canonical) == canonical_bytes(second.canonical)
    assert first.validation == second.validation
    assert first.validation.valid
    assert first.validation.issues
    assert all(
        item.code == "uncited-reference" and item.severity == ValidationSeverity.WARNING
        for item in first.validation.issues
    )


def test_id_registry_rejects_duplicates_and_orphans() -> None:
    registry = IdRegistry()
    registry.register("known")
    with pytest.raises(IdRegistryError, match="duplicate"):
        registry.register("known")
    with pytest.raises(IdRegistryError, match="orphan"):
        registry.resolve("missing")


def test_validator_normalizes_malformed_xml_and_unsafe_assets() -> None:
    vendor = Path(__file__).parents[1] / "vendor" / "jats" / "1.3"
    validator = OfflineJatsValidator(vendor)
    malformed = validator.validate(b"<article>")
    assert not malformed.valid
    assert malformed.issues[0].code == "xml-not-well-formed"

    raw = IdmlParser().parse(synthetic_idml(), logical_name="ESA_2024001_AOP.idml")
    article = CanonicalMapper(load_profile()).map(raw)
    xml = JatsBuilder().build(article).replace(b"Figure 1.jpg", b"https://bad.invalid/x")
    report = validator.validate(xml)
    assert not report.valid
    assert any(
        item.code == "unsafe-asset-reference" and item.severity == ValidationSeverity.ERROR
        for item in report.issues
    )


def test_validator_checks_bibliography_reference_semantics() -> None:
    vendor = Path(__file__).parents[1] / "vendor" / "jats" / "1.3"
    validator = OfflineJatsValidator(vendor)
    xml = DeterministicPipeline().run(synthetic_idml(), logical_name="ESA_2024001_AOP.idml").xml
    root = etree.fromstring(xml)
    reference_ids = [item.get("id") for item in root.xpath("//ref")]
    cited = xml.replace(
        b"</p>",
        (f'<xref ref-type="bibr" rid="{" ".join(reference_ids)}">[1,2]</xref></p>').encode(),
        1,
    )
    cited_report = validator.validate(cited)
    assert not any(item.code in {"orphan-rid", "uncited-reference"} for item in cited_report.issues)

    figure_id = str(root.xpath("//fig/@id")[0])
    wrong_target = xml.replace(
        b"</p>",
        f'<xref ref-type="bibr" rid="{figure_id}">[x]</xref></p>'.encode(),
        1,
    )
    wrong_report = validator.validate(wrong_target)
    assert any(item.code == "invalid-bibliography-rid-target" for item in wrong_report.issues)


def test_vendored_jats_files_match_pinned_provenance() -> None:
    vendor = Path(__file__).parents[1] / "vendor" / "jats" / "1.3"
    provenance = json.loads((vendor / "SOURCE.json").read_text(encoding="utf-8"))
    assert provenance["archive_sha256"] == (
        "41ddeaf6eeb04eb64244e9894212e0aaeafdbb9114d20602da2d855ad39b9b7b"
    )
    for name, expected in provenance["files"].items():
        assert hashlib.sha256((vendor / name).read_bytes()).hexdigest() == expected
