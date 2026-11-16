import asyncio
import os
import stat
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from idml_foundation.ingest import xml_security
from idml_foundation.ingest.safe_zip import UnsafeArchiveError, _validate_name, inspect_idml
from idml_foundation.ingest.scanner import PolicyOnlyScanner
from idml_foundation.ingest.xml_security import UnsafeXmlError, parse_untrusted_xml
from idml_foundation.models import Artifact, Organization
from idml_foundation.pipeline.idml_parser import IdmlParser
from idml_foundation.services.artifacts import store_idml_artifact
from idml_foundation.services.storage_budget import ArtifactStorageError
from idml_foundation.settings import Settings
from tests.test_phase7_v12_http_upload import consume, multipart


def archive_with(
    entries: tuple[tuple[str | ZipInfo, bytes, int], ...] = (),
    *,
    mimetype: bytes = b"application/vnd.adobe.indesign-idml-package",
    designmap: bytes = b"<Document/>",
    include_required: bool = True,
) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        if include_required:
            archive.writestr("mimetype", mimetype, compress_type=ZIP_STORED)
            archive.writestr("designmap.xml", designmap, compress_type=ZIP_DEFLATED)
        for name, content, compression in entries:
            archive.writestr(name, content, compress_type=compression)
    return output.getvalue()


def mark_first_entry_encrypted(data: bytes) -> bytes:
    mutated = bytearray(data)
    local = mutated.find(b"PK\x03\x04")
    central = mutated.find(b"PK\x01\x02")
    assert local >= 0 and central >= 0
    mutated[local + 6] |= 0x01
    mutated[central + 8] |= 0x01
    return bytes(mutated)


def mark_first_entry_with_unsupported_compression(data: bytes) -> bytes:
    mutated = bytearray(data)
    local = mutated.find(b"PK\x03\x04")
    central = mutated.find(b"PK\x01\x02")
    assert local >= 0 and central >= 0
    mutated[local + 8 : local + 10] = (99).to_bytes(2, "little")
    mutated[central + 10 : central + 12] = (99).to_bytes(2, "little")
    return bytes(mutated)


@pytest.mark.security
@pytest.mark.parametrize(
    ("entry_name", "expected_code"),
    [
        ("/absolute.xml", "path_traversal"),
        ("C:/absolute.xml", "absolute_path"),
        ("Stories//Story.xml", "invalid_path"),
        ("Stories/./Story.xml", "path_traversal"),
        ("Stories/Story\u202e.xml", "invalid_path"),
        ("Resources/payload.exe", "forbidden_payload"),
        ("Resources/payload.idml", "nested_archive"),
    ],
)
def test_path_and_payload_matrix_fails_closed(
    settings: Settings, entry_name: str, expected_code: str
) -> None:
    with pytest.raises(UnsafeArchiveError) as error:
        inspect_idml(archive_with(((entry_name, b"x", ZIP_STORED),)), settings)
    assert error.value.code == expected_code


@pytest.mark.security
def test_windows_separator_is_rejected(settings: Settings) -> None:
    del settings
    with pytest.raises(UnsafeArchiveError) as error:
        _validate_name("Stories\\Story.xml")
    assert error.value.code == "invalid_path"


@pytest.mark.security
def test_unicode_normalization_collision_is_rejected(settings: Settings) -> None:
    data = archive_with(
        (
            ("Stories/Caf\u00e9.xml", b"<Story/>", ZIP_STORED),
            ("Stories/Cafe\u0301.xml", b"<Story/>", ZIP_STORED),
        )
    )
    with pytest.raises(UnsafeArchiveError) as error:
        inspect_idml(data, settings)
    assert error.value.code == "duplicate_entry"


@pytest.mark.security
def test_case_collision_and_encrypted_entry_are_rejected(settings: Settings) -> None:
    collision = archive_with(
        (
            ("Stories/Story.xml", b"<Story/>", ZIP_STORED),
            ("stories/story.XML", b"<Story/>", ZIP_STORED),
        )
    )
    with pytest.raises(UnsafeArchiveError) as duplicate_error:
        inspect_idml(collision, settings)
    assert duplicate_error.value.code == "duplicate_entry"

    with pytest.raises(UnsafeArchiveError) as encrypted_error:
        inspect_idml(mark_first_entry_encrypted(archive_with()), settings)
    assert encrypted_error.value.code == "encrypted_entry"

    unsupported = mark_first_entry_with_unsupported_compression(archive_with())
    with pytest.raises(UnsafeArchiveError) as compression_error:
        inspect_idml(unsupported, settings)
    assert compression_error.value.code == "unsupported_compression"


@pytest.mark.security
@pytest.mark.parametrize("parent_first", [True, False])
def test_file_directory_shadowing_is_rejected(settings: Settings, parent_first: bool) -> None:
    parent = ("Stories", b"not-a-directory", ZIP_STORED)
    child = ("Stories/Story.xml", b"<Story/>", ZIP_STORED)
    entries = (parent, child) if parent_first else (child, parent)
    with pytest.raises(UnsafeArchiveError) as error:
        inspect_idml(archive_with(entries), settings)
    assert error.value.code == "path_type_conflict"


@pytest.mark.security
def test_symlink_entry_is_rejected(settings: Settings) -> None:
    symlink = ZipInfo("Links/escape")
    symlink.create_system = 3
    symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
    with pytest.raises(UnsafeArchiveError) as error:
        inspect_idml(archive_with(((symlink, b"../../outside", ZIP_STORED),)), settings)
    assert error.value.code == "special_entry"


@pytest.mark.security
def test_entry_count_expanded_size_depth_and_path_limits(settings: Settings) -> None:
    three_entries = archive_with((("Stories/Story.xml", b"<Story/>", ZIP_STORED),))
    with pytest.raises(UnsafeArchiveError) as count_error:
        inspect_idml(three_entries, settings.model_copy(update={"zip_max_entries": 2}))
    assert count_error.value.code == "too_many_entries"

    expanded = archive_with((("Stories/Story.xml", b"x" * 256, ZIP_STORED),))
    with pytest.raises(UnsafeArchiveError) as size_error:
        inspect_idml(expanded, settings.model_copy(update={"zip_max_uncompressed_bytes": 128}))
    assert size_error.value.code == "expanded_too_large"

    deep = archive_with((("a/b/c/d.xml", b"<x/>", ZIP_STORED),))
    with pytest.raises(UnsafeArchiveError) as depth_error:
        inspect_idml(deep, settings.model_copy(update={"zip_max_depth": 3}))
    assert depth_error.value.code == "path_too_deep"

    long_path = archive_with(((f"Stories/{'a' * 80}.xml", b"<x/>", ZIP_STORED),))
    with pytest.raises(UnsafeArchiveError) as path_error:
        inspect_idml(long_path, settings.model_copy(update={"zip_max_path_bytes": 64}))
    assert path_error.value.code == "path_too_long"


@pytest.mark.security
def test_upload_size_and_compression_ratio_are_rejected(settings: Settings) -> None:
    data = archive_with((("Stories/Story.xml", b"A" * 4096, ZIP_DEFLATED),))
    with pytest.raises(UnsafeArchiveError) as upload_error:
        inspect_idml(data, settings.model_copy(update={"upload_max_bytes": len(data) - 1}))
    assert upload_error.value.code == "upload_too_large"

    with pytest.raises(UnsafeArchiveError) as ratio_error:
        inspect_idml(data, settings.model_copy(update={"zip_max_ratio": 2}))
    assert ratio_error.value.code == "compression_ratio"


@pytest.mark.security
def test_missing_required_entry_and_mimetype_case_are_controlled(settings: Settings) -> None:
    with pytest.raises(UnsafeArchiveError) as missing_error:
        inspect_idml(archive_with(include_required=False), settings)
    assert missing_error.value.code == "invalid_idml"

    output = BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr("MIMETYPE", b"application/vnd.adobe.indesign-idml-package")
        archive.writestr("designmap.xml", b"<Document/>")
    with pytest.raises(UnsafeArchiveError) as case_error:
        inspect_idml(output.getvalue(), settings)
    assert case_error.value.code == "invalid_idml"

    with pytest.raises(UnsafeArchiveError) as mime_error:
        inspect_idml(archive_with(mimetype=b"application/zip"), settings)
    assert mime_error.value.code == "invalid_mimetype"


@pytest.mark.security
def test_corrupt_entry_crc_is_rejected_before_parsing(settings: Settings) -> None:
    marker = b"UNIQUE-STORED-PAYLOAD"
    corrupted = bytearray(archive_with((("Stories/Story.xml", marker, ZIP_STORED),)))
    offset = corrupted.find(marker)
    assert offset >= 0
    corrupted[offset] ^= 0x01
    with pytest.raises(UnsafeArchiveError) as error:
        inspect_idml(bytes(corrupted), settings)
    assert error.value.code == "corrupt_entry"


@pytest.mark.security
def test_xml_security_handles_utf16_dtd_entities_binary_and_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    utf16_dtd = '<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE x><x/>'.encode("utf-16")
    with pytest.raises(UnsafeXmlError, match="DOCTYPE"):
        parse_untrusted_xml(utf16_dtd)
    with pytest.raises(UnsafeXmlError, match="malformed"):
        parse_untrusted_xml(b"\x00\x01binary")
    monkeypatch.setattr(xml_security, "MAX_UNTRUSTED_XML_BYTES", 32)
    with pytest.raises(UnsafeXmlError, match="size limit"):
        parse_untrusted_xml(b"<x>" + b"a" * 32 + b"</x>")


@pytest.mark.security
def test_xml_comments_and_safe_unicode_are_preserved() -> None:
    root = parse_untrusted_xml("<x><!--audit--><p>caf\u00e9</p></x>".encode())
    assert root.findtext("p") == "caf\u00e9"
    assert root[0].text == "audit"


@pytest.mark.security
def test_incomplete_idml_references_are_classified_without_crashing() -> None:
    design = b"""<Document Self="doc"
      StoryList="missing-story orphan-story threaded-story"/>"""
    story = b"""<idPkg:Story
      xmlns:idPkg="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging">
      <Story Self="orphan-story"/>
    </idPkg:Story>"""
    threaded_story = story.replace(b"orphan-story", b"threaded-story")
    spread = b"""<idPkg:Spread
      xmlns:idPkg="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging">
      <Spread Self="spread"><Page Self="page"/>
        <TextFrame Self="broken-frame" ParentStory="missing-parent"
          PreviousTextFrame="n" NextTextFrame="n"/>
        <TextFrame Self="threaded-frame" ParentStory="threaded-story"
          PreviousTextFrame="n" NextTextFrame="missing-frame"/>
      </Spread>
    </idPkg:Spread>"""
    data = archive_with(
        (
            ("Stories/Story_orphan.xml", story, ZIP_DEFLATED),
            ("Stories/Story_threaded.xml", threaded_story, ZIP_DEFLATED),
            ("Spreads/Spread.xml", spread, ZIP_DEFLATED),
        ),
        designmap=design,
    )

    raw = IdmlParser().parse(data, logical_name="incomplete.idml")

    assert {issue.code for issue in raw.reading_order_issues} == {
        "frame_parent_story_missing",
        "frame_thread_reference_missing",
        "story_list_reference_missing",
        "story_without_frame",
    }
    assert len(raw.stories) == 2
    assert len(raw.frames) == 1


@pytest.mark.security
def test_malformed_internal_idml_structure_is_rejected_with_controlled_code() -> None:
    data = archive_with((("Stories/Broken.xml", b"<NotAStory/>", ZIP_DEFLATED),))
    with pytest.raises(UnsafeArchiveError) as error:
        IdmlParser().parse(data, logical_name="broken.idml")
    assert error.value.code == "invalid_idml_structure"


@pytest.mark.security
def test_temporary_upload_is_removed_when_atomic_move_fails(
    db: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    organization = Organization(slug="v02-cleanup", name="V02 Cleanup")
    db.add(organization)
    db.flush()

    def fail_replace(source: os.PathLike[str], destination: os.PathLike[str]) -> None:
        del source, destination
        raise OSError("simulated storage failure")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(ArtifactStorageError, match="artifact_storage_unavailable") as error:
        store_idml_artifact(
            db,
            organization_id=organization.id,
            original_name="unsafe-name.idml",
            data=archive_with(),
            settings=settings,
            scanner=PolicyOnlyScanner(),
        )
    assert isinstance(error.value.__cause__, OSError)
    assert str(error.value.__cause__) == "simulated storage failure"
    assert list(settings.artifact_root.rglob(".upload-*")) == []
    assert db.scalar(select(Artifact).where(Artifact.organization_id == organization.id)) is None


@pytest.mark.security
def test_cancelled_and_oversized_uploads_never_reach_storage(settings: Settings) -> None:
    settings.upload_max_bytes = 256
    with pytest.raises(asyncio.CancelledError):
        consume(settings, multipart(b"part", ending=False), interrupt="cancel")
    with pytest.raises(HTTPException) as oversized_error:
        consume(settings, multipart(b"x" * 257))
    assert oversized_error.value.status_code == 413
    # A persistent admission lock is expected even for rejected requests.
    assert {p.name for p in settings.artifact_root.iterdir()} == {".upload-admission"}
