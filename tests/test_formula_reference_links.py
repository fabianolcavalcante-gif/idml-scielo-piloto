import copy

import pytest
from lxml import etree

from idml_foundation.domain.canonical import (
    FieldState,
    FormulaBlock,
    FormulaRepresentation,
    InlineKind,
    InlineNode,
    Paragraph,
    RichText,
    SourcedText,
)
from idml_foundation.pipeline.jats_builder import JatsBuilder
from idml_foundation.pipeline.object_reference_resolver import resolve_object_references
from tests.domain_helpers import canonical_article, sourced


def formula(number):
    return FormulaBlock(
        id=f"formula-{number}",
        display=True,
        source=sourced("x=y"),
        representation=FormulaRepresentation.TEXT,
        label=sourced(f"({number})"),
        evidence_ids=("evidence-source-1",),
    )


def paragraph(text, identifier="p-1", inlines=()):
    return Paragraph(
        id=identifier,
        content=RichText(
            plain=sourced(text)
            if text.strip()
            else SourcedText(
                value=text,
                state=FieldState.NEEDS_REVIEW,
                evidence_ids=("evidence-source-1",),
            ),
            inlines=inlines,
        ),
        evidence_ids=("evidence-source-1",),
    )


def article_with(blocks):
    article = canonical_article()
    section = article.body[0].model_copy(update={"blocks": tuple(blocks), "children": ()})
    return article.model_copy(update={"body": (section,)})


def links(article):
    return [
        (i.text, i.target_id)
        for i in article.body[0].blocks[0].content.inlines
        if i.kind == InlineKind.CROSS_REFERENCE
    ]


@pytest.mark.parametrize(
    "text",
    [
        "Equations 11 and 12:",
        "According to Equations 11 and 12, respectively.",
        "equations\u00a011 and\u00a012",
        "Equations 11 and 12.",
        "Equations 11 and 12)",
    ],
)
def test_explicit_pair_links_both_destinations_without_changing_prose(text):
    article = article_with([paragraph(text), formula(11), formula(12)])
    before = copy.deepcopy(article)
    result = resolve_object_references(article)
    assert article == before
    assert links(result)[-1] == ("12", "formula-12")
    assert len(links(result)) == 2
    assert result.body[0].blocks[0].content.plain == article.body[0].blocks[0].content.plain
    assert result.body[0].blocks[1:] == article.body[0].blocks[1:]
    assert {r.target_id for r in result.body[0].blocks[0].cross_references} == {
        "formula-11",
        "formula-12",
    }
    assert resolve_object_references(result) == result


@pytest.mark.parametrize(
    "text",
    [
        "Equations 11 and 12a",
        "Equations 11 and 12.5",
        "Equations 11 and 12-15",
        "Equations 11 and 12\u201315",
        "Equations 11 and 12 and 13",
        "Equations 11 and 12, 13",
        "Equations 11 and 12, and 13",
        "Equation 11 and 12",
        "11 and 12",
        "Table 11 and 12",
        "Equations 11\nand 12",
        "Equations 11 or 12",
        "Equations 11 and 011",
    ],
)
def test_unqualified_grammar_never_infers_second_formula(text):
    result = resolve_object_references(article_with([paragraph(text), formula(11), formula(12)]))
    assert all(target != "formula-12" for _, target in links(result))


@pytest.mark.parametrize("numbers", [(11,), (12,), (11, 11)])
def test_missing_or_ambiguous_target_is_not_invented(numbers):
    article = article_with([paragraph("Equations 11 and 12"), *(formula(n) for n in numbers)])
    if numbers == (11, 11):
        with pytest.raises(ValueError, match="duplicate numbered"):
            resolve_object_references(article)
    else:
        assert all(t != "formula-12" for _, t in links(resolve_object_references(article)))


@pytest.mark.parametrize(
    "kind,target", [(InlineKind.CROSS_REFERENCE, "formula-12"), (InlineKind.EMPHASIS, None)]
)
def test_conflicting_or_styled_head_is_preserved(kind, target):
    first = InlineNode(
        id="prior",
        kind=kind,
        text="Equations 11",
        target_id=target,
        evidence_ids=("evidence-source-1",),
    )
    tail = InlineNode(
        id="tail", kind=InlineKind.TEXT, text=" and 12", evidence_ids=("evidence-source-1",)
    )
    article = article_with(
        [paragraph("Equations 11 and 12", inlines=(first, tail)), formula(11), formula(12)]
    )
    # Existing legacy resolver can link an emphasized head. Conflicting links are immutable.
    if kind == InlineKind.CROSS_REFERENCE:
        result = resolve_object_references(article)
        assert result.body[0].blocks[0].content.inlines == (first, tail)
    else:
        styled_tail = tail.model_copy(update={"kind": InlineKind.EMPHASIS})
        result = resolve_object_references(
            article_with(
                [
                    paragraph("Equations 11 and 12", inlines=(first, styled_tail)),
                    formula(11),
                    formula(12),
                ]
            )
        )
        assert result.body[0].blocks[0].content.inlines[-1] == styled_tail


@pytest.mark.parametrize(
    "text", ["Thus we have:", "we have:\n", "Replacing Equation 8, we have:\n\n"]
)
def test_unique_following_formula_uses_existing_intro_text(text):
    article = article_with(
        [paragraph(text), paragraph("\n\n", "blank"), formula(15), paragraph("Next.", "next")]
    )
    result = resolve_object_references(article)
    assert links(result)[-1] == ("we have", "formula-15")
    assert result.body[0].blocks[0].content.plain == article.body[0].blocks[0].content.plain
    assert result.body[0].blocks[1:] == article.body[0].blocks[1:]
    assert resolve_object_references(result) == result
    xml = etree.fromstring(JatsBuilder().build(result))
    target = xml.xpath('.//xref[@ref-type="disp-formula"]')[0]
    assert target.text == "we have"
    assert xml.xpath("//*[@id=$rid]", rid=target.get("rid"))[0].tag == "disp-formula"


@pytest.mark.parametrize(
    "scenario",
    [
        "two_formulas",
        "intervening_text",
        "other_object",
        "no_colon",
        "more_text",
        "no_label",
        "section_boundary",
        "existing_link",
        "emphasis",
    ],
)
def test_ambiguous_or_nonliteral_intro_abstains(scenario):
    p = paragraph("Thus we have:")
    blocks = [p, formula(15)]
    if scenario == "two_formulas":
        blocks.append(formula(16))
    elif scenario == "intervening_text":
        blocks.insert(1, paragraph("Other information.", "other"))
    elif scenario == "other_object":
        blocks.insert(1, canonical_article().body[0].blocks[1])
    elif scenario in {"no_colon", "more_text"}:
        blocks[0] = paragraph(
            "Thus we have." if scenario == "no_colon" else "Thus we have: more information."
        )
    elif scenario == "no_label":
        blocks[1] = blocks[1].model_copy(update={"label": None})
    elif scenario == "section_boundary":
        blocks.pop()
    elif scenario in {"existing_link", "emphasis"}:
        kind = InlineKind.CROSS_REFERENCE if scenario == "existing_link" else InlineKind.EMPHASIS
        blocks[0] = paragraph(
            "Thus we have:",
            inlines=(
                InlineNode(
                    id="kept",
                    kind=kind,
                    text="Thus we have:",
                    target_id="formula-16" if scenario == "existing_link" else None,
                    evidence_ids=("evidence-source-1",),
                ),
            ),
        )
        if scenario == "existing_link":
            blocks.append(formula(16))
    article = article_with(blocks)
    if scenario == "section_boundary":
        section = article.body[0]
        child = section.model_copy(update={"id": "child", "level": 2, "blocks": (formula(15),)})
        article = article.model_copy(
            update={"body": (section.model_copy(update={"children": (child,)}),)}
        )
    result = resolve_object_references(article)
    assert all(target != "formula-15" for _, target in links(result))
