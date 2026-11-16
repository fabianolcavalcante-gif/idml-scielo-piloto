from idml_foundation.domain.canonical import (
    Affiliation,
    Asset,
    BackMatter,
    CanonicalArticle,
    Contributor,
    ContributorName,
    CrossReference,
    FieldState,
    FigureBlock,
    FrontMatter,
    Identifier,
    InlineKind,
    InlineNode,
    JournalIdentity,
    LocalizedText,
    Paragraph,
    RichText,
    Section,
    SourcedText,
)
from idml_foundation.domain.common import BoundingBox, Evidence, EvidenceLocator, SourceKind
from idml_foundation.domain.raw import RawArticle, RawSpread, RawStory, RawTextFrame, RawTextRun

SOURCE_SHA = "a" * 64
RAW_SHA = "b" * 64


def evidence() -> Evidence:
    return Evidence(
        id="evidence-source-1",
        source_kind=SourceKind.IDML,
        locator=EvidenceLocator(
            artifact_sha256=SOURCE_SHA,
            logical_path="Stories/Story_u1.xml",
            element_id="u1",
        ),
        description="Synthetic source locator",
    )


def sourced(value: str, *, evidence_ids: tuple[str, ...] = ("evidence-source-1",)) -> SourcedText:
    return SourcedText(
        value=value,
        state=FieldState.PRESENT,
        evidence_ids=evidence_ids,
        confidence=1.0,
    )


def rich(value: str) -> RichText:
    return RichText(
        plain=sourced(value),
        inlines=(
            InlineNode(
                id=f"inline-{len(value)}-{value[:4]}",
                kind=InlineKind.TEXT,
                text=value,
                evidence_ids=("evidence-source-1",),
            ),
        ),
    )


def raw_article() -> RawArticle:
    run = RawTextRun(
        id="run-1",
        text="Synthetic paragraph",
        position=0,
        evidence_ids=("evidence-source-1",),
    )
    story = RawStory(
        id="story-1",
        source_self_id="u1",
        runs=(run,),
        evidence_ids=("evidence-source-1",),
    )
    frame = RawTextFrame(
        id="frame-1",
        source_self_id="tf1",
        parent_story_id=story.id,
        page_index=0,
        box=BoundingBox(x=0, y=0, width=100, height=200),
        transform=(1, 0, 0, 1, 0, 0),
        evidence_ids=("evidence-source-1",),
    )
    spread = RawSpread(
        id="spread-1",
        source_self_id="spread-u1",
        page_indices=(0,),
        frame_ids=(frame.id,),
        evidence_ids=("evidence-source-1",),
    )
    return RawArticle(
        article_id="article-test-1",
        source_artifact_sha256=SOURCE_SHA,
        document_self_id="document-u1",
        adobe_dom_version="20.3",
        stories=(story,),
        frames=(frame,),
        spreads=(spread,),
        reading_order=(story.id,),
        evidence=(evidence(),),
    )


def canonical_article() -> CanonicalArticle:
    affiliation = Affiliation(
        id="affiliation-1",
        institution=sourced("Example University"),
        evidence_ids=("evidence-source-1",),
    )
    contributor = Contributor(
        id="contributor-1",
        contributor_type="person",
        name=ContributorName(
            given_names=sourced("Ana"),
            surname=sourced("Silva"),
        ),
        affiliation_ids=(affiliation.id,),
        evidence_ids=("evidence-source-1",),
    )
    asset = Asset(
        id="asset-1",
        logical_name="article-gf01.jpg",
        media_type="image/jpeg",
        sha256="c" * 64,
        state=FieldState.PRESENT,
        evidence_ids=("evidence-source-1",),
    )
    figure = FigureBlock(
        id="figure-1",
        label=sourced("Figure 1"),
        caption=rich("Synthetic figure"),
        asset_id=asset.id,
        evidence_ids=("evidence-source-1",),
    )
    paragraph = Paragraph(
        id="paragraph-1",
        content=RichText(
            plain=sourced("See Figure 1."),
            inlines=(
                InlineNode(
                    id="inline-paragraph-text",
                    kind=InlineKind.TEXT,
                    text="See ",
                    evidence_ids=("evidence-source-1",),
                ),
                InlineNode(
                    id="inline-paragraph-xref",
                    kind=InlineKind.CROSS_REFERENCE,
                    text="Figure 1",
                    target_id=figure.id,
                    evidence_ids=("evidence-source-1",),
                ),
                InlineNode(
                    id="inline-paragraph-period",
                    kind=InlineKind.TEXT,
                    text=".",
                    evidence_ids=("evidence-source-1",),
                ),
            ),
        ),
        cross_references=(
            CrossReference(
                target_id=figure.id,
                reference_type="figure",
                evidence_ids=("evidence-source-1",),
            ),
        ),
        evidence_ids=("evidence-source-1",),
    )
    return CanonicalArticle(
        article_id="article-test-1",
        journal_profile_id="esa-sps-1.10-v1",
        source_raw_sha256=RAW_SHA,
        front=FrontMatter(
            journal=JournalIdentity(
                title=sourced("Example Journal"),
                identifiers=(Identifier(kind="issn", value=sourced("1234-5678")),),
            ),
            article_identifiers=(Identifier(kind="doi", value=sourced("10.1/example")),),
            article_category=sourced("research-article"),
            titles=(LocalizedText(language="pt", text=sourced("Synthetic title")),),
            contributors=(contributor,),
            affiliations=(affiliation,),
            publication_date=sourced("2026-08-24"),
        ),
        body=(
            Section(
                id="section-1",
                title=sourced("Introduction"),
                level=1,
                blocks=(paragraph, figure),
                evidence_ids=("evidence-source-1",),
            ),
        ),
        back=BackMatter(),
        assets=(asset,),
        evidence=(evidence(),),
    )
