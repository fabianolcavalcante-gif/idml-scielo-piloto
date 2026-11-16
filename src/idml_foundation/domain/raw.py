from enum import StrEnum
from typing import Self

from pydantic import Field, model_validator

from idml_foundation.domain.common import (
    SHA256_PATTERN,
    BoundingBox,
    Evidence,
    StrictModel,
)

RAW_SCHEMA_VERSION = "1.3.0"


class StyleKind(StrEnum):
    PARAGRAPH = "paragraph"
    CHARACTER = "character"
    TABLE = "table"
    CELL = "cell"


class RawStyle(StrictModel):
    id: str
    source_name: str
    normalized_name: str
    kind: StyleKind
    parent_style_id: str | None = None
    properties: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    evidence_ids: tuple[str, ...] = ()


class RawTextRun(StrictModel):
    id: str
    text: str
    paragraph_style_id: str | None = None
    character_style_id: str | None = None
    position: int = Field(ge=0)
    evidence_ids: tuple[str, ...] = ()


class RawParagraph(StrictModel):
    id: str
    position: int = Field(ge=0)
    paragraph_style_id: str | None = None
    text_run_ids: tuple[str, ...] = ()
    table_cell_id: str | None = None
    evidence_ids: tuple[str, ...] = ()


class RawStory(StrictModel):
    id: str
    source_self_id: str
    runs: tuple[RawTextRun, ...] = ()
    paragraphs: tuple[RawParagraph, ...] = ()
    table_ids: tuple[str, ...] = ()
    anchored_object_ids: tuple[str, ...] = ()
    note_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()


class RawTextFrame(StrictModel):
    id: str
    source_self_id: str
    parent_story_id: str
    page_index: int = Field(ge=0)
    box: BoundingBox
    transform: tuple[float, float, float, float, float, float]
    previous_frame_id: str | None = None
    next_frame_id: str | None = None
    column_index: int | None = Field(default=None, ge=0)
    evidence_ids: tuple[str, ...] = ()


class RawSpread(StrictModel):
    id: str
    source_self_id: str
    page_indices: tuple[int, ...]
    frame_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()


class RawTableCell(StrictModel):
    id: str
    row: int = Field(ge=0)
    column: int = Field(ge=0)
    row_span: int = Field(default=1, ge=1)
    column_span: int = Field(default=1, ge=1)
    text_run_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()


class RawTable(StrictModel):
    id: str
    source_self_id: str
    row_count: int = Field(ge=1)
    column_count: int = Field(ge=1)
    cells: tuple[RawTableCell, ...]
    style_id: str | None = None
    evidence_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def cells_fit_dimensions(self) -> Self:
        occupied: set[tuple[int, int]] = set()
        for cell in self.cells:
            if cell.row + cell.row_span > self.row_count:
                raise ValueError("table cell exceeds row_count")
            if cell.column + cell.column_span > self.column_count:
                raise ValueError("table cell exceeds column_count")
            coordinates = {
                (row, column)
                for row in range(cell.row, cell.row + cell.row_span)
                for column in range(cell.column, cell.column + cell.column_span)
            }
            if occupied & coordinates:
                raise ValueError("table cells cannot overlap")
            occupied.update(coordinates)
        return self


class RawObjectKind(StrEnum):
    FIGURE = "figure"
    TABLE = "table"
    FORMULA = "formula"
    MEDIA = "media"
    UNKNOWN = "unknown"


class AnchoredPlacement(StrEnum):
    BLOCK = "block"
    INLINE = "inline"
    UNKNOWN = "unknown"


class RawAnchoredObject(StrictModel):
    id: str
    source_self_id: str
    kind: RawObjectKind
    placement: AnchoredPlacement = AnchoredPlacement.UNKNOWN
    label: str | None = Field(default=None, max_length=80)
    anchor_run_id: str | None = None
    asset_ids: tuple[str, ...] = ()
    box: BoundingBox | None = None
    page_index: int | None = Field(default=None, ge=0)
    evidence_ids: tuple[str, ...] = ()


class RawAsset(StrictModel):
    id: str
    logical_path: str
    media_type: str
    sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    size_bytes: int | None = Field(default=None, ge=0)
    external: bool = False
    evidence_ids: tuple[str, ...] = ()


class RawLink(StrictModel):
    id: str
    source_id: str
    target: str
    relationship: str
    evidence_ids: tuple[str, ...] = ()


class RawNote(StrictModel):
    id: str
    source_self_id: str
    text_run_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...] = ()


class ReadingOrderIssue(StrictModel):
    code: str
    story_id: str | None = None
    frame_id: str | None = None
    details: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    evidence_ids: tuple[str, ...] = ()


class RawArticle(StrictModel):
    schema_version: str = RAW_SCHEMA_VERSION
    article_id: str
    source_artifact_sha256: str = Field(pattern=SHA256_PATTERN)
    document_self_id: str
    adobe_dom_version: str | None = None
    stories: tuple[RawStory, ...]
    frames: tuple[RawTextFrame, ...]
    spreads: tuple[RawSpread, ...]
    styles: tuple[RawStyle, ...] = ()
    tables: tuple[RawTable, ...] = ()
    anchored_objects: tuple[RawAnchoredObject, ...] = ()
    assets: tuple[RawAsset, ...] = ()
    links: tuple[RawLink, ...] = ()
    notes: tuple[RawNote, ...] = ()
    reading_order: tuple[str, ...] = ()
    reading_order_issues: tuple[ReadingOrderIssue, ...] = ()
    evidence: tuple[Evidence, ...]

    @model_validator(mode="after")
    def validate_graph(self) -> Self:
        if self.schema_version != RAW_SCHEMA_VERSION:
            raise ValueError("unsupported Raw Article schema version")
        collections = (
            self.stories,
            self.frames,
            self.spreads,
            self.styles,
            self.tables,
            self.anchored_objects,
            self.assets,
            self.links,
            self.notes,
            self.evidence,
        )
        all_ids = [item.id for collection in collections for item in collection]
        run_ids = [run.id for story in self.stories for run in story.runs]
        paragraph_ids = [paragraph.id for story in self.stories for paragraph in story.paragraphs]
        cell_ids = [cell.id for table in self.tables for cell in table.cells]
        domain_ids = all_ids + run_ids + paragraph_ids + cell_ids
        if len(set(domain_ids)) != len(domain_ids):
            raise ValueError("domain IDs must be globally unique")
        if any(not value.strip() for value in domain_ids):
            raise ValueError("domain IDs cannot be empty")

        story_ids = {item.id for item in self.stories}
        frame_ids = {item.id for item in self.frames}
        style_ids = {item.id for item in self.styles}
        table_ids = {item.id for item in self.tables}
        object_ids = {item.id for item in self.anchored_objects}
        asset_ids = {item.id for item in self.assets}
        note_ids = {item.id for item in self.notes}
        known_run_ids = set(run_ids)
        evidence_ids = {item.id for item in self.evidence}
        run_owner = {run.id: story.id for story in self.stories for run in story.runs}
        table_owner: dict[str, str] = {}
        object_owner: dict[str, str] = {}
        note_owner: dict[str, str] = {}
        for story in self.stories:
            for owned_id, owners, label in (
                *((item, table_owner, "table") for item in story.table_ids),
                *((item, object_owner, "anchored object") for item in story.anchored_object_ids),
                *((item, note_owner, "note") for item in story.note_ids),
            ):
                if owned_id in owners:
                    raise ValueError(f"{label} cannot belong to multiple stories")
                owners[owned_id] = story.id

        for frame in self.frames:
            if frame.parent_story_id not in story_ids:
                raise ValueError("frame references an unknown story")
            if frame.previous_frame_id and frame.previous_frame_id not in frame_ids:
                raise ValueError("frame references an unknown previous frame")
            if frame.next_frame_id and frame.next_frame_id not in frame_ids:
                raise ValueError("frame references an unknown next frame")
            for reference in (frame.previous_frame_id, frame.next_frame_id):
                if (
                    reference
                    and next(item.parent_story_id for item in self.frames if item.id == reference)
                    != frame.parent_story_id
                ):
                    raise ValueError("threaded frames must belong to the same story")
        for spread in self.spreads:
            if not set(spread.frame_ids) <= frame_ids:
                raise ValueError("spread references an unknown frame")
        spread_frame_ids = [frame_id for spread in self.spreads for frame_id in spread.frame_ids]
        if len(set(spread_frame_ids)) != len(spread_frame_ids):
            raise ValueError("frame cannot belong to multiple spreads")
        if set(spread_frame_ids) != frame_ids:
            raise ValueError("every frame must belong to exactly one spread")
        page_indices = [index for spread in self.spreads for index in spread.page_indices]
        if len(set(page_indices)) != len(page_indices):
            raise ValueError("page cannot belong to multiple spreads")
        if sorted(page_indices) != list(range(len(page_indices))):
            raise ValueError("page indices must be contiguous from zero")
        for story in self.stories:
            if not set(story.table_ids) <= table_ids:
                raise ValueError("story references an unknown table")
            if not set(story.anchored_object_ids) <= object_ids:
                raise ValueError("story references an unknown anchored object")
            if not set(story.note_ids) <= note_ids:
                raise ValueError("story references an unknown note")
            for paragraph in story.paragraphs:
                if not set(paragraph.text_run_ids) <= known_run_ids:
                    raise ValueError("paragraph references an unknown text run")
                if any(run_owner[run_id] != story.id for run_id in paragraph.text_run_ids):
                    raise ValueError("paragraph references a text run from another story")
                if paragraph.paragraph_style_id and paragraph.paragraph_style_id not in style_ids:
                    raise ValueError("paragraph references an unknown paragraph style")
                if paragraph.table_cell_id:
                    cell_owner = next(
                        (
                            table_owner.get(table.id)
                            for table in self.tables
                            if any(cell.id == paragraph.table_cell_id for cell in table.cells)
                        ),
                        None,
                    )
                    if cell_owner is None:
                        raise ValueError("paragraph references an unknown table cell")
                    if cell_owner != story.id:
                        raise ValueError("paragraph references a table cell from another story")
            positions = [run.position for run in story.runs]
            if sorted(positions) != list(range(len(positions))):
                raise ValueError("story run positions must be unique and contiguous")
            paragraph_positions = [paragraph.position for paragraph in story.paragraphs]
            if len(set(paragraph_positions)) != len(paragraph_positions):
                raise ValueError("story paragraph positions must be unique")
            for run in story.runs:
                if run.paragraph_style_id and run.paragraph_style_id not in style_ids:
                    raise ValueError("text run references an unknown paragraph style")
                if run.character_style_id and run.character_style_id not in style_ids:
                    raise ValueError("text run references an unknown character style")
        for style in self.styles:
            if style.parent_style_id and style.parent_style_id not in style_ids:
                raise ValueError("style references an unknown parent")
        for table in self.tables:
            if table.id not in table_owner:
                raise ValueError("table is not owned by a story")
            if table.style_id and table.style_id not in style_ids:
                raise ValueError("table references an unknown style")
            for cell in table.cells:
                if not set(cell.text_run_ids) <= known_run_ids:
                    raise ValueError("table cell references an unknown text run")
                if any(run_owner[run_id] != table_owner[table.id] for run_id in cell.text_run_ids):
                    raise ValueError("table cell references a text run from another story")
        for item in self.anchored_objects:
            if item.anchor_run_id and item.anchor_run_id not in known_run_ids:
                raise ValueError("anchored object references an unknown text run")
            if not set(item.asset_ids) <= asset_ids:
                raise ValueError("anchored object references an unknown asset")
            if (
                item.anchor_run_id
                and item.id in object_owner
                and run_owner[item.anchor_run_id] != object_owner[item.id]
            ):
                raise ValueError("anchored object references a text run from another story")
        for note in self.notes:
            if note.id not in note_owner:
                raise ValueError("note is not owned by a story")
            if not set(note.text_run_ids) <= known_run_ids:
                raise ValueError("note references an unknown text run")
            if any(run_owner[run_id] != note_owner[note.id] for run_id in note.text_run_ids):
                raise ValueError("note references a text run from another story")
        if len(set(self.reading_order)) != len(self.reading_order):
            raise ValueError("reading_order cannot contain duplicate stories")
        if not set(self.reading_order) <= story_ids:
            raise ValueError("reading_order references an unknown story")
        if set(self.reading_order) != story_ids:
            raise ValueError("reading_order must include every story")

        spread_ids = {item.id for item in self.spreads}
        for link in self.links:
            if link.relationship == "external-hyperlink":
                if link.source_id not in known_run_ids or not link.target:
                    raise ValueError("external hyperlink has an invalid endpoint")
            elif link.relationship == "external-asset":
                if link.source_id not in story_ids or link.target not in asset_ids:
                    raise ValueError("external asset link has an invalid endpoint")
            elif link.relationship == "external-layout-asset":
                if link.source_id not in spread_ids or link.target not in asset_ids:
                    raise ValueError("layout asset link has an invalid endpoint")
            else:
                raise ValueError("unsupported raw link relationship")

        evidence_bearers: list[object] = [
            item for collection in collections[:-1] for item in collection
        ]
        evidence_bearers.extend(run for story in self.stories for run in story.runs)
        evidence_bearers.extend(
            paragraph for story in self.stories for paragraph in story.paragraphs
        )
        evidence_bearers.extend(cell for table in self.tables for cell in table.cells)
        evidence_bearers.extend(self.reading_order_issues)
        for bearer in evidence_bearers:
            if not set(getattr(bearer, "evidence_ids", ())) <= evidence_ids:
                raise ValueError("component references unknown evidence")
        return self
