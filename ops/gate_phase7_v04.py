"""Execute the content-free V-04 domain-model integrity gate."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from collections.abc import Callable
from pathlib import Path

from pydantic import ValidationError

from idml_foundation.domain.canonical import (
    CANONICAL_SCHEMA_VERSION,
    CanonicalArticle,
    Contributor,
    FieldState,
    InlineKind,
    InlineNode,
    ListBlock,
    RichText,
    SourcedText,
    TableBlock,
)
from idml_foundation.domain.common import canonical_bytes, content_digest
from idml_foundation.domain.raw import RAW_SCHEMA_VERSION, RawArticle
from idml_foundation.domain.schema_migrations import migrate_payload
from idml_foundation.pipeline.idml_parser import IdmlParser
from idml_foundation.pipeline.service import DeterministicPipeline

sys.path.insert(0, str(Path(__file__).parents[1]))
from tests.domain_helpers import canonical_article, sourced
from tests.test_idml_fidelity_v03 import fidelity_idml


def expect_validation_error(execute: Callable[[], object]) -> None:
    try:
        execute()
    except ValidationError:
        return
    raise AssertionError("invalid model candidate was accepted")


def mutation_cases() -> tuple[tuple[str, Callable[[], object]], ...]:
    raw_payload = (
        IdmlParser()
        .parse(fidelity_idml(), logical_name="ESA_2024999_AOP.idml")
        .model_dump(mode="json")
    )
    canonical_payload = canonical_article().model_dump(mode="json")

    def raw_with(mutator: Callable[[dict[str, object]], None]) -> RawArticle:
        payload = copy.deepcopy(raw_payload)
        mutator(payload)
        return RawArticle.model_validate(payload)

    def canonical_with(mutator: Callable[[dict[str, object]], None]) -> CanonicalArticle:
        payload = copy.deepcopy(canonical_payload)
        mutator(payload)
        return CanonicalArticle.model_validate(payload)

    def dangling_style(payload: dict[str, object]) -> None:
        payload["stories"][0]["runs"][0]["character_style_id"] = "missing"  # type: ignore[index]

    def incomplete_order(payload: dict[str, object]) -> None:
        payload["reading_order"] = payload["reading_order"][:-1]  # type: ignore[index]

    def cross_story_run(payload: dict[str, object]) -> None:
        stories = payload["stories"]  # type: ignore[assignment]
        stories[0]["paragraphs"][0]["text_run_ids"] = [stories[1]["runs"][0]["id"]]  # type: ignore[index]

    def overlapping_cells(payload: dict[str, object]) -> None:
        cells = payload["tables"][0]["cells"]  # type: ignore[index]
        cells[-1]["row"] = cells[0]["row"]
        cells[-1]["column"] = cells[0]["column"]

    def wrong_reference_type(payload: dict[str, object]) -> None:
        payload["body"][0]["blocks"][0]["cross_references"][0]["reference_type"] = "table"  # type: ignore[index]

    def missing_reference_metadata(payload: dict[str, object]) -> None:
        payload["body"][0]["blocks"][0]["cross_references"] = []  # type: ignore[index]

    def empty_id(payload: dict[str, object]) -> None:
        payload["body"][0]["id"] = " "  # type: ignore[index]

    def top_level_two(payload: dict[str, object]) -> None:
        payload["body"][0]["level"] = 2  # type: ignore[index]

    valid_contributor = Contributor(
        id="contributor-valid",
        contributor_type="person",
        name=canonical_article().front.contributors[0].name,
        orcid=sourced("0000-0002-1825-0097"),
    )

    def invalid_orcid() -> object:
        payload = valid_contributor.model_dump(mode="json")
        payload["orcid"] = sourced("0000-0002-1825-0098").model_dump(mode="json")
        return Contributor.model_validate(payload)

    return (
        ("raw_dangling_style", lambda: raw_with(dangling_style)),
        ("raw_incomplete_reading_order", lambda: raw_with(incomplete_order)),
        ("raw_cross_story_run", lambda: raw_with(cross_story_run)),
        ("raw_overlapping_table_cells", lambda: raw_with(overlapping_cells)),
        ("canonical_wrong_reference_type", lambda: canonical_with(wrong_reference_type)),
        (
            "canonical_missing_reference_metadata",
            lambda: canonical_with(missing_reference_metadata),
        ),
        ("canonical_empty_id", lambda: canonical_with(empty_id)),
        ("canonical_top_level_section", lambda: canonical_with(top_level_two)),
        ("canonical_invalid_orcid", invalid_orcid),
        (
            "inline_field_exclusivity",
            lambda: InlineNode(
                id="inline", kind=InlineKind.TEXT, text="text", href="https://example.org"
            ),
        ),
        (
            "rich_text_plain_mismatch",
            lambda: RichText(
                plain=SourcedText(value="whole", state=FieldState.PRESENT),
                inlines=(InlineNode(id="inline", kind=InlineKind.TEXT, text="partial"),),
            ),
        ),
        (
            "empty_list",
            lambda: ListBlock(id="list", ordered=False, items=()),
        ),
        (
            "empty_table",
            lambda: TableBlock(
                id="table",
                label=sourced("Table 1"),
                caption=RichText(plain=sourced("Caption")),
                rows=(),
            ),
        ),
    )


def verify_round_trip(raw: RawArticle, canonical: CanonicalArticle) -> None:
    restored_raw = RawArticle.model_validate_json(canonical_bytes(raw))
    restored_canonical = CanonicalArticle.model_validate_json(canonical_bytes(canonical))
    if restored_raw != raw or restored_canonical != canonical:
        raise AssertionError("model round-trip changed content")
    if content_digest(restored_raw) != content_digest(raw):
        raise AssertionError("Raw Article digest changed after round-trip")
    if content_digest(restored_canonical) != content_digest(canonical):
        raise AssertionError("Canonical Article digest changed after round-trip")


def property_checks() -> int:
    alphabet = ("á", "β", "漢", "🙂", "\u00a0", "\u00ad", "\t", "\n")
    for seed in range(128):
        pieces = (
            "v",
            "".join(alphabet[(seed + offset) % len(alphabet)] for offset in range(seed % 11)),
            str(seed),
        )
        value = "".join(pieces)
        rich = RichText(
            plain=SourcedText(value=value, state=FieldState.PRESENT),
            inlines=tuple(
                InlineNode(id=f"inline-{seed}-{index}", kind=InlineKind.TEXT, text=piece)
                for index, piece in enumerate(pieces)
            ),
        )
        if RichText.model_validate_json(canonical_bytes(rich)) != rich:
            raise AssertionError("RichText property round-trip changed content")
    return 128


def migration_checks() -> int:
    raw = (
        IdmlParser()
        .parse(fidelity_idml(), logical_name="ESA_2024999_AOP.idml")
        .model_dump(mode="json")
    )
    legacy_raw = copy.deepcopy(raw)
    legacy_raw["schema_version"] = "1.2.0"
    for table in legacy_raw["tables"]:
        for cell in table["cells"]:
            cell.pop("id")
    migrated_raw = migrate_payload("raw", legacy_raw)
    if migrated_raw["schema_version"] != RAW_SCHEMA_VERSION:
        raise AssertionError("Raw Article migration stopped before latest")
    RawArticle.model_validate(migrated_raw)

    legacy_canonical = canonical_article().model_dump(mode="json")
    legacy_canonical["schema_version"] = "1.1.0"
    migrated_canonical = migrate_payload("canonical", legacy_canonical)
    if migrated_canonical["schema_version"] != CANONICAL_SCHEMA_VERSION:
        raise AssertionError("Canonical Article migration stopped before latest")
    CanonicalArticle.model_validate(migrated_canonical)
    return 2


def synthetic_gate() -> dict[str, int]:
    rows = mutation_cases()
    for _, execute in rows:
        expect_validation_error(execute)
    result = DeterministicPipeline().run(fidelity_idml(), logical_name="ESA_2024999_AOP.idml")
    verify_round_trip(result.raw, result.canonical)
    return {
        "negative_cases": len(rows),
        "property_cases": property_checks(),
        "migration_paths": migration_checks(),
        "round_trip_candidates": 1,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--real-idml", type=Path, action="append", default=[])
    arguments = parser.parse_args()
    rows: list[dict[str, object]] = []
    try:
        metrics = synthetic_gate()
    except Exception as exc:
        rows.append({"case": "synthetic_v04", "passed": False, "error_type": type(exc).__name__})
    else:
        rows.append({"case": "synthetic_v04", "passed": True, "metrics": metrics})

    real_verified = 0
    for index, path in enumerate(arguments.real_idml, start=1):
        try:
            result = DeterministicPipeline().run(path.read_bytes(), logical_name=path.name)
            verify_round_trip(result.raw, result.canonical)
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
            rows.append(
                {
                    "case": f"real_idml_{index}",
                    "passed": True,
                    "metrics": {
                        "raw_stories": len(result.raw.stories),
                        "canonical_sections": len(result.canonical.body),
                        "review_reasons": len(result.canonical.review_reasons),
                    },
                }
            )

    approved = all(bool(row["passed"]) for row in rows) and real_verified == len(
        arguments.real_idml
    )
    report = {
        "version": "phase7-v04-gate-1.0",
        "family": "V-04",
        "approved": approved,
        "raw_schema_version": RAW_SCHEMA_VERSION,
        "canonical_schema_version": CANONICAL_SCHEMA_VERSION,
        "real_packages_requested": len(arguments.real_idml),
        "real_packages_verified": real_verified,
        "rows": rows,
        "network_required": False,
        "restricted_content_emitted": False,
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if approved else 2


if __name__ == "__main__":
    raise SystemExit(main())
