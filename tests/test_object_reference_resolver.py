from __future__ import annotations

from idml_foundation.domain.canonical import InlineKind, Paragraph, RichText, Section
from idml_foundation.pipeline.object_reference_resolver import resolve_object_references
from tests.domain_helpers import canonical_article, sourced


def test_resolver_links_explicit_numbered_object_mention_without_changing_prose() -> None:
    article = canonical_article()
    source_section = article.body[0]
    source_figure = source_section.blocks[1]
    paragraph = Paragraph(
        id="paragraph-object-mention",
        content=RichText(plain=sourced("As shown in Figure 1, the result is stable.")),
        evidence_ids=("evidence-source-1",),
    )
    updated = article.model_copy(
        update={
            "body": (
                Section(
                    id=source_section.id,
                    title=source_section.title,
                    level=source_section.level,
                    blocks=(paragraph, source_figure),
                    evidence_ids=source_section.evidence_ids,
                ),
            )
        }
    )

    resolved = resolve_object_references(updated)
    output = resolved.body[0].blocks[0]

    assert isinstance(output, Paragraph)
    assert output.content.plain.value == "As shown in Figure 1, the result is stable."
    links = [item for item in output.content.inlines if item.kind == InlineKind.CROSS_REFERENCE]
    assert [(item.text, item.target_id) for item in links] == [("Figure 1", source_figure.id)]


def test_resolver_is_deterministic_and_idempotent() -> None:
    article = canonical_article()

    first = resolve_object_references(article)
    second = resolve_object_references(first)

    assert first == second
