from __future__ import annotations

import hashlib
import mimetypes
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePosixPath
from typing import cast
from urllib.parse import unquote, urlparse
from zipfile import ZipFile

from lxml import etree

from idml_foundation.asset_identity import equation_asset_placement, figure_asset_number
from idml_foundation.domain.common import (
    BoundingBox,
    Evidence,
    EvidenceLocator,
    SourceKind,
    stable_id,
)
from idml_foundation.domain.raw import (
    AnchoredPlacement,
    RawAnchoredObject,
    RawArticle,
    RawAsset,
    RawLink,
    RawNote,
    RawObjectKind,
    RawParagraph,
    RawSpread,
    RawStory,
    RawStyle,
    RawTable,
    RawTableCell,
    RawTextFrame,
    RawTextRun,
    ReadingOrderIssue,
    StyleKind,
)
from idml_foundation.ingest.safe_zip import UnsafeArchiveError, inspect_idml
from idml_foundation.ingest.xml_security import (
    UnsafeXmlError,
    XmlComplexityBudget,
    parse_untrusted_xml,
)
from idml_foundation.pipeline.profile import DIRECT_PARAGRAPH_SUFFIX
from idml_foundation.settings import Settings

_STYLE_PREFIX = re.compile(r"^(\d{1,2}(?:\.\d+)?)")
_NULL_REFERENCE = {"", "n", "$ID/"}


def _local_name(element: etree._Element) -> str:
    return etree.QName(element).localname if isinstance(element.tag, str) else ""


def _elements(root: etree._Element, name: str) -> list[etree._Element]:
    return [element for element in root.iter() if _local_name(element) == name]


def _direct_elements(root: etree._Element, name: str) -> list[etree._Element]:
    return [element for element in root if _local_name(element) == name]


def _normalize_style_name(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).replace("\ufffd", "")
    return " ".join(value.casefold().split())


def _direct_character_style_name(value: str, position: str | None) -> str:
    """An explicit run position overrides script hints in the applied style's name.

    Only the semantic name used by the mapper changes. The source style, parent,
    exact properties and text remain in the raw graph for audit. Unknown position
    modes retain the existing representation; this is not font/glyph substitution.
    """
    normalized = _normalize_style_name(value)
    explicit = (position or "").casefold()
    if explicit not in {"normal", "subscript", "superscript"}:
        return normalized
    normalized = re.sub(r"superscript|sobrescrito|subscript|subscrito", "", normalized)
    return " ".join((normalized + (" " + explicit if explicit != "normal" else "")).split())


def style_prefix(value: str) -> str | None:
    """Return the journal-controlled numeric prefix without trusting mojibake text."""
    match = _STYLE_PREFIX.match(value.strip())
    return match.group(1) if match else None


def _reference(value: str | None) -> str | None:
    return None if value is None or value in _NULL_REFERENCE else value


def _numbers(value: str | None, expected: int) -> tuple[float, ...]:
    if value is None:
        return (0.0,) * expected
    parts = tuple(float(item) for item in value.split())
    return parts if len(parts) == expected else (0.0,) * expected


def _content_value(element: etree._Element) -> str:
    return "".join(cast(str, item) for item in element.itertext())


def _page_interval_score(
    page_range: tuple[float, float],
    frame_left: float,
    frame_right: float,
    frame_center: float,
) -> tuple[bool, float, float]:
    page_left, page_right = page_range
    overlap = max(0.0, min(frame_right, page_right) - max(frame_left, page_left))
    distance = abs(frame_center - ((page_left + page_right) / 2))
    return overlap > 0, overlap, -distance


_Affine = tuple[float, float, float, float, float, float]
_IDENTITY: _Affine = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def _compose(outer: _Affine, inner: _Affine) -> _Affine:
    """Return the affine map applying ``inner`` first, then ``outer`` (IDML row vectors)."""
    a, b, c, d, e, f = inner
    oa, ob, oc, od, oe, of = outer
    return (
        a * oa + b * oc,
        a * ob + b * od,
        c * oa + d * oc,
        c * ob + d * od,
        e * oa + f * oc + oe,
        e * ob + f * od + of,
    )


def _affine(value: str | None) -> _Affine:
    parts = _numbers(value, 6)
    return _IDENTITY if parts == (0.0,) * 6 else cast(_Affine, parts)


def _spread_box(
    element: etree._Element, spread: etree._Element
) -> tuple[float, float, float, float] | None:
    """Bounding box of an item in spread coordinates, composing every ancestor transform."""
    transform = _affine(element.get("ItemTransform"))
    for ancestor in element.iterancestors():
        if ancestor is spread:
            break
        if "ItemTransform" in ancestor.attrib:
            transform = _compose(_affine(ancestor.get("ItemTransform")), transform)
    points = [_numbers(item.get("Anchor"), 2) for item in _elements(element, "PathPointType")]
    if not points:
        return None
    a, b, c, d, e, f = transform
    xs = [a * x + c * y + e for x, y in points]
    ys = [b * x + d * y + f for x, y in points]
    return min(xs), min(ys), max(xs), max(ys)


def _page_box(page: etree._Element) -> tuple[float, float, float, float]:
    top, left, bottom, right = _numbers(page.get("GeometricBounds"), 4)
    a, b, c, d, e, f = _affine(page.get("ItemTransform"))
    xs = [a * x + c * y + e for x, y in ((left, top), (right, bottom))]
    ys = [b * x + d * y + f for x, y in ((left, top), (right, bottom))]
    return min(xs), min(ys), max(xs), max(ys)


def _off_all_pages(
    box: tuple[float, float, float, float] | None,
    pages: list[tuple[float, float, float, float]],
) -> bool:
    """True only when the item has area and touches no page (a pasteboard leftover).

    Pages without usable bounds make the decision unknown, so nothing is excluded.
    """
    pages = [page for page in pages if page[2] - page[0] > 0 and page[3] - page[1] > 0]
    if box is None or not pages:
        return False
    x0, y0, x1, y1 = box
    if x1 - x0 <= 0 or y1 - y0 <= 0:
        return False
    return all(
        min(x1, px1) - max(x0, px0) <= 0 or min(y1, py1) - max(y0, py0) <= 0
        for px0, py0, px1, py1 in pages
    )


def _sanitized_asset_name(uri: str) -> str:
    parsed = urlparse(uri)
    candidate = PurePosixPath(unquote(parsed.path.replace("\\", "/"))).name
    candidate = "".join(ch for ch in candidate if ch.isprintable() and ch not in {"/", "\\"})
    return candidate[:255] or "unnamed-asset"


def _media_type(name: str, resource_format: str | None) -> str:
    guessed = mimetypes.guess_type(name)[0]
    if guessed:
        return guessed
    normalized = (resource_format or "").casefold()
    if "pdf" in normalized or "portable document" in normalized:
        return "application/pdf"
    return "application/octet-stream"


def _anchored_object_kind(name: str, media_type: str) -> RawObjectKind:
    """Classify linked artwork without assuming that every PDF is a formula."""
    if figure_asset_number(name) is not None:
        return RawObjectKind.FIGURE
    if media_type == "application/pdf":
        return RawObjectKind.FORMULA
    return RawObjectKind.UNKNOWN


def _text_of_range(element: etree._Element) -> str:
    pieces: list[str] = []
    range_is_table_cell = any(_local_name(item) == "Cell" for item in element.iterancestors())
    range_is_note = any(
        _local_name(item) in {"Note", "Footnote"} for item in element.iterancestors()
    )

    def nested_below(descendant: etree._Element, name: str) -> bool:
        for ancestor in descendant.iterancestors():
            if ancestor is element:
                return False
            if _local_name(ancestor) == name:
                return True
        return False

    for descendant in element.iter():
        name = _local_name(descendant)
        if (not range_is_table_cell and nested_below(descendant, "Table")) or (
            not range_is_note
            and any(nested_below(descendant, note_name) for note_name in ("Note", "Footnote"))
        ):
            continue
        if name == "Content":
            if nested_below(descendant, "TextVariableInstance"):
                continue
            pieces.append(_content_value(descendant))
        elif name == "Br":
            pieces.append("\n")
        elif name == "TextVariableInstance":
            result = descendant.get("ResultText")
            if result:
                pieces.append(result)
    return "".join(pieces)


@dataclass(frozen=True)
class _RangeEvent:
    kind: str
    value: str
    hyperlink_source_id: str | None = None


def _range_events(
    element: etree._Element,
    hyperlink_targets: dict[str, str] | None = None,
) -> list[_RangeEvent]:
    events: list[_RangeEvent] = []
    range_is_table_cell = any(_local_name(item) == "Cell" for item in element.iterancestors())
    range_is_note = any(
        _local_name(item) in {"Note", "Footnote"} for item in element.iterancestors()
    )

    def nested_below(descendant: etree._Element, name: str) -> bool:
        for ancestor in descendant.iterancestors():
            if ancestor is element:
                return False
            if _local_name(ancestor) == name:
                return True
        return False

    def hyperlink_source_id(descendant: etree._Element) -> str | None:
        return next(
            (
                ancestor.get("Self")
                for ancestor in descendant.iterancestors()
                if _local_name(ancestor) == "HyperlinkTextSource" and ancestor.get("Self")
            ),
            None,
        )

    for descendant in element.iter():
        name = _local_name(descendant)
        if (not range_is_table_cell and nested_below(descendant, "Table")) or (
            not range_is_note
            and any(nested_below(descendant, note_name) for note_name in ("Note", "Footnote"))
        ):
            continue
        if name == "Content":
            if nested_below(descendant, "TextVariableInstance"):
                continue
            events.append(
                _RangeEvent(
                    kind="text",
                    value=_content_value(descendant),
                    hyperlink_source_id=hyperlink_source_id(descendant),
                )
            )
        elif name == "Br":
            events.append(
                _RangeEvent(
                    kind="text",
                    value="\n",
                    hyperlink_source_id=hyperlink_source_id(descendant),
                )
            )
        elif name == "TextVariableInstance":
            if result := descendant.get("ResultText"):
                events.append(
                    _RangeEvent(
                        kind="text",
                        value=result,
                        hyperlink_source_id=hyperlink_source_id(descendant),
                    )
                )
        elif name == "Link" and (link_self := descendant.get("Self")):
            events.append(_RangeEvent(kind="asset_link", value=link_self))
        elif name == "TextFrame" and (parent_story := descendant.get("ParentStory")):
            events.append(_RangeEvent(kind="embedded_story", value=parent_story))
        elif (
            name in {"Rectangle", "Oval", "Polygon", "GraphicLine", "Group"}
            and (page_item_self := descendant.get("Self"))
            and page_item_self in (hyperlink_targets or {})
        ):
            events.append(_RangeEvent(kind="hyperlink_page_item", value=page_item_self))
    return events


def _anchor_context(
    events: list[_RangeEvent],
    position: int,
) -> tuple[AnchoredPlacement, str | None]:
    left = ""
    for event in reversed(events[:position]):
        if event.kind != "text":
            break
        left = event.value + left
        if "\n" in event.value:
            left = left.rsplit("\n", maxsplit=1)[-1]
            break
    right = ""
    for event in events[position + 1 :]:
        if event.kind != "text":
            break
        right += event.value
        if "\n" in event.value:
            right = right.split("\n", maxsplit=1)[0]
            break
    label_match = re.fullmatch(r"\s*(\(\d+\))\s*", right)
    if not left.strip() and (not right.strip() or label_match):
        return AnchoredPlacement.BLOCK, label_match.group(1) if label_match else None
    return AnchoredPlacement.INLINE, None


@dataclass(frozen=True)
class _StoryResult:
    story: RawStory
    styles: tuple[RawStyle, ...]
    tables: tuple[RawTable, ...]
    notes: tuple[RawNote, ...]
    objects: tuple[RawAnchoredObject, ...]
    assets: tuple[RawAsset, ...]
    links: tuple[RawLink, ...]
    evidence: tuple[Evidence, ...]


@dataclass(frozen=True)
class _LayoutResult:
    frames: tuple[RawTextFrame, ...]
    spreads: tuple[RawSpread, ...]
    objects: tuple[RawAnchoredObject, ...]
    assets: tuple[RawAsset, ...]
    links: tuple[RawLink, ...]
    evidence: tuple[Evidence, ...]
    pasteboard_frame_ids: frozenset[str] = frozenset()


class IdmlParser:
    """Parse an untrusted IDML package into the loss-aware Raw Article model."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()

    def parse(self, data: bytes, *, logical_name: str) -> RawArticle:
        inspect_idml(data, self.settings)
        artifact_sha = hashlib.sha256(data).hexdigest()
        article_key = PurePosixPath(logical_name.replace("\\", "/")).stem

        try:
            with ZipFile(BytesIO(data)) as archive:
                budget = XmlComplexityBudget()
                roots = {
                    name: parse_untrusted_xml(archive.read(name), budget=budget)
                    for name in archive.namelist()
                    if name.casefold().endswith(".xml")
                }
        except UnsafeXmlError as exc:
            raise UnsafeArchiveError("unsafe_xml", "IDML contains malformed or unsafe XML") from exc

        design = roots["designmap.xml"]
        document_self_id = design.get("Self", "document")
        hyperlink_targets = self._hyperlink_targets(roots)
        try:
            styles, style_evidence = self._parse_styles(roots, article_key, artifact_sha)
            story_results = [
                self._parse_story(
                    path,
                    root,
                    article_key,
                    artifact_sha,
                    hyperlink_targets,
                )
                for path, root in sorted(roots.items())
                if path.startswith("Stories/")
            ]
            layout = self._parse_layout(roots, article_key, artifact_sha)
        except (IndexError, StopIteration, TypeError, ValueError) as exc:
            raise UnsafeArchiveError(
                "invalid_idml_structure", "IDML contains invalid internal structure"
            ) from exc
        discovered_styles = styles + tuple(
            style for result in story_results for style in result.styles
        )
        unique_styles: dict[str, RawStyle] = {}
        for style in discovered_styles:
            unique_styles.setdefault(style.id, style)
        styles = tuple(unique_styles.values())
        known_style_ids = {style.id for style in styles}
        styles = tuple(
            style.model_copy(
                update={
                    "parent_style_id": (
                        style.parent_style_id if style.parent_style_id in known_style_ids else None
                    )
                }
            )
            for style in styles
        )
        frames, spreads = layout.frames, layout.spreads
        frames_per_story: defaultdict[str, set[str]] = defaultdict(set)
        for frame in frames:
            frames_per_story[frame.parent_story_id].add(frame.id)
        pasteboard_story_ids = {
            story_id
            for story_id, frame_ids in frames_per_story.items()
            if frame_ids and frame_ids <= layout.pasteboard_frame_ids
        }
        pasteboard_issues = [
            ReadingOrderIssue(
                code="pasteboard_story_excluded",
                story_id=result.story.id,
                details={"source_story_id": result.story.source_self_id},
            )
            for result in story_results
            if result.story.id in pasteboard_story_ids
        ]
        # Content of pasteboard stories is dropped; their evidence stays for audit.
        pasteboard_evidence = [
            item
            for result in story_results
            if result.story.id in pasteboard_story_ids
            for item in result.evidence
        ]
        story_results = [
            result for result in story_results if result.story.id not in pasteboard_story_ids
        ]
        frames = tuple(
            frame for frame in frames if frame.parent_story_id not in pasteboard_story_ids
        )
        stories = tuple(result.story for result in story_results)
        story_by_source_self = {story.source_self_id: story for story in stories}
        style_by_id = {style.id: style for style in styles}

        def is_embedded_formula_story(source_self_id: str) -> bool:
            embedded_story = story_by_source_self.get(source_self_id)
            if embedded_story is None:
                return False
            value = "".join(run.text for run in embedded_story.runs).strip()
            if not value or len(value) > 64:
                return False
            return any(
                str(style_by_id[run.character_style_id].properties.get("Position", "")).casefold()
                in {"subscript", "superscript"}
                for run in embedded_story.runs
                if run.character_style_id in style_by_id
            )

        story_objects = tuple(item for result in story_results for item in result.objects)
        story_objects = tuple(
            item.model_copy(update={"kind": RawObjectKind.FORMULA})
            if item.kind == RawObjectKind.UNKNOWN
            and not item.asset_ids
            and is_embedded_formula_story(item.source_self_id)
            else item
            for item in story_objects
        )
        known_story_ids = {story.id for story in stories}
        reference_issues: list[ReadingOrderIssue] = []
        for frame in frames:
            if frame.parent_story_id not in known_story_ids:
                reference_issues.append(
                    ReadingOrderIssue(
                        code="frame_parent_story_missing",
                        details={"source_frame_id": frame.source_self_id},
                        evidence_ids=frame.evidence_ids,
                    )
                )
        frames = tuple(frame for frame in frames if frame.parent_story_id in known_story_ids)
        known_frame_ids = {frame.id for frame in frames}
        for frame in frames:
            for direction, reference in (
                ("previous", frame.previous_frame_id),
                ("next", frame.next_frame_id),
            ):
                if reference and reference not in known_frame_ids:
                    reference_issues.append(
                        ReadingOrderIssue(
                            code="frame_thread_reference_missing",
                            story_id=frame.parent_story_id,
                            frame_id=frame.id,
                            details={"direction": direction},
                            evidence_ids=frame.evidence_ids,
                        )
                    )
        frames = tuple(
            frame.model_copy(
                update={
                    "previous_frame_id": (
                        frame.previous_frame_id
                        if frame.previous_frame_id in known_frame_ids
                        else None
                    ),
                    "next_frame_id": (
                        frame.next_frame_id if frame.next_frame_id in known_frame_ids else None
                    ),
                }
            )
            for frame in frames
        )
        spreads = tuple(
            spread.model_copy(
                update={
                    "frame_ids": tuple(
                        frame_id for frame_id in spread.frame_ids if frame_id in known_frame_ids
                    )
                }
            )
            for spread in spreads
        )
        order, issues = self._reading_order(
            stories,
            frames,
            tuple(design.get("StoryList", "").split()),
        )
        issues = tuple(pasteboard_issues) + tuple(reference_issues) + issues

        try:
            return RawArticle(
                article_id=article_key,
                source_artifact_sha256=artifact_sha,
                document_self_id=document_self_id,
                adobe_dom_version=design.get("DOMVersion"),
                stories=stories,
                frames=frames,
                spreads=spreads,
                styles=styles,
                tables=tuple(table for result in story_results for table in result.tables),
                anchored_objects=story_objects + layout.objects,
                assets=tuple(asset for result in story_results for asset in result.assets)
                + layout.assets,
                links=tuple(link for result in story_results for link in result.links)
                + layout.links,
                notes=tuple(note for result in story_results for note in result.notes),
                reading_order=order,
                reading_order_issues=issues,
                evidence=tuple(
                    [*style_evidence, *layout.evidence]
                    + [item for result in story_results for item in result.evidence]
                    + pasteboard_evidence
                ),
            )
        except ValueError as exc:
            raise UnsafeArchiveError(
                "invalid_idml_structure", "IDML contains an inconsistent internal graph"
            ) from exc

    def _evidence(
        self,
        article_key: str,
        artifact_sha: str,
        logical_path: str,
        element_id: str,
        description: str,
    ) -> Evidence:
        evidence_id = stable_id(article_key, "evidence", f"{logical_path}#{element_id}")
        return Evidence(
            id=evidence_id,
            source_kind=SourceKind.IDML,
            locator=EvidenceLocator(
                artifact_sha256=artifact_sha,
                logical_path=logical_path,
                element_id=element_id,
            ),
            description=description,
        )

    def _parse_styles(
        self,
        roots: dict[str, etree._Element],
        article_key: str,
        artifact_sha: str,
    ) -> tuple[tuple[RawStyle, ...], tuple[Evidence, ...]]:
        kind_by_name = {
            "ParagraphStyle": StyleKind.PARAGRAPH,
            "CharacterStyle": StyleKind.CHARACTER,
            "TableStyle": StyleKind.TABLE,
            "CellStyle": StyleKind.CELL,
        }
        styles: list[RawStyle] = []
        evidence: list[Evidence] = []
        for path, root in sorted(roots.items()):
            if not path.startswith("Resources/"):
                continue
            for element in root.iter():
                kind = kind_by_name.get(_local_name(element))
                source_self = element.get("Self")
                if kind is None or source_self is None:
                    continue
                source_name = element.get("Name", source_self.rsplit("/", 1)[-1])
                evidence_item = self._evidence(
                    article_key, artifact_sha, path, source_self, "IDML style definition"
                )
                evidence.append(evidence_item)
                parent = next(
                    (
                        child.text
                        for child in element.iter()
                        if _local_name(child) == "BasedOn" and child.text
                    ),
                    None,
                )
                properties: dict[str, str | int | float | bool | None] = {}
                prefix = style_prefix(source_name)
                if prefix:
                    properties["journal_prefix"] = prefix
                for key in ("FontStyle", "Position", "PointSize"):
                    if key in element.attrib:
                        properties[key] = cast(str, element.attrib[key])
                styles.append(
                    RawStyle(
                        id=stable_id(article_key, "style", source_self),
                        source_name=source_name,
                        normalized_name=_normalize_style_name(source_name),
                        kind=kind,
                        parent_style_id=(
                            stable_id(article_key, "style", parent) if parent else None
                        ),
                        properties=properties,
                        evidence_ids=(evidence_item.id,),
                    )
                )
        known = {item.id for item in styles}
        styles = [
            item.model_copy(
                update={
                    "parent_style_id": (
                        item.parent_style_id if item.parent_style_id in known else None
                    )
                }
            )
            for item in styles
        ]
        return tuple(styles), tuple(evidence)

    def _hyperlink_targets(self, roots: dict[str, etree._Element]) -> dict[str, str]:
        destination_by_key = {
            element.get("DestinationUniqueKey", ""): element.get("DestinationURL", "")
            for root in roots.values()
            for element in _elements(root, "HyperlinkURLDestination")
            if element.get("DestinationUniqueKey") and element.get("DestinationURL")
        }
        source_page_items = {
            element.get("Self", ""): element.get("SourcePageItem", "")
            for root in roots.values()
            for element in _elements(root, "HyperlinkPageItemSource")
            if element.get("Self") and element.get("SourcePageItem")
        }
        targets = {
            source: destination_by_key[key]
            for root in roots.values()
            for element in _elements(root, "Hyperlink")
            if (source := element.get("Source"))
            and (key := element.get("DestinationUniqueKey")) in destination_by_key
        }
        targets.update(
            {
                page_item: targets[source]
                for source, page_item in source_page_items.items()
                if source in targets
            }
        )
        return targets

    def _parse_story(
        self,
        path: str,
        root: etree._Element,
        article_key: str,
        artifact_sha: str,
        hyperlink_targets: dict[str, str],
    ) -> _StoryResult:
        story_element = next(element for element in _elements(root, "Story") if element.get("Self"))
        source_self = story_element.get("Self", PurePosixPath(path).stem)
        story_id = stable_id(article_key, "story", source_self)
        story_evidence = self._evidence(article_key, artifact_sha, path, source_self, "IDML story")
        evidence: list[Evidence] = [story_evidence]
        runs: list[RawTextRun] = []
        paragraphs: list[RawParagraph] = []
        override_styles: list[RawStyle] = []
        unresolved_styles: list[RawStyle] = []
        unresolved_style_ids: set[str] = set()
        run_ids_by_cell: defaultdict[str, list[str]] = defaultdict(list)
        run_ids_by_note: defaultdict[str, list[str]] = defaultdict(list)
        hyperlink_run_ids: defaultdict[str, list[str]] = defaultdict(list)
        anchor_run_by_link: dict[str, str] = {}
        anchor_placement_by_link: dict[str, AnchoredPlacement] = {}
        anchor_label_by_link: dict[str, str] = {}
        embedded_story_evidence: dict[str, tuple[str, ...]] = {}
        note_elements = [
            element
            for element in story_element.iter()
            if _local_name(element) in {"Note", "Footnote"}
        ]
        note_key_by_element = {
            element: element.get("Self", f"{source_self}:note:{position}")
            for position, element in enumerate(note_elements)
        }
        override_style_by_element: dict[etree._Element, str] = {}

        def ensure_source_style(
            source_style: str | None,
            kind: StyleKind,
            source_evidence: Evidence,
        ) -> str | None:
            if source_style is None:
                return None
            style_id = stable_id(article_key, "style", source_style)
            if style_id not in unresolved_style_ids:
                unresolved_style_ids.add(style_id)
                source_name = source_style.rsplit("/", 1)[-1]
                unresolved_styles.append(
                    RawStyle(
                        id=style_id,
                        source_name=source_name,
                        normalized_name=_normalize_style_name(source_name),
                        kind=kind,
                        properties={"unresolved": True},
                        evidence_ids=(source_evidence.id,),
                    )
                )
            return style_id

        def cell_key(cell: etree._Element) -> str:
            table = next(
                (ancestor for ancestor in cell.iterancestors() if _local_name(ancestor) == "Table"),
                None,
            )
            table_self = table.get("Self", "table") if table is not None else "table"
            return f"{table_self}:{cell.get('Name', 'cell')}"

        paragraph_ranges = _elements(story_element, "ParagraphStyleRange")
        for paragraph_position, paragraph_range in enumerate(paragraph_ranges):
            paragraph_locator = f"{source_self}:paragraph:{paragraph_position}"
            paragraph_evidence = self._evidence(
                article_key, artifact_sha, path, paragraph_locator, "IDML paragraph range"
            )
            evidence.append(paragraph_evidence)
            paragraph_style = paragraph_range.get("AppliedParagraphStyle")
            paragraph_style_id = ensure_source_style(
                paragraph_style,
                StyleKind.PARAGRAPH,
                paragraph_evidence,
            )
            paragraph_properties = {
                cast(str, key): cast(str, value)
                for key, value in paragraph_range.attrib.items()
                if key != "AppliedParagraphStyle"
            }
            if paragraph_properties:
                paragraph_override_source = (
                    f"{source_self}:paragraph:{paragraph_position}:paragraph-style"
                )
                paragraph_style_id = stable_id(
                    article_key, "inline-paragraph-style", paragraph_override_source
                )
                base_name = (
                    paragraph_style.rsplit("/", 1)[-1] if paragraph_style else "missing-style"
                )
                override_styles.append(
                    RawStyle(
                        id=paragraph_style_id,
                        source_name=f"{base_name}{DIRECT_PARAGRAPH_SUFFIX}",
                        normalized_name=_normalize_style_name(
                            " ".join((paragraph_style or "", *paragraph_properties.values()))
                        ),
                        kind=StyleKind.PARAGRAPH,
                        parent_style_id=(
                            stable_id(article_key, "style", paragraph_style)
                            if paragraph_style
                            else None
                        ),
                        properties=paragraph_properties,
                        evidence_ids=(paragraph_evidence.id,),
                    )
                )
            paragraph_run_ids: list[str] = []
            cell = next(
                (
                    ancestor
                    for ancestor in paragraph_range.iterancestors()
                    if _local_name(ancestor) == "Cell"
                ),
                None,
            )
            note = next(
                (
                    ancestor
                    for ancestor in paragraph_range.iterancestors()
                    if _local_name(ancestor) in {"Note", "Footnote"}
                ),
                None,
            )
            character_ranges: list[etree._Element] = []
            for child in paragraph_range:
                if _local_name(child) == "CharacterStyleRange":
                    character_ranges.append(child)
                elif _local_name(child) == "HyperlinkTextSource":
                    nested_ranges = _direct_elements(child, "CharacterStyleRange")
                    character_ranges.extend(nested_ranges or [child])
            range_events = [
                (character_range, _range_events(character_range, hyperlink_targets))
                for character_range in character_ranges
            ]
            paragraph_events = [event for _, events in range_events for event in events]
            for event_position, event in enumerate(paragraph_events):
                if event.kind not in {"asset_link", "embedded_story"}:
                    continue
                placement, label = _anchor_context(paragraph_events, event_position)
                anchor_placement_by_link[event.value] = placement
                if label is not None:
                    anchor_label_by_link[event.value] = label
                if event.kind == "embedded_story":
                    embedded_story_evidence[event.value] = (paragraph_evidence.id,)

            def character_style_id(
                character_range: etree._Element,
                paragraph_position: int = paragraph_position,
                paragraph_evidence: Evidence = paragraph_evidence,
            ) -> str | None:
                base_style = character_range.get("AppliedCharacterStyle")
                base_style_id = ensure_source_style(
                    base_style,
                    StyleKind.CHARACTER,
                    paragraph_evidence,
                )
                properties = {
                    cast(str, key): cast(str, value)
                    for key, value in character_range.attrib.items()
                    if key != "AppliedCharacterStyle"
                }
                if not properties:
                    return base_style_id
                if character_range in override_style_by_element:
                    return override_style_by_element[character_range]
                source_override_id = (
                    f"{source_self}:paragraph:{paragraph_position}:"
                    f"inline-style:{len(override_styles)}"
                )
                override_id = stable_id(article_key, "inline-style", source_override_id)
                override_style_by_element[character_range] = override_id
                override_styles.append(
                    RawStyle(
                        id=override_id,
                        source_name=source_override_id,
                        normalized_name=_direct_character_style_name(
                            " ".join((base_style or "", *properties.values())),
                            character_range.get("Position"),
                        ),
                        kind=StyleKind.CHARACTER,
                        parent_style_id=(base_style_id),
                        properties=properties,
                        evidence_ids=(paragraph_evidence.id,),
                    )
                )
                return override_id

            def append_run(
                text: str,
                character_range: etree._Element,
                *,
                anchor_link_self: str | None = None,
                hyperlink_source_id: str | None = None,
                paragraph_style_id: str | None = paragraph_style_id,
                paragraph_evidence: Evidence = paragraph_evidence,
                paragraph_run_ids: list[str] = paragraph_run_ids,
                cell: etree._Element | None = cell,
                note: etree._Element | None = note,
            ) -> None:
                position = len(runs)
                run_id = stable_id(article_key, "run", f"{source_self}:{position}")
                runs.append(
                    RawTextRun(
                        id=run_id,
                        text=text,
                        paragraph_style_id=paragraph_style_id,
                        character_style_id=character_style_id(character_range),
                        position=position,
                        evidence_ids=(paragraph_evidence.id,),
                    )
                )
                paragraph_run_ids.append(run_id)
                if cell is not None:
                    run_ids_by_cell[cell_key(cell)].append(run_id)
                if note is not None:
                    run_ids_by_note[note_key_by_element[note]].append(run_id)
                if hyperlink_source_id is not None:
                    hyperlink_run_ids[hyperlink_source_id].append(run_id)
                if anchor_link_self is not None:
                    anchor_run_by_link[anchor_link_self] = run_id

            for character_range, events in range_events:
                buffered_text = ""
                buffered_hyperlink_source_id: str | None = None
                pending_label: str | None = None
                for event in events:
                    if event.kind == "text":
                        if (
                            buffered_text
                            and buffered_hyperlink_source_id != event.hyperlink_source_id
                        ):
                            append_run(
                                buffered_text,
                                character_range,
                                hyperlink_source_id=buffered_hyperlink_source_id,
                            )
                            buffered_text = ""
                        if pending_label is not None:
                            value = re.sub(
                                rf"^\s*{re.escape(pending_label)}\s*",
                                "",
                                event.value,
                                count=1,
                            )
                            pending_label = None
                        else:
                            value = event.value
                        buffered_text += value
                        buffered_hyperlink_source_id = event.hyperlink_source_id
                        continue
                    if buffered_text:
                        append_run(
                            buffered_text,
                            character_range,
                            hyperlink_source_id=buffered_hyperlink_source_id,
                        )
                        buffered_text = ""
                        buffered_hyperlink_source_id = None
                    if event.kind == "hyperlink_page_item":
                        append_run(
                            "",
                            character_range,
                            hyperlink_source_id=event.value,
                        )
                        continue
                    append_run("", character_range, anchor_link_self=event.value)
                    pending_label = anchor_label_by_link.get(event.value)
                if buffered_text:
                    append_run(
                        buffered_text,
                        character_range,
                        hyperlink_source_id=buffered_hyperlink_source_id,
                    )
            paragraph_id = stable_id(article_key, "paragraph", paragraph_locator)
            cell_id = (
                stable_id(
                    article_key,
                    "cell",
                    f"{source_self}:{cell_key(cell)}",
                )
                if cell is not None
                else None
            )
            if note is None:
                paragraphs.append(
                    RawParagraph(
                        id=paragraph_id,
                        position=paragraph_position,
                        paragraph_style_id=paragraph_style_id,
                        text_run_ids=tuple(paragraph_run_ids),
                        table_cell_id=cell_id,
                        evidence_ids=(paragraph_evidence.id,),
                    )
                )

        tables: list[RawTable] = []
        for table_position, table_element in enumerate(_elements(story_element, "Table")):
            source_table_id = table_element.get("Self", f"{source_self}:table:{table_position}")
            table_evidence = self._evidence(
                article_key, artifact_sha, path, source_table_id, "IDML table"
            )
            evidence.append(table_evidence)
            table_style_id = ensure_source_style(
                table_element.get("AppliedTableStyle"),
                StyleKind.TABLE,
                table_evidence,
            )
            cells: list[RawTableCell] = []
            max_row = max_column = 0
            for cell in _elements(table_element, "Cell"):
                coordinates = cell.get("Name", "0:0").split(":", 1)
                column, row = (int(value) for value in coordinates)
                row_span = int(cell.get("RowSpan", "1"))
                column_span = int(cell.get("ColumnSpan", "1"))
                max_row = max(max_row, row + row_span)
                max_column = max(max_column, column + column_span)
                cells.append(
                    RawTableCell(
                        id=stable_id(
                            article_key,
                            "cell",
                            f"{source_self}:{cell_key(cell)}",
                        ),
                        row=row,
                        column=column,
                        row_span=row_span,
                        column_span=column_span,
                        text_run_ids=tuple(run_ids_by_cell[cell_key(cell)]),
                        evidence_ids=(table_evidence.id,),
                    )
                )
            row_count = int(table_element.get("BodyRowCount", str(max_row or 1)))
            row_count += int(table_element.get("HeaderRowCount", "0"))
            row_count += int(table_element.get("FooterRowCount", "0"))
            column_count = int(table_element.get("ColumnCount", str(max_column or 1)))
            tables.append(
                RawTable(
                    id=stable_id(article_key, "table", source_table_id),
                    source_self_id=source_table_id,
                    row_count=max(row_count, max_row, 1),
                    column_count=max(column_count, max_column, 1),
                    cells=tuple(cells),
                    style_id=table_style_id,
                    evidence_ids=(table_evidence.id,),
                )
            )

        assets: list[RawAsset] = []
        links: list[RawLink] = []
        objects: list[RawAnchoredObject] = []
        for link_position, link in enumerate(_elements(story_element, "Link")):
            link_self = link.get("Self", f"{source_self}:link:{link_position}")
            name = _sanitized_asset_name(link.get("LinkResourceURI", ""))
            media_type = _media_type(name, link.get("LinkResourceFormat"))
            explicit_formula_placement = equation_asset_placement(name)
            asset_id = stable_id(article_key, "asset", link_self)
            link_evidence = self._evidence(
                article_key, artifact_sha, path, link_self, "Sanitized external asset link"
            )
            evidence.append(link_evidence)
            assets.append(
                RawAsset(
                    id=asset_id,
                    logical_path=name,
                    media_type=media_type,
                    external=True,
                    evidence_ids=(link_evidence.id,),
                )
            )
            links.append(
                RawLink(
                    id=stable_id(article_key, "link", link_self),
                    source_id=story_id,
                    target=asset_id,
                    relationship="external-asset",
                    evidence_ids=(link_evidence.id,),
                )
            )
            objects.append(
                RawAnchoredObject(
                    id=stable_id(article_key, "object", link_self),
                    source_self_id=link_self,
                    kind=_anchored_object_kind(name, media_type),
                    placement=(
                        AnchoredPlacement(explicit_formula_placement)
                        if explicit_formula_placement is not None
                        else anchor_placement_by_link.get(
                            link_self,
                            AnchoredPlacement.UNKNOWN,
                        )
                    ),
                    label=anchor_label_by_link.get(link_self),
                    anchor_run_id=anchor_run_by_link.get(link_self),
                    asset_ids=(asset_id,),
                    evidence_ids=(link_evidence.id,),
                )
            )

        for embedded_story_self, evidence_ids in sorted(embedded_story_evidence.items()):
            objects.append(
                RawAnchoredObject(
                    id=stable_id(article_key, "object", embedded_story_self),
                    source_self_id=embedded_story_self,
                    kind=RawObjectKind.UNKNOWN,
                    placement=anchor_placement_by_link.get(
                        embedded_story_self,
                        AnchoredPlacement.UNKNOWN,
                    ),
                    label=anchor_label_by_link.get(embedded_story_self),
                    anchor_run_id=anchor_run_by_link.get(embedded_story_self),
                    evidence_ids=evidence_ids,
                )
            )

        run_by_id = {run.id: run for run in runs}
        for hyperlink_source_id, run_ids in sorted(hyperlink_run_ids.items()):
            target = hyperlink_targets.get(hyperlink_source_id)
            if target is None:
                continue
            for run_id in run_ids:
                links.append(
                    RawLink(
                        id=stable_id(article_key, "hyperlink", run_id),
                        source_id=run_id,
                        target=target,
                        relationship="external-hyperlink",
                        evidence_ids=run_by_id[run_id].evidence_ids,
                    )
                )

        notes: list[RawNote] = []
        for note_element in note_elements:
            note_key = note_key_by_element[note_element]
            note_evidence = self._evidence(
                article_key, artifact_sha, path, note_key, "IDML note or footnote"
            )
            evidence.append(note_evidence)
            notes.append(
                RawNote(
                    id=stable_id(article_key, "note", note_key),
                    source_self_id=note_key,
                    text_run_ids=tuple(run_ids_by_note[note_key]),
                    evidence_ids=(note_evidence.id,),
                )
            )

        return _StoryResult(
            story=RawStory(
                id=story_id,
                source_self_id=source_self,
                runs=tuple(runs),
                paragraphs=tuple(paragraphs),
                table_ids=tuple(item.id for item in tables),
                anchored_object_ids=tuple(item.id for item in objects),
                note_ids=tuple(item.id for item in notes),
                evidence_ids=(story_evidence.id,),
            ),
            styles=tuple((*unresolved_styles, *override_styles)),
            tables=tuple(tables),
            notes=tuple(notes),
            objects=tuple(objects),
            assets=tuple(assets),
            links=tuple(links),
            evidence=tuple(evidence),
        )

    def _parse_layout(
        self,
        roots: dict[str, etree._Element],
        article_key: str,
        artifact_sha: str,
    ) -> _LayoutResult:
        frames: list[RawTextFrame] = []
        spreads: list[RawSpread] = []
        objects: list[RawAnchoredObject] = []
        assets: list[RawAsset] = []
        links: list[RawLink] = []
        evidence: list[Evidence] = []
        pasteboard_frames: set[str] = set()
        page_counter = 0
        referenced_paths = [
            normalized_source
            for element in _elements(roots["designmap.xml"], "Spread")
            if (source := element.get("src"))
            and (normalized_source := source.replace("\\", "/")) in roots
        ]
        remaining_paths = sorted(
            path for path in roots if path.startswith("Spreads/") and path not in referenced_paths
        )
        for path in dict.fromkeys((*referenced_paths, *remaining_paths)):
            root = roots[path]
            spread_element = next(
                element for element in _elements(root, "Spread") if element.get("Self")
            )
            spread_self = spread_element.get("Self", PurePosixPath(path).stem)
            pages = _elements(spread_element, "Page")
            page_indices = tuple(range(page_counter, page_counter + len(pages)))
            page_ranges: list[tuple[float, float]] = []
            for page in pages:
                page_transform = _numbers(page.get("ItemTransform"), 6)
                page_bounds = _numbers(page.get("GeometricBounds"), 4)
                left = page_transform[4] + page_bounds[1]
                right = page_transform[4] + page_bounds[3]
                page_ranges.append((min(left, right), max(left, right)))
            page_counter += len(pages)
            page_boxes = [_page_box(page) for page in pages]
            spread_frame_ids: list[str] = []
            for frame_element in _elements(spread_element, "TextFrame"):
                source_self = frame_element.get("Self")
                parent_story = frame_element.get("ParentStory")
                if source_self is None or parent_story is None:
                    continue
                if _off_all_pages(_spread_box(frame_element, spread_element), page_boxes):
                    pasteboard_frames.add(stable_id(article_key, "frame", source_self))
                transform = _numbers(frame_element.get("ItemTransform"), 6)
                anchors = [
                    _numbers(item.get("Anchor"), 2)
                    for item in _elements(frame_element, "PathPointType")
                ]
                first = transform[4] + min((point[0] for point in anchors), default=0.0)
                second = transform[5] + min((point[1] for point in anchors), default=0.0)
                first_max = transform[4] + max((point[0] for point in anchors), default=0.0)
                second_max = transform[5] + max((point[1] for point in anchors), default=0.0)
                frame_left, frame_right = sorted((first, first_max))
                frame_center = (frame_left + frame_right) / 2

                local_page = max(
                    range(len(pages)),
                    key=lambda index: _page_interval_score(
                        page_ranges[index], frame_left, frame_right, frame_center
                    ),
                )
                page_index = page_indices[local_page]
                page_left, page_right = page_ranges[local_page]
                column_index = 0 if frame_center <= (page_left + page_right) / 2 else 1
                frame_evidence = self._evidence(
                    article_key, artifact_sha, path, source_self, "IDML text frame"
                )
                evidence.append(frame_evidence)
                frame_id = stable_id(article_key, "frame", source_self)
                spread_frame_ids.append(frame_id)
                frames.append(
                    RawTextFrame(
                        id=frame_id,
                        source_self_id=source_self,
                        parent_story_id=stable_id(article_key, "story", parent_story),
                        page_index=page_index,
                        box=BoundingBox(
                            x=first,
                            y=second,
                            width=max(0.0, first_max - first),
                            height=max(0.0, second_max - second),
                        ),
                        transform=transform,
                        previous_frame_id=(
                            stable_id(article_key, "frame", previous)
                            if (previous := _reference(frame_element.get("PreviousTextFrame")))
                            else None
                        ),
                        next_frame_id=(
                            stable_id(article_key, "frame", following)
                            if (following := _reference(frame_element.get("NextTextFrame")))
                            else None
                        ),
                        column_index=column_index,
                        evidence_ids=(frame_evidence.id,),
                    )
                )
            spread_evidence = self._evidence(
                article_key, artifact_sha, path, spread_self, "IDML spread"
            )
            evidence.append(spread_evidence)
            for link_position, link in enumerate(_elements(spread_element, "Link")):
                link_self = link.get("Self", f"{spread_self}:link:{link_position}")
                name = _sanitized_asset_name(link.get("LinkResourceURI", ""))
                asset_id = stable_id(article_key, "layout-asset", link_self)
                link_evidence = self._evidence(
                    article_key,
                    artifact_sha,
                    path,
                    link_self,
                    "Sanitized spread asset link",
                )
                evidence.append(link_evidence)
                media_type = _media_type(name, link.get("LinkResourceFormat"))
                assets.append(
                    RawAsset(
                        id=asset_id,
                        logical_path=name,
                        media_type=media_type,
                        external=True,
                        evidence_ids=(link_evidence.id,),
                    )
                )
                links.append(
                    RawLink(
                        id=stable_id(article_key, "layout-link", link_self),
                        source_id=stable_id(article_key, "spread", spread_self),
                        target=asset_id,
                        relationship="external-layout-asset",
                        evidence_ids=(link_evidence.id,),
                    )
                )
                objects.append(
                    RawAnchoredObject(
                        id=stable_id(article_key, "layout-object", link_self),
                        source_self_id=link_self,
                        kind=_anchored_object_kind(name, media_type),
                        asset_ids=(asset_id,),
                        page_index=page_indices[0] if page_indices else None,
                        evidence_ids=(link_evidence.id,),
                    )
                )
            spreads.append(
                RawSpread(
                    id=stable_id(article_key, "spread", spread_self),
                    source_self_id=spread_self,
                    page_indices=page_indices,
                    frame_ids=tuple(spread_frame_ids),
                    evidence_ids=(spread_evidence.id,),
                )
            )
        return _LayoutResult(
            frames=tuple(frames),
            spreads=tuple(spreads),
            objects=tuple(objects),
            assets=tuple(assets),
            links=tuple(links),
            evidence=tuple(evidence),
            pasteboard_frame_ids=frozenset(pasteboard_frames),
        )

    def _reading_order(
        self,
        stories: tuple[RawStory, ...],
        frames: tuple[RawTextFrame, ...],
        story_list: tuple[str, ...],
    ) -> tuple[tuple[str, ...], tuple[ReadingOrderIssue, ...]]:
        frames_by_story: defaultdict[str, list[RawTextFrame]] = defaultdict(list)
        for frame in frames:
            frames_by_story[frame.parent_story_id].append(frame)
        source_hint = {source_id: index for index, source_id in enumerate(story_list)}
        issues: list[ReadingOrderIssue] = []
        known_source_story_ids = {story.source_self_id for story in stories}
        issues.extend(
            ReadingOrderIssue(
                code="story_list_reference_missing",
                details={"source_story_id": source_story_id},
            )
            for source_story_id in story_list
            if source_story_id not in known_source_story_ids
        )
        first_positions: dict[str, tuple[int, int, float, float, int]] = {}
        for story in stories:
            story_frames = frames_by_story[story.id]
            starts = [item for item in story_frames if item.previous_frame_id is None]
            if not story_frames:
                issues.append(ReadingOrderIssue(code="story_without_frame", story_id=story.id))
                first_positions[story.id] = (
                    10**9,
                    10**9,
                    0.0,
                    0.0,
                    source_hint.get(story.source_self_id, 10**9),
                )
                continue
            if len(starts) != 1:
                issues.append(
                    ReadingOrderIssue(
                        code="invalid_thread_start_count",
                        story_id=story.id,
                        details={"start_count": len(starts)},
                    )
                )
            frame_by_id = {frame.id: frame for frame in story_frames}
            for frame in story_frames:
                if frame.next_frame_id:
                    following = frame_by_id.get(frame.next_frame_id)
                    if following is None or following.previous_frame_id != frame.id:
                        issues.append(
                            ReadingOrderIssue(
                                code="non_reciprocal_thread_link",
                                story_id=story.id,
                                frame_id=frame.id,
                            )
                        )
            visited: set[str] = set()
            cursor = starts[0] if len(starts) == 1 else None
            while cursor is not None and cursor.id not in visited:
                visited.add(cursor.id)
                cursor = frame_by_id.get(cursor.next_frame_id or "")
            if cursor is not None:
                issues.append(
                    ReadingOrderIssue(
                        code="thread_cycle",
                        story_id=story.id,
                        frame_id=cursor.id,
                    )
                )
            if len(starts) == 1 and len(visited) != len(story_frames):
                issues.append(
                    ReadingOrderIssue(
                        code="thread_disconnected",
                        story_id=story.id,
                        details={
                            "visited_frames": len(visited),
                            "story_frames": len(story_frames),
                        },
                    )
                )
            first = min(
                starts or story_frames,
                key=lambda item: (item.page_index, item.box.y, item.box.x),
            )
            first_positions[story.id] = (
                first.page_index,
                first.column_index or 0,
                first.box.y,
                first.box.x,
                source_hint.get(story.source_self_id, 10**9),
            )
        ordered = tuple(sorted((story.id for story in stories), key=first_positions.__getitem__))
        return ordered, tuple(issues)
