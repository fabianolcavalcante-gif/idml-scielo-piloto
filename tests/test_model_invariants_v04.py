import copy

import pytest
from pydantic import ValidationError

from idml_foundation.domain.canonical import (
    CANONICAL_SCHEMA_VERSION,
    CanonicalArticle,
    Contributor,
    FieldState,
    InlineKind,
    InlineNode,
    RichText,
    SourcedText,
)
from idml_foundation.domain.common import canonical_bytes, content_digest
from idml_foundation.domain.raw import RAW_SCHEMA_VERSION, RawArticle
from idml_foundation.domain.schema_migrations import (
    UnsupportedSchemaVersion,
    migrate_payload,
)
from idml_foundation.pipeline.idml_parser import IdmlParser
from tests.domain_helpers import canonical_article, raw_article, sourced
from tests.test_idml_fidelity_v03 import fidelity_idml


def fidelity_raw() -> RawArticle:
    return IdmlParser().parse(fidelity_idml(), logical_name="ESA_2024999_AOP.idml")


def test_raw_schema_rejects_cross_story_dangling_and_incomplete_graphs() -> None:
    original = fidelity_raw().model_dump(mode="json")
    main = next(story for story in original["stories"] if story["source_self_id"] == "u-main")
    other = next(story for story in original["stories"] if story["source_self_id"] == "u-left")

    cases: list[tuple[dict[str, object], str]] = []

    dangling_style = copy.deepcopy(original)
    dangling_style["stories"][0]["runs"][0]["character_style_id"] = "missing-style"
    cases.append((dangling_style, "unknown character style"))

    cross_story = copy.deepcopy(original)
    changed_main = next(
        story for story in cross_story["stories"] if story["source_self_id"] == "u-main"
    )
    changed_main["paragraphs"][0]["text_run_ids"] = [other["runs"][0]["id"]]
    cases.append((cross_story, "another story"))

    duplicate_position = copy.deepcopy(original)
    changed_main = next(
        story for story in duplicate_position["stories"] if story["source_self_id"] == "u-main"
    )
    changed_main["runs"][1]["position"] = changed_main["runs"][0]["position"]
    cases.append((duplicate_position, "unique and contiguous"))

    incomplete_order = copy.deepcopy(original)
    incomplete_order["reading_order"] = incomplete_order["reading_order"][:-1]
    cases.append((incomplete_order, "include every story"))

    unowned_frame = copy.deepcopy(original)
    unowned_frame["spreads"][0]["frame_ids"] = unowned_frame["spreads"][0]["frame_ids"][1:]
    cases.append((unowned_frame, "exactly one spread"))

    broken_link = copy.deepcopy(original)
    hyperlink = next(
        link for link in broken_link["links"] if link["relationship"] == "external-hyperlink"
    )
    hyperlink["source_id"] = "missing-run"
    cases.append((broken_link, "invalid endpoint"))

    for payload, message in cases:
        with pytest.raises(ValidationError, match=message):
            RawArticle.model_validate(payload)

    assert main["paragraphs"]


def test_canonical_schema_rejects_ambiguous_or_mismatched_relationships() -> None:
    original = canonical_article().model_dump(mode="json")
    paragraph = original["body"][0]["blocks"][0]

    wrong_type = copy.deepcopy(original)
    wrong_type["body"][0]["blocks"][0]["cross_references"][0]["reference_type"] = "table"
    with pytest.raises(ValidationError, match="type does not match"):
        CanonicalArticle.model_validate(wrong_type)

    missing_metadata = copy.deepcopy(original)
    missing_metadata["body"][0]["blocks"][0]["cross_references"] = []
    with pytest.raises(ValidationError, match="metadata must match"):
        CanonicalArticle.model_validate(missing_metadata)

    empty_id = copy.deepcopy(original)
    empty_id["body"][0]["id"] = " "
    with pytest.raises(ValidationError, match="IDs cannot be empty"):
        CanonicalArticle.model_validate(empty_id)

    assert paragraph["cross_references"]


def test_inline_fields_and_rich_text_are_mutually_consistent() -> None:
    with pytest.raises(ValidationError, match="href is exclusive"):
        InlineNode(id="inline", kind=InlineKind.TEXT, text="text", href="https://example.org")
    with pytest.raises(ValidationError, match="target_id is exclusive"):
        InlineNode(id="inline", kind=InlineKind.STRONG, text="text", target_id="target")
    with pytest.raises(ValidationError, match="plain value"):
        RichText(
            plain=SourcedText(state=FieldState.NEEDS_REVIEW),
            inlines=(InlineNode(id="inline", kind=InlineKind.TEXT, text="visible"),),
        )


def test_contributor_kind_affiliations_and_orcid_are_unambiguous() -> None:
    valid = Contributor(
        id="contributor-valid",
        contributor_type="person",
        name=canonical_article().front.contributors[0].name,
        orcid=sourced("https://orcid.org/0000-0002-1825-0097"),
    )
    assert valid.orcid and valid.orcid.value.endswith("0097")

    payload = valid.model_dump(mode="json")
    payload["orcid"] = sourced("0000-0002-1825-0098").model_dump(mode="json")
    with pytest.raises(ValidationError, match="ORCID checksum"):
        Contributor.model_validate(payload)

    payload = valid.model_dump(mode="json")
    payload["group_name"] = sourced("Research Group").model_dump(mode="json")
    with pytest.raises(ValidationError, match="cannot contain group_name"):
        Contributor.model_validate(payload)

    payload = valid.model_dump(mode="json")
    payload["affiliation_ids"] = ["affiliation-1", "affiliation-1"]
    with pytest.raises(ValidationError, match="cannot be duplicated"):
        Contributor.model_validate(payload)


def test_formal_metadata_contract_rejects_ambiguous_values() -> None:
    original = canonical_article().model_dump(mode="json")

    invalid_country = copy.deepcopy(original)
    invalid_country["front"]["affiliations"][0]["country_code"] = sourced("br").model_dump(
        mode="json"
    )
    with pytest.raises(ValidationError, match="country_code"):
        CanonicalArticle.model_validate(invalid_country)

    invalid_license = copy.deepcopy(original)
    invalid_license["front"]["license_url"] = sourced("http://example.org/license").model_dump(
        mode="json"
    )
    with pytest.raises(ValidationError, match="license_url"):
        CanonicalArticle.model_validate(invalid_license)

    dangling_mode = copy.deepcopy(original)
    dangling_mode["back"]["data_availability_mode"] = "data-available"
    with pytest.raises(ValidationError, match="mode requires a statement"):
        CanonicalArticle.model_validate(dangling_mode)

    duplicate_history = copy.deepcopy(original)
    event = {
        "date_type": "accepted",
        "date": sourced("2026-01-01").model_dump(mode="json"),
    }
    duplicate_history["front"]["history_dates"] = [event, copy.deepcopy(event)]
    with pytest.raises(ValidationError, match="date types cannot be duplicated"):
        CanonicalArticle.model_validate(duplicate_history)


def test_schema_migrations_cover_every_persisted_version_and_cell_identity() -> None:
    raw_current = fidelity_raw().model_dump(mode="json")
    canonical_current = canonical_article().model_dump(mode="json")

    raw_legacy = copy.deepcopy(raw_current)
    raw_legacy["schema_version"] = "1.2.0"
    for table in raw_legacy["tables"]:
        for cell in table["cells"]:
            cell.pop("id")
    untouched = copy.deepcopy(raw_legacy)
    migrated_raw = migrate_payload("raw", raw_legacy)
    assert raw_legacy == untouched
    assert migrated_raw["schema_version"] == RAW_SCHEMA_VERSION
    assert RawArticle.model_validate(migrated_raw) == fidelity_raw()

    canonical_legacy = copy.deepcopy(canonical_current)
    canonical_legacy["schema_version"] = "1.1.0"
    migrated_canonical = migrate_payload("canonical", canonical_legacy)
    assert migrated_canonical["schema_version"] == CANONICAL_SCHEMA_VERSION
    assert CanonicalArticle.model_validate(migrated_canonical) == canonical_article()

    canonical_1_3 = copy.deepcopy(canonical_current)
    canonical_1_3["schema_version"] = "1.3.0"
    canonical_1_3["front"]["journal"].pop("publisher_name")
    canonical_1_3["front"].pop("history_dates")
    canonical_1_3["front"].pop("license_url")
    canonical_1_3["front"]["affiliations"][0].pop("original_text")
    canonical_1_3["front"]["affiliations"][0].pop("country_code")
    canonical_1_3["back"].pop("data_availability_mode")
    migrated_1_3 = migrate_payload("canonical", canonical_1_3)
    assert migrated_1_3["schema_version"] == CANONICAL_SCHEMA_VERSION
    assert migrated_1_3["front"]["journal"]["publisher_name"] is None
    assert migrated_1_3["front"]["history_dates"] == []
    assert migrated_1_3["back"]["data_availability_mode"] is None

    with pytest.raises(UnsupportedSchemaVersion):
        migrate_payload("raw", raw_current, target_version="1.2.0")


def test_unicode_rich_text_round_trip_property_is_stable_and_lossless() -> None:
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
                InlineNode(id=f"inline-{seed}-{position}", kind=InlineKind.TEXT, text=piece)
                for position, piece in enumerate(pieces)
            ),
        )
        restored = RichText.model_validate_json(canonical_bytes(rich))
        assert restored == rich
        assert content_digest(restored) == content_digest(rich)

        corrupted = rich.model_dump(mode="json")
        corrupted["inlines"][1]["text"] += "x"
        with pytest.raises(ValidationError, match="preserve the plain value"):
            RichText.model_validate(corrupted)


def test_models_and_migrations_are_idempotent() -> None:
    raw = raw_article()
    canonical = canonical_article()
    assert RawArticle.model_validate(raw.model_dump(mode="json")) == raw
    assert CanonicalArticle.model_validate(canonical.model_dump(mode="json")) == canonical
    assert migrate_payload("raw", raw.model_dump(mode="json")) == raw.model_dump(mode="json")
    assert migrate_payload("canonical", canonical.model_dump(mode="json")) == canonical.model_dump(
        mode="json"
    )
