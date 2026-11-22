import re
from datetime import date
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, model_validator

from idml_foundation.domain.common import SHA256_PATTERN, Evidence, StrictModel
from idml_foundation.mathml import parse_mathml_fragment

CANONICAL_SCHEMA_VERSION = "1.7.0"

_ORCID = re.compile(r"^(?:https?://orcid\.org/)?(\d{4})-(\d{4})-(\d{4})-(\d{3}[\dXx])$")


class FieldState(StrEnum):
    PRESENT = "present"
    MISSING = "missing"
    AMBIGUOUS = "ambiguous"
    NEEDS_REVIEW = "needs_review"


class SourcedText(StrictModel):
    value: str | None = None
    state: FieldState
    evidence_ids: tuple[str, ...] = ()
    alternatives: tuple[str, ...] = ()
    transformation: str | None = Field(default=None, max_length=300)
    confidence: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def state_matches_value(self) -> Self:
        if self.state == FieldState.PRESENT and (self.value is None or not self.value.strip()):
            raise ValueError("present field requires a non-empty value")
        if self.state == FieldState.MISSING and self.value is not None:
            raise ValueError("missing field cannot contain a value")
        if self.state == FieldState.AMBIGUOUS and len(self.alternatives) < 2:
            raise ValueError("ambiguous field requires at least two alternatives")
        return self


class Identifier(StrictModel):
    kind: str = Field(min_length=1, max_length=80)
    value: SourcedText


class LocalizedText(StrictModel):
    language: str = Field(pattern=r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$")
    text: SourcedText


class JournalIdentity(StrictModel):
    title: SourcedText
    abbreviated_title: SourcedText | None = None
    identifiers: tuple[Identifier, ...] = ()
    publisher_name: SourcedText | None = None


class Affiliation(StrictModel):
    id: str
    institution: SourcedText
    original_text: SourcedText | None = None
    department: SourcedText | None = None
    city: SourcedText | None = None
    state_or_province: SourcedText | None = None
    country: SourcedText | None = None
    country_code: SourcedText | None = None
    ror: SourcedText | None = None
    evidence_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def country_code_is_iso_3166_alpha_2(self) -> Self:
        if self.country_code and self.country_code.value:
            if not re.fullmatch(r"[A-Z]{2}", self.country_code.value):
                raise ValueError(
                    "affiliation country_code must be an uppercase ISO 3166-1 alpha-2 code"
                )
        return self


class ContributorName(StrictModel):
    given_names: SourcedText
    surname: SourcedText
    prefix: SourcedText | None = None
    suffix: SourcedText | None = None


class Contributor(StrictModel):
    id: str
    contributor_type: Literal["person", "group"]
    name: ContributorName | None = None
    group_name: SourcedText | None = None
    orcid: SourcedText | None = None
    affiliation_ids: tuple[str, ...] = ()
    roles: tuple[str, ...] = ()
    corresponding: bool = False
    email: SourcedText | None = None
    evidence_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def contributor_has_matching_name(self) -> Self:
        if self.contributor_type == "person" and self.name is None:
            raise ValueError("person contributor requires a structured name")
        if self.contributor_type == "group" and self.group_name is None:
            raise ValueError("group contributor requires group_name")
        if self.contributor_type == "person" and self.group_name is not None:
            raise ValueError("person contributor cannot contain group_name")
        if self.contributor_type == "group" and self.name is not None:
            raise ValueError("group contributor cannot contain a structured name")
        if len(set(self.affiliation_ids)) != len(self.affiliation_ids):
            raise ValueError("contributor affiliation references cannot be duplicated")
        if self.orcid and self.orcid.value and not _valid_orcid(self.orcid.value):
            raise ValueError("contributor ORCID checksum is invalid")
        return self


class FundingStatement(StrictModel):
    agency: SourcedText
    award_id: SourcedText | None = None
    statement: SourcedText | None = None


class ArticleHistoryDate(StrictModel):
    date_type: Literal["received", "rev-request", "rev-recd", "accepted"]
    date: SourcedText

    @model_validator(mode="after")
    def date_is_present_iso_8601(self) -> Self:
        if self.date.state != FieldState.PRESENT or self.date.value is None:
            raise ValueError("article history date must be present")
        try:
            date.fromisoformat(self.date.value)
        except ValueError as exc:
            raise ValueError("article history date must use ISO 8601 YYYY-MM-DD") from exc
        return self


class FrontMatter(StrictModel):
    journal: JournalIdentity
    article_identifiers: tuple[Identifier, ...]
    article_category: SourcedText
    titles: tuple[LocalizedText, ...]
    contributors: tuple[Contributor, ...]
    affiliations: tuple[Affiliation, ...]
    publication_date: SourcedText
    history_dates: tuple[ArticleHistoryDate, ...] = ()
    volume: SourcedText | None = None
    issue: SourcedText | None = None
    abstracts: tuple[LocalizedText, ...] = ()
    keywords: tuple[LocalizedText, ...] = ()
    license_text: SourcedText | None = None
    license_url: SourcedText | None = None
    funding: tuple[FundingStatement, ...] = ()
    subject_category: SourcedText | None = None

    @model_validator(mode="after")
    def license_url_is_https(self) -> Self:
        if self.license_url and self.license_url.value:
            if not re.fullmatch(r"https://[^\s]+", self.license_url.value):
                raise ValueError("license_url must use HTTPS")
        date_types = [item.date_type for item in self.history_dates]
        if len(set(date_types)) != len(date_types):
            raise ValueError("article history date types cannot be duplicated")
        return self


class CrossReference(StrictModel):
    target_id: str
    reference_type: Literal["figure", "table", "formula", "note", "section", "reference"]
    label: str | None = None
    evidence_ids: tuple[str, ...] = ()


class InlineKind(StrEnum):
    TEXT = "text"
    EMPHASIS = "emphasis"
    STRONG = "strong"
    SUBSCRIPT = "subscript"
    SUPERSCRIPT = "superscript"
    EXTERNAL_LINK = "external_link"
    CROSS_REFERENCE = "cross_reference"
    INLINE_FORMULA = "inline_formula"
    NAMED_CONTENT = "named_content"


class FormulaRepresentation(StrEnum):
    TEXT = "text"
    LATEX = "latex"
    MATHML = "mathml"
    IMAGE = "image"
    UNKNOWN = "unknown"


class InlineNode(StrictModel):
    id: str
    kind: InlineKind
    text: str
    target_id: str | None = None
    href: str | None = None
    name: str | None = None
    attributes: dict[str, str] = Field(default_factory=dict)
    formula_source: SourcedText | None = None
    formula_representation: FormulaRepresentation | None = None
    formula_asset_id: str | None = None
    evidence_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def required_target_is_present(self) -> Self:
        if self.kind == InlineKind.CROSS_REFERENCE and self.target_id is None:
            raise ValueError("cross-reference inline requires target_id")
        if self.kind == InlineKind.EXTERNAL_LINK and self.href is None:
            raise ValueError("external link inline requires href")
        if self.kind == InlineKind.NAMED_CONTENT and self.name is None:
            raise ValueError("named content inline requires name")
        if self.kind != InlineKind.CROSS_REFERENCE and self.target_id is not None:
            raise ValueError("target_id is exclusive to cross-reference inlines")
        if self.kind != InlineKind.EXTERNAL_LINK and self.href is not None:
            raise ValueError("href is exclusive to external-link inlines")
        if self.kind != InlineKind.NAMED_CONTENT and self.name is not None:
            raise ValueError("name is exclusive to named-content inlines")
        formula_fields = (
            self.formula_source,
            self.formula_representation,
            self.formula_asset_id,
        )
        if self.kind != InlineKind.INLINE_FORMULA and any(
            value is not None for value in formula_fields
        ):
            raise ValueError("formula fields are exclusive to inline formulas")
        if self.kind == InlineKind.INLINE_FORMULA:
            if self.formula_source is None or self.formula_representation is None:
                raise ValueError("inline formula requires source and representation")
            if (
                self.formula_representation == FormulaRepresentation.IMAGE
                and self.formula_asset_id is None
            ):
                raise ValueError("inline image formula requires asset_id")
            if self.formula_representation == FormulaRepresentation.MATHML:
                parse_mathml_fragment(self.formula_source.value or "", display=False)
        return self


class RichText(StrictModel):
    plain: SourcedText
    inlines: tuple[InlineNode, ...] = ()

    @model_validator(mode="after")
    def inline_text_preserves_plain_value(self) -> Self:
        if self.plain.value is None and any(item.text for item in self.inlines):
            raise ValueError("inline text requires a plain value")
        if self.inlines and self.plain.value is not None:
            reconstructed = "".join(item.text for item in self.inlines)
            if reconstructed != self.plain.value:
                raise ValueError("inline text must preserve the plain value exactly")
        return self


class Paragraph(StrictModel):
    kind: Literal["paragraph"] = "paragraph"
    id: str
    content: RichText
    cross_references: tuple[CrossReference, ...] = ()
    evidence_ids: tuple[str, ...] = ()


class ListItem(StrictModel):
    id: str
    content: RichText
    evidence_ids: tuple[str, ...] = ()


class ListBlock(StrictModel):
    kind: Literal["list"] = "list"
    id: str
    ordered: bool
    items: tuple[ListItem, ...] = Field(min_length=1)
    evidence_ids: tuple[str, ...] = ()


class QuoteBlock(StrictModel):
    kind: Literal["quote"] = "quote"
    id: str
    content: RichText
    attribution: SourcedText | None = None
    evidence_ids: tuple[str, ...] = ()


class FigureBlock(StrictModel):
    kind: Literal["figure"] = "figure"
    id: str
    label: SourcedText
    caption: RichText
    asset_id: str | None = None
    evidence_ids: tuple[str, ...] = ()


class TableCellSpan(StrictModel):
    row: int = Field(ge=0)
    column: int = Field(ge=0)
    row_span: int = Field(default=1, ge=1)
    column_span: int = Field(default=1, ge=1)


class TableBlock(StrictModel):
    kind: Literal["table"] = "table"
    id: str
    label: SourcedText
    caption: RichText
    rows: tuple[tuple[RichText, ...], ...] = Field(min_length=1)
    cell_spans: tuple[TableCellSpan, ...] = ()
    footnotes: tuple[RichText, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    # Leading rows rendered as <thead>; derived from the journal's header cell style.
    header_rows: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def spans_fit_the_table_and_do_not_overlap(self) -> Self:
        occupied: set[tuple[int, int]] = set()
        origins: set[tuple[int, int]] = set()
        for span in self.cell_spans:
            if span.row >= len(self.rows) or span.column >= len(self.rows[span.row]):
                raise ValueError("table cell span origin is outside the table")
            if span.row + span.row_span > len(self.rows):
                raise ValueError("table cell span exceeds the table rows")
            if any(
                span.column + span.column_span > len(row)
                for row in self.rows[span.row : span.row + span.row_span]
            ):
                raise ValueError("table cell span exceeds the table columns")
            coordinates = {
                (row, column)
                for row in range(span.row, span.row + span.row_span)
                for column in range(span.column, span.column + span.column_span)
            }
            if occupied & coordinates:
                raise ValueError("table cell spans cannot overlap")
            occupied.update(coordinates)
            origins.add((span.row, span.column))
        for row, column in occupied - origins:
            if self.rows[row][column].plain.value is not None:
                raise ValueError("covered table cell cannot contain independent content")
        return self


class FormulaBlock(StrictModel):
    kind: Literal["formula"] = "formula"
    id: str
    display: bool
    source: SourcedText
    representation: FormulaRepresentation
    label: SourcedText | None = None
    asset_id: str | None = None
    evidence_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def representation_is_complete_and_safe(self) -> Self:
        if self.representation == FormulaRepresentation.IMAGE and self.asset_id is None:
            raise ValueError("image formula requires asset_id")
        if self.representation == FormulaRepresentation.MATHML:
            parse_mathml_fragment(self.source.value or "", display=self.display)
        return self


class NoteBlock(StrictModel):
    kind: Literal["note"] = "note"
    id: str
    note_type: str
    content: RichText
    evidence_ids: tuple[str, ...] = ()


ContentBlock = Annotated[
    Paragraph | ListBlock | QuoteBlock | FigureBlock | TableBlock | FormulaBlock | NoteBlock,
    Field(discriminator="kind"),
]


class Section(StrictModel):
    id: str
    title: SourcedText
    level: int = Field(ge=1, le=10)
    section_type: str | None = None
    blocks: tuple[ContentBlock, ...] = ()
    children: tuple["Section", ...] = ()
    evidence_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def children_are_deeper(self) -> Self:
        if any(child.level <= self.level for child in self.children):
            raise ValueError("child section level must be deeper than its parent")
        return self


class Asset(StrictModel):
    id: str
    logical_name: str
    media_type: str
    sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    state: FieldState
    evidence_ids: tuple[str, ...] = ()


class Reference(StrictModel):
    id: str
    mixed_citation: RichText
    identifiers: tuple[Identifier, ...] = ()
    authors: tuple[SourcedText, ...] = ()
    year: SourcedText | None = None
    title: SourcedText | None = None
    source: SourcedText | None = None
    volume: SourcedText | None = None
    issue: SourcedText | None = None
    first_page: SourcedText | None = None
    last_page: SourcedText | None = None
    elocation_id: SourcedText | None = None
    publication_type: Literal["journal", "book", "thesis", "webpage", "report", "other"] | None = (
        None
    )
    part_title: SourcedText | None = None
    editors: tuple[SourcedText, ...] = ()
    publisher_name: SourcedText | None = None
    publisher_location: SourcedText | None = None
    edition: SourcedText | None = None
    publication_description: SourcedText | None = None
    access_date: SourcedText | None = None
    review_reasons: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()


class BackMatter(StrictModel):
    acknowledgements: tuple[Paragraph, ...] = ()
    contribution_statement: SourcedText | None = None
    data_availability: SourcedText | None = None
    data_availability_mode: Literal["data-available", "data-available-upon-request"] | None = None
    conflicts: SourcedText | None = None
    notes: tuple[NoteBlock, ...] = ()
    references: tuple[Reference, ...] = ()

    @model_validator(mode="after")
    def availability_mode_requires_statement(self) -> Self:
        if self.data_availability_mode and not (
            self.data_availability and self.data_availability.value
        ):
            raise ValueError("data availability mode requires a statement")
        return self


def _walk_models(value: object) -> list[BaseModel]:
    found: list[BaseModel] = []
    if isinstance(value, BaseModel):
        found.append(value)
        for field_name in type(value).model_fields:
            found.extend(_walk_models(getattr(value, field_name)))
    elif isinstance(value, (tuple, list)):
        for item in value:
            found.extend(_walk_models(item))
    elif isinstance(value, dict):
        for item in value.values():
            found.extend(_walk_models(item))
    return found


class CanonicalArticle(StrictModel):
    schema_version: str = CANONICAL_SCHEMA_VERSION
    article_id: str
    journal_profile_id: str
    source_raw_sha256: str = Field(pattern=SHA256_PATTERN)
    front: FrontMatter
    body: tuple[Section, ...]
    back: BackMatter
    assets: tuple[Asset, ...] = ()
    evidence: tuple[Evidence, ...]
    review_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_graph(self) -> Self:
        if self.schema_version != CANONICAL_SCHEMA_VERSION:
            raise ValueError("unsupported Canonical Article schema version")
        models = _walk_models(self)
        identified = [item.id for item in models if hasattr(item, "id")]
        if len(set(identified)) != len(identified):
            raise ValueError("canonical IDs must be globally unique")
        if any(not item_id.strip() for item_id in identified):
            raise ValueError("canonical IDs cannot be empty")
        if any(section.level != 1 for section in self.body):
            raise ValueError("top-level sections must have level one")

        evidence_ids = {item.id for item in self.evidence}
        for item in models:
            refs = getattr(item, "evidence_ids", ())
            if not set(refs) <= evidence_ids:
                raise ValueError("component references unknown evidence")

        affiliation_ids = {item.id for item in self.front.affiliations}
        for contributor in self.front.contributors:
            if not set(contributor.affiliation_ids) <= affiliation_ids:
                raise ValueError("contributor references an unknown affiliation")

        asset_ids = {item.id for item in self.assets}
        target_ids = set(identified)
        target_types: dict[str, str] = {}
        for item in models:
            for model_type, reference_type in (
                (FigureBlock, "figure"),
                (TableBlock, "table"),
                (FormulaBlock, "formula"),
                (NoteBlock, "note"),
                (Section, "section"),
                (Reference, "reference"),
            ):
                if isinstance(item, model_type):
                    target_types[item.id] = reference_type
                    break
        for item in models:
            if isinstance(item, (FigureBlock, FormulaBlock)):
                if item.asset_id and item.asset_id not in asset_ids:
                    raise ValueError("content references an unknown asset")
            if isinstance(item, InlineNode) and item.formula_asset_id:
                if item.formula_asset_id not in asset_ids:
                    raise ValueError("inline formula references an unknown asset")
            if isinstance(item, CrossReference) and item.target_id not in target_ids:
                raise ValueError("cross-reference target is unknown")
            if isinstance(item, CrossReference) and (
                target_types.get(item.target_id) != item.reference_type
            ):
                raise ValueError("cross-reference type does not match its target")
            if (
                isinstance(item, InlineNode)
                and item.kind == InlineKind.CROSS_REFERENCE
                and item.target_id not in target_ids
            ):
                raise ValueError("inline cross-reference target is unknown")
            if isinstance(item, Paragraph):
                inline_targets = {
                    inline.target_id
                    for inline in item.content.inlines
                    if inline.kind == InlineKind.CROSS_REFERENCE
                }
                declared_targets = {reference.target_id for reference in item.cross_references}
                if inline_targets != declared_targets:
                    raise ValueError(
                        "paragraph cross-reference metadata must match its inline targets"
                    )
        return self


def _valid_orcid(value: str) -> bool:
    match = _ORCID.fullmatch(value.strip())
    if match is None:
        return False
    digits = "".join(match.groups())
    total = 0
    for character in digits[:-1]:
        total = (total + int(character)) * 2
    result = (12 - total % 11) % 11
    expected = "X" if result == 10 else str(result)
    return digits[-1].upper() == expected
