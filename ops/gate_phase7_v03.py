"""Execute the content-free V-03 IDML reading and fidelity gate."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from lxml import etree

from idml_foundation.domain.raw import RawArticle, RawObjectKind, StyleKind
from idml_foundation.pipeline.idml_parser import IdmlParser
from idml_foundation.pipeline.service import DeterministicPipeline

sys.path.insert(0, str(Path(__file__).parents[1]))
from tests.test_idml_fidelity_v03 import fidelity_idml


def local_name(element: etree._Element) -> str:
    return etree.QName(element).localname if isinstance(element.tag, str) else ""


def elements(root: etree._Element, name: str) -> list[etree._Element]:
    return [element for element in root.iter() if local_name(element) == name]


def nested_below(descendant: etree._Element, boundary: etree._Element, names: set[str]) -> bool:
    for ancestor in descendant.iterancestors():
        if ancestor is boundary:
            return False
        if local_name(ancestor) in names:
            return True
    return False


def visible_text(container: etree._Element) -> str:
    pieces: list[str] = []
    inside_table = any(local_name(item) == "Cell" for item in container.iterancestors())
    inside_note = any(
        local_name(item) in {"Note", "Footnote"} for item in container.iterancestors()
    )
    for descendant in container.iter():
        if (not inside_table and nested_below(descendant, container, {"Table"})) or (
            not inside_note and nested_below(descendant, container, {"Note", "Footnote"})
        ):
            continue
        name = local_name(descendant)
        if name == "Content":
            if nested_below(descendant, container, {"TextVariableInstance"}):
                continue
            pieces.extend(str(item) for item in descendant.itertext())
        elif name == "Br":
            pieces.append("\n")
        elif name == "TextVariableInstance" and descendant.get("ResultText"):
            pieces.append(descendant.get("ResultText", ""))
    return "".join(pieces)


def paragraph_containers(paragraph: etree._Element) -> Iterable[etree._Element]:
    for child in paragraph:
        if local_name(child) == "CharacterStyleRange":
            yield child
        elif local_name(child) == "HyperlinkTextSource":
            nested_ranges = [item for item in child if local_name(item) == "CharacterStyleRange"]
            yield from nested_ranges or [child]


def source_story_text(story: etree._Element) -> str:
    return "".join(
        visible_text(container)
        for paragraph in elements(story, "ParagraphStyleRange")
        for container in paragraph_containers(paragraph)
    )


def reconstructed_story_text(raw: RawArticle, story_id: str) -> str:
    story = next(item for item in raw.stories if item.source_self_id == story_id)
    labels = {
        item.anchor_run_id: item.label
        for item in raw.anchored_objects
        if item.kind == RawObjectKind.FORMULA
        and item.anchor_run_id is not None
        and item.label is not None
    }
    runs = {run.id: run for run in story.runs}
    # A label in a separate style range stays in the raw text. Only restore
    # labels consumed by the parser; never count the separate range twice.
    for paragraph in story.paragraphs:
        for index, run_id in enumerate(paragraph.text_run_ids):
            label = labels.get(run_id)
            if label is None:
                continue
            following = "".join(runs[key].text for key in paragraph.text_run_ids[index + 1 :])
            if re.match(rf"^\s*{re.escape(label)}", following):
                labels.pop(run_id)
    return "".join(run.text + labels.get(run.id, "") for run in story.runs)


def parse_roots(data: bytes) -> dict[str, etree._Element]:
    with ZipFile(BytesIO(data)) as archive:
        return {
            name: etree.fromstring(archive.read(name))
            for name in archive.namelist()
            if name.casefold().endswith(".xml")
        }


def resolved_hyperlink_source_count(roots: dict[str, etree._Element]) -> int:
    destinations = {
        element.get("DestinationUniqueKey"): element.get("DestinationURL")
        for root in roots.values()
        for element in elements(root, "HyperlinkURLDestination")
        if element.get("DestinationUniqueKey") and element.get("DestinationURL")
    }
    linked_sources = {
        element.get("Source")
        for root in roots.values()
        for element in elements(root, "Hyperlink")
        if element.get("Source")
        and destinations.get(element.get("DestinationUniqueKey")) is not None
    }
    return sum(
        bool(visible_text(element)) and element.get("Self") in linked_sources
        for root in roots.values()
        for element in elements(root, "HyperlinkTextSource")
    )


def structural_counts(roots: dict[str, etree._Element]) -> dict[str, int]:
    story_roots = [root for path, root in roots.items() if path.startswith("Stories/")]
    return {
        "stories": sum(
            sum(element.get("Self") is not None for element in elements(root, "Story"))
            for root in story_roots
        ),
        "pages": sum(
            len(elements(root, "Page"))
            for path, root in roots.items()
            if path.startswith("Spreads/")
        ),
        "tables": sum(len(elements(root, "Table")) for root in story_roots),
        "notes": sum(
            len(elements(root, "Note")) + len(elements(root, "Footnote")) for root in story_roots
        ),
        "table_cells": sum(len(elements(root, "Cell")) for root in story_roots),
        "spanning_cells": sum(
            int(element.get("RowSpan", "1")) > 1 or int(element.get("ColumnSpan", "1")) > 1
            for root in story_roots
            for element in elements(root, "Cell")
        ),
        "empty_cells": sum(
            not visible_text(element) for root in story_roots for element in elements(root, "Cell")
        ),
        "hyperlink_sources": resolved_hyperlink_source_count(roots),
    }


def raw_counts(raw: RawArticle) -> dict[str, int]:
    return {
        "stories": len(raw.stories),
        "pages": sum(len(spread.page_indices) for spread in raw.spreads),
        "tables": len(raw.tables),
        "notes": len(raw.notes),
        "table_cells": sum(len(table.cells) for table in raw.tables),
        "spanning_cells": sum(
            cell.row_span > 1 or cell.column_span > 1
            for table in raw.tables
            for cell in table.cells
        ),
        "empty_cells": sum(not cell.text_run_ids for table in raw.tables for cell in table.cells),
        "hyperlink_runs": sum(link.relationship == "external-hyperlink" for link in raw.links),
    }


def verify_package(data: bytes, logical_name: str) -> tuple[RawArticle, dict[str, int]]:
    roots = parse_roots(data)
    raw = IdmlParser().parse(data, logical_name=logical_name)
    source = structural_counts(roots)
    actual = raw_counts(raw)
    for key in ("stories", "pages", "tables", "notes", "table_cells", "spanning_cells"):
        if source[key] != actual[key]:
            raise AssertionError(f"structural_count:{key}")
    if actual["empty_cells"] < source["empty_cells"]:
        raise AssertionError("empty_table_cell_lost")
    if actual["hyperlink_runs"] < source["hyperlink_sources"]:
        raise AssertionError("hyperlink_source_lost")

    story_elements = {
        element.get("Self", ""): element
        for path, root in roots.items()
        if path.startswith("Stories/")
        for element in elements(root, "Story")
        if element.get("Self")
    }
    exact = sum(
        source_story_text(element) == reconstructed_story_text(raw, story_id)
        for story_id, element in story_elements.items()
    )
    if exact != len(story_elements):
        raise AssertionError("story_text_mismatch")
    if len(raw.reading_order) != len(raw.stories) or len(set(raw.reading_order)) != len(
        raw.stories
    ):
        raise AssertionError("reading_order_incomplete")
    return raw, {
        "source_stories": len(story_elements),
        "exact_stories": exact,
        "pages": actual["pages"],
        "tables": actual["tables"],
        "notes": actual["notes"],
        "hyperlink_sources": source["hyperlink_sources"],
        "hyperlink_runs": actual["hyperlink_runs"],
    }


def synthetic_gate() -> dict[str, int]:
    data = fidelity_idml()
    raw, metrics = verify_package(data, "ESA_2024999_AOP.idml")
    result = DeterministicPipeline().run(data, logical_name="ESA_2024999_AOP.idml")
    root = etree.fromstring(result.xml)
    character_overrides = [
        style for style in raw.styles if style.kind == StyleKind.CHARACTER and style.properties
    ]
    paragraph_overrides = [
        style
        for style in raw.styles
        if style.kind == StyleKind.PARAGRAPH and "BulletsAndNumberingListType" in style.properties
    ]
    required = {
        "valid_jats": result.validation.valid,
        "combined_emphasis": bool(root.xpath("body//bold/italic")),
        "safe_hyperlink": bool(
            root.xpath(
                "body//ext-link[starts-with(@xlink:href, 'https://')]",
                namespaces={"xlink": "http://www.w3.org/1999/xlink"},
            )
        ),
        "unsafe_hyperlink_blocked": not bool(
            root.xpath(
                "body//ext-link[starts-with(@xlink:href, 'javascript:')]",
                namespaces={"xlink": "http://www.w3.org/1999/xlink"},
            )
        ),
        "footnote": bool(root.xpath("back/fn-group/fn/p")),
        # SPS profile intentionally emits a one-item list as a paragraph (7C-04).
        "single_item_list_preserved": root.xpath("string(body//p[normalize-space(.)='list item'])")
        == "list item"
        and not root.xpath("body//list"),
        "designmap_order": [spread.source_self_id for spread in raw.spreads]
        == ["spread-first", "spread-second"],
        "page_columns": sorted(
            {frame.column_index for frame in raw.frames if frame.column_index is not None}
        )
        == [0, 1],
        "character_overrides": len(character_overrides) >= 4,
        "paragraph_overrides": len(paragraph_overrides) == 1,
    }
    failed = [name for name, passed in required.items() if not passed]
    if failed:
        raise AssertionError(f"synthetic_checks:{','.join(failed)}")
    return {**metrics, "checks": len(required)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--real-idml", type=Path, action="append", default=[])
    arguments = parser.parse_args()
    rows: list[dict[str, object]] = []
    try:
        metrics = synthetic_gate()
    except Exception as exc:
        rows.append({"case": "synthetic_v03", "passed": False, "error_type": type(exc).__name__})
    else:
        rows.append({"case": "synthetic_v03", "passed": True, "metrics": metrics})

    total_exact_stories = 0
    total_source_stories = 0
    real_verified = 0
    for index, path in enumerate(arguments.real_idml, start=1):
        try:
            _, metrics = verify_package(path.read_bytes(), path.name)
        except Exception as exc:
            rows.append(
                {
                    "case": f"real_idml_{index}",
                    "passed": False,
                    "error_type": type(exc).__name__,
                }
            )
        else:
            real_verified += 1
            total_exact_stories += metrics["exact_stories"]
            total_source_stories += metrics["source_stories"]
            rows.append({"case": f"real_idml_{index}", "passed": True, "metrics": metrics})

    approved = all(bool(row["passed"]) for row in rows) and real_verified == len(
        arguments.real_idml
    )
    report = {
        "version": "phase7-v03-gate-1.0",
        "family": "V-03",
        "approved": approved,
        "synthetic_cases": 1,
        "synthetic_passed": bool(rows[0]["passed"]),
        "real_packages_requested": len(arguments.real_idml),
        "real_packages_verified": real_verified,
        "real_source_stories": total_source_stories,
        "real_exact_stories": total_exact_stories,
        "rows": rows,
        "network_required": False,
        "restricted_content_emitted": False,
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if approved else 2


if __name__ == "__main__":
    raise SystemExit(main())
