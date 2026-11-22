import copy
from collections.abc import Callable
from typing import Any, Literal

from idml_foundation.domain.canonical import CANONICAL_SCHEMA_VERSION
from idml_foundation.domain.common import stable_id
from idml_foundation.domain.raw import RAW_SCHEMA_VERSION

ModelKind = Literal["raw", "canonical"]
Migration = Callable[[dict[str, Any]], dict[str, Any]]


class UnsupportedSchemaVersion(ValueError):
    pass


def _raw_0_1_to_1_0(payload: dict[str, Any]) -> dict[str, Any]:
    migrated = copy.deepcopy(payload)
    migrated["source_artifact_sha256"] = migrated.pop("source_sha256")
    migrated["schema_version"] = "1.0.0"
    return migrated


def _raw_1_0_to_1_1(payload: dict[str, Any]) -> dict[str, Any]:
    migrated = copy.deepcopy(payload)
    for story in migrated.get("stories", []):
        story.setdefault("paragraphs", [])
    migrated.setdefault("reading_order", [story["id"] for story in migrated.get("stories", [])])
    migrated.setdefault("reading_order_issues", [])
    migrated["schema_version"] = "1.1.0"
    return migrated


def _raw_1_1_to_1_2(payload: dict[str, Any]) -> dict[str, Any]:
    migrated = copy.deepcopy(payload)
    for anchored_object in migrated.get("anchored_objects", []):
        anchored_object.setdefault("placement", "unknown")
    migrated["schema_version"] = "1.2.0"
    return migrated


def _raw_1_2_to_1_3(payload: dict[str, Any]) -> dict[str, Any]:
    migrated = copy.deepcopy(payload)
    owner_by_table = {
        table_id: story.get("source_self_id", story["id"])
        for story in migrated.get("stories", [])
        for table_id in story.get("table_ids", [])
    }
    article_id = migrated.get("article_id", "legacy-article")
    for table in migrated.get("tables", []):
        owner = owner_by_table.get(table.get("id"), "unowned-story")
        table_self = table.get("source_self_id", table.get("id", "table"))
        for cell in table.get("cells", []):
            cell.setdefault(
                "id",
                stable_id(
                    article_id,
                    "cell",
                    f"{owner}:{table_self}:{cell.get('column', 0)}:{cell.get('row', 0)}",
                ),
            )
    migrated["schema_version"] = RAW_SCHEMA_VERSION
    return migrated


def _canonical_0_1_to_1_0(payload: dict[str, Any]) -> dict[str, Any]:
    migrated = copy.deepcopy(payload)
    migrated["journal_profile_id"] = migrated.pop("profile")
    migrated["source_raw_sha256"] = migrated.pop("raw_sha256")
    migrated.setdefault("assets", [])
    migrated.setdefault("review_reasons", [])
    migrated["schema_version"] = "1.0.0"
    return migrated


def _canonical_1_0_to_1_1(payload: dict[str, Any]) -> dict[str, Any]:
    migrated = copy.deepcopy(payload)
    migrated["schema_version"] = "1.1.0"
    return migrated


def _canonical_1_1_to_1_2(payload: dict[str, Any]) -> dict[str, Any]:
    migrated = copy.deepcopy(payload)
    migrated["schema_version"] = "1.2.0"
    return migrated


def _canonical_1_2_to_1_3(payload: dict[str, Any]) -> dict[str, Any]:
    migrated = copy.deepcopy(payload)

    def add_table_spans(section: dict[str, Any]) -> None:
        for block in section.get("blocks", []):
            if block.get("kind") == "table":
                block.setdefault("cell_spans", [])
        for child in section.get("children", []):
            add_table_spans(child)

    for section in migrated.get("body", []):
        add_table_spans(section)
    migrated["schema_version"] = "1.3.0"
    return migrated


def _canonical_1_3_to_1_4(payload: dict[str, Any]) -> dict[str, Any]:
    migrated = copy.deepcopy(payload)
    front = migrated.get("front", {})
    journal = front.get("journal", {})
    journal.setdefault("publisher_name", None)
    for affiliation in front.get("affiliations", []):
        affiliation.setdefault("original_text", None)
        affiliation.setdefault("country_code", None)
    front.setdefault("license_url", None)
    front.setdefault("history_dates", [])
    back = migrated.get("back", {})
    back.setdefault("data_availability_mode", None)
    migrated["schema_version"] = "1.4.0"
    return migrated


def _canonical_1_4_to_1_5(payload: dict[str, Any]) -> dict[str, Any]:
    migrated = copy.deepcopy(payload)
    # Migration is not reconversion: do not infer bibliographic classification.
    migrated["schema_version"] = "1.5.0"
    return migrated


def _canonical_1_5_to_1_6(payload: dict[str, Any]) -> dict[str, Any]:
    migrated = copy.deepcopy(payload)
    # Webpage/report are permitted, never assigned by migration.
    migrated["schema_version"] = "1.6.0"
    return migrated


def _canonical_1_6_to_1_7(payload: dict[str, Any]) -> dict[str, Any]:
    """1.7.0 adds TableBlock.header_rows (default 0: same rendering as before)."""
    migrated = copy.deepcopy(payload)
    migrated["schema_version"] = "1.7.0"
    return migrated


MIGRATIONS: dict[tuple[ModelKind, str], tuple[str, Migration]] = {
    ("raw", "0.1.0"): ("1.0.0", _raw_0_1_to_1_0),
    ("raw", "1.0.0"): ("1.1.0", _raw_1_0_to_1_1),
    ("raw", "1.1.0"): ("1.2.0", _raw_1_1_to_1_2),
    ("raw", "1.2.0"): (RAW_SCHEMA_VERSION, _raw_1_2_to_1_3),
    ("canonical", "0.1.0"): ("1.0.0", _canonical_0_1_to_1_0),
    ("canonical", "1.0.0"): ("1.1.0", _canonical_1_0_to_1_1),
    ("canonical", "1.1.0"): ("1.2.0", _canonical_1_1_to_1_2),
    ("canonical", "1.2.0"): ("1.3.0", _canonical_1_2_to_1_3),
    ("canonical", "1.3.0"): ("1.4.0", _canonical_1_3_to_1_4),
    ("canonical", "1.4.0"): ("1.5.0", _canonical_1_4_to_1_5),
    ("canonical", "1.5.0"): ("1.6.0", _canonical_1_5_to_1_6),
    ("canonical", "1.6.0"): (CANONICAL_SCHEMA_VERSION, _canonical_1_6_to_1_7),
}

LATEST_VERSIONS: dict[ModelKind, str] = {
    "raw": RAW_SCHEMA_VERSION,
    "canonical": CANONICAL_SCHEMA_VERSION,
}


def migrate_payload(
    kind: ModelKind,
    payload: dict[str, Any],
    target_version: str | None = None,
) -> dict[str, Any]:
    target = target_version or LATEST_VERSIONS[kind]
    migrated = copy.deepcopy(payload)
    seen: set[str] = set()
    while migrated.get("schema_version") != target:
        current = migrated.get("schema_version")
        if not isinstance(current, str) or current in seen:
            raise UnsupportedSchemaVersion(f"cannot migrate {kind} schema from {current!r}")
        seen.add(current)
        step = MIGRATIONS.get((kind, current))
        if step is None:
            raise UnsupportedSchemaVersion(f"no {kind} schema migration from {current}")
        next_version, migration = step
        migrated = migration(migrated)
        if migrated.get("schema_version") != next_version:
            raise RuntimeError(f"{kind} migration did not produce {next_version}")
    return migrated
