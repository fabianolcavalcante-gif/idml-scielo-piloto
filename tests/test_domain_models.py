import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from idml_foundation.domain.canonical import (
    CANONICAL_SCHEMA_VERSION,
    CanonicalArticle,
    FieldState,
    InlineKind,
    InlineNode,
    RichText,
    SourcedText,
)
from idml_foundation.domain.common import canonical_bytes, content_digest, stable_id
from idml_foundation.domain.raw import RAW_SCHEMA_VERSION, RawArticle
from idml_foundation.domain.schema_migrations import (
    UnsupportedSchemaVersion,
    migrate_payload,
)
from tests.domain_helpers import canonical_article, raw_article


def test_raw_round_trip_is_lossless_and_deterministic() -> None:
    original = raw_article()
    restored = RawArticle.model_validate_json(canonical_bytes(original))
    assert restored == original
    assert restored.schema_version == RAW_SCHEMA_VERSION
    assert content_digest(restored) == content_digest(original)


def test_raw_graph_rejects_dangling_frame_reference() -> None:
    payload = raw_article().model_dump(mode="json")
    payload["frames"][0]["parent_story_id"] = "unknown-story"
    with pytest.raises(ValidationError, match="unknown story"):
        RawArticle.model_validate(payload)


def test_canonical_round_trip_and_graph_integrity() -> None:
    original = canonical_article()
    restored = CanonicalArticle.model_validate_json(canonical_bytes(original))
    assert restored == original
    assert restored.schema_version == CANONICAL_SCHEMA_VERSION

    payload = original.model_dump(mode="json")
    payload["body"][0]["blocks"][0]["cross_references"][0]["target_id"] = "missing"
    with pytest.raises(ValidationError, match="cross-reference"):
        CanonicalArticle.model_validate(payload)


def test_sourced_value_states_do_not_invent_missing_data() -> None:
    missing = SourcedText(state=FieldState.MISSING)
    assert missing.value is None
    with pytest.raises(ValidationError, match="present field"):
        SourcedText(state=FieldState.PRESENT)
    with pytest.raises(ValidationError, match="at least two alternatives"):
        SourcedText(state=FieldState.AMBIGUOUS, alternatives=("one",))


def test_rich_text_preserves_inline_content_without_loss() -> None:
    with pytest.raises(ValidationError, match="preserve the plain value"):
        RichText(
            plain=SourcedText(value="complete", state=FieldState.PRESENT),
            inlines=(InlineNode(id="inline-1", kind=InlineKind.TEXT, text="partial"),),
        )


def test_stable_ids_are_repeatable_and_locator_sensitive() -> None:
    first = stable_id("article-1", "paragraph", "Story_u1.xml#p1")
    assert first == stable_id("article-1", "paragraph", "Story_u1.xml#p1")
    assert first != stable_id("article-1", "paragraph", "Story_u1.xml#p2")


def test_versioned_schema_migrations_are_explicit_and_non_mutating() -> None:
    raw_legacy = raw_article().model_dump(mode="json")
    raw_legacy["schema_version"] = "0.1.0"
    raw_legacy["source_sha256"] = raw_legacy.pop("source_artifact_sha256")
    untouched = json.loads(json.dumps(raw_legacy))
    migrated = migrate_payload("raw", raw_legacy)
    assert migrated["schema_version"] == RAW_SCHEMA_VERSION
    assert raw_legacy == untouched

    canonical_legacy = canonical_article().model_dump(mode="json")
    canonical_legacy["schema_version"] = "0.1.0"
    canonical_legacy["profile"] = canonical_legacy.pop("journal_profile_id")
    canonical_legacy["raw_sha256"] = canonical_legacy.pop("source_raw_sha256")
    migrated_canonical = migrate_payload("canonical", canonical_legacy)
    assert CanonicalArticle.model_validate(migrated_canonical)

    with pytest.raises(UnsupportedSchemaVersion):
        migrate_payload("raw", {"schema_version": "9.9.9"})


def test_exported_json_schemas_match_runtime_contracts() -> None:
    schema_root = Path(__file__).parents[1] / "schemas"
    raw_schema = json.loads((schema_root / "raw-article-1.3.0.schema.json").read_text())
    canonical_schema = json.loads((schema_root / "canonical-article-1.7.0.schema.json").read_text())
    assert raw_schema == RawArticle.model_json_schema()
    assert canonical_schema == CanonicalArticle.model_json_schema()
