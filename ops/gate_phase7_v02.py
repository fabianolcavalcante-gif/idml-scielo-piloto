"""Execute the content-free V-02 IDML ingestion security matrix."""

from __future__ import annotations

import argparse
import json
import stat
from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

from idml_foundation.ingest.safe_zip import UnsafeArchiveError, _validate_name, inspect_idml
from idml_foundation.ingest.xml_security import UnsafeXmlError, parse_untrusted_xml
from idml_foundation.pipeline.idml_parser import IdmlParser
from idml_foundation.settings import Settings

MIMETYPE = b"application/vnd.adobe.indesign-idml-package"


def archive_with(
    entries: tuple[tuple[str | ZipInfo, bytes, int], ...] = (),
    *,
    mimetype: bytes = MIMETYPE,
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
    if local < 0 or central < 0:
        raise AssertionError("could not construct encrypted entry case")
    mutated[local + 6] |= 0x01
    mutated[central + 8] |= 0x01
    return bytes(mutated)


def mark_first_entry_with_unsupported_compression(data: bytes) -> bytes:
    mutated = bytearray(data)
    local = mutated.find(b"PK\x03\x04")
    central = mutated.find(b"PK\x01\x02")
    if local < 0 or central < 0:
        raise AssertionError("could not construct unsupported compression case")
    mutated[local + 8 : local + 10] = (99).to_bytes(2, "little")
    mutated[central + 10 : central + 12] = (99).to_bytes(2, "little")
    return bytes(mutated)


def expect_archive_error(data: bytes, settings: Settings, code: str) -> None:
    try:
        inspect_idml(data, settings)
    except UnsafeArchiveError as exc:
        if exc.code != code:
            raise AssertionError(f"expected {code}, received {exc.code}") from exc
    else:
        raise AssertionError(f"expected archive rejection {code}")


def expect_xml_error(data: bytes) -> None:
    try:
        parse_untrusted_xml(data)
    except UnsafeXmlError:
        return
    raise AssertionError("expected XML rejection")


def security_cases(settings: Settings) -> tuple[tuple[str, Callable[[], None]], ...]:
    unicode_collision = archive_with(
        (
            ("Stories/Caf\u00e9.xml", b"<Story/>", ZIP_STORED),
            ("Stories/Cafe\u0301.xml", b"<Story/>", ZIP_STORED),
        )
    )
    parent_conflict = archive_with(
        (
            ("Stories", b"not-a-directory", ZIP_STORED),
            ("Stories/Story.xml", b"<Story/>", ZIP_STORED),
        )
    )
    case_collision = archive_with(
        (
            ("Stories/Story.xml", b"<Story/>", ZIP_STORED),
            ("stories/story.XML", b"<Story/>", ZIP_STORED),
        )
    )
    symlink = ZipInfo("Links/escape")
    symlink.create_system = 3
    symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
    compressed = archive_with((("Stories/Story.xml", b"A" * 4096, ZIP_DEFLATED),))
    marker = b"V02-CRC-PAYLOAD"
    corrupted = bytearray(archive_with((("Stories/Story.xml", marker, ZIP_STORED),)))
    marker_offset = corrupted.find(marker)
    if marker_offset < 0:
        raise AssertionError("could not construct CRC case")
    corrupted[marker_offset] ^= 0x01

    def safe_archive() -> None:
        inspection = inspect_idml(archive_with(), settings)
        if inspection.entry_count != 2:
            raise AssertionError("safe archive inspection count changed")

    def windows_separator() -> None:
        try:
            _validate_name("Stories\\Story.xml")
        except UnsafeArchiveError as exc:
            if exc.code == "invalid_path":
                return
            raise
        raise AssertionError("Windows separator was accepted")

    def safe_xml() -> None:
        root = parse_untrusted_xml("<x><p>caf\u00e9</p></x>".encode())
        if root.findtext("p") != "caf\u00e9":
            raise AssertionError("safe XML content changed")

    def incomplete_references() -> None:
        story = b"""<idPkg:Story
          xmlns:idPkg="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging">
          <Story Self="orphan-story"/>
        </idPkg:Story>"""
        spread = b"""<idPkg:Spread
          xmlns:idPkg="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging">
          <Spread Self="spread"><Page Self="page"/>
            <TextFrame Self="broken-frame" ParentStory="missing-parent"
              PreviousTextFrame="n" NextTextFrame="n"/>
          </Spread>
        </idPkg:Spread>"""
        data = archive_with(
            (
                ("Stories/Story_orphan.xml", story, ZIP_DEFLATED),
                ("Spreads/Spread.xml", spread, ZIP_DEFLATED),
            ),
            designmap=b'<Document Self="doc" StoryList="missing-story orphan-story"/>',
        )
        raw = IdmlParser(settings).parse(data, logical_name="incomplete.idml")
        codes = {issue.code for issue in raw.reading_order_issues}
        expected = {
            "frame_parent_story_missing",
            "story_list_reference_missing",
            "story_without_frame",
        }
        if codes != expected:
            raise AssertionError("incomplete IDML classification changed")

    def malformed_structure() -> None:
        data = archive_with((("Stories/Broken.xml", b"<NotAStory/>", ZIP_DEFLATED),))
        try:
            IdmlParser(settings).parse(data, logical_name="broken.idml")
        except UnsafeArchiveError as exc:
            if exc.code == "invalid_idml_structure":
                return
            raise
        raise AssertionError("malformed IDML structure was accepted")

    return (
        ("safe_minimal_idml", safe_archive),
        (
            "invalid_zip",
            lambda: expect_archive_error(b"not-a-zip", settings, "invalid_zip"),
        ),
        (
            "path_traversal",
            lambda: expect_archive_error(
                archive_with((("../escape.xml", b"x", ZIP_STORED),)),
                settings,
                "path_traversal",
            ),
        ),
        ("windows_separator", windows_separator),
        (
            "unicode_collision",
            lambda: expect_archive_error(unicode_collision, settings, "duplicate_entry"),
        ),
        (
            "case_collision",
            lambda: expect_archive_error(case_collision, settings, "duplicate_entry"),
        ),
        (
            "file_directory_shadowing",
            lambda: expect_archive_error(parent_conflict, settings, "path_type_conflict"),
        ),
        (
            "symlink",
            lambda: expect_archive_error(
                archive_with(((symlink, b"../../outside", ZIP_STORED),)),
                settings,
                "special_entry",
            ),
        ),
        (
            "encrypted_entry",
            lambda: expect_archive_error(
                mark_first_entry_encrypted(archive_with()), settings, "encrypted_entry"
            ),
        ),
        (
            "unsupported_compression",
            lambda: expect_archive_error(
                mark_first_entry_with_unsupported_compression(archive_with()),
                settings,
                "unsupported_compression",
            ),
        ),
        (
            "nested_archive",
            lambda: expect_archive_error(
                archive_with((("Links/payload.zip", b"x", ZIP_STORED),)),
                settings,
                "nested_archive",
            ),
        ),
        (
            "executable_payload",
            lambda: expect_archive_error(
                archive_with((("Resources/payload.exe", b"x", ZIP_STORED),)),
                settings,
                "forbidden_payload",
            ),
        ),
        (
            "entry_count_limit",
            lambda: expect_archive_error(
                archive_with((("Stories/Story.xml", b"<Story/>", ZIP_STORED),)),
                settings.model_copy(update={"zip_max_entries": 2}),
                "too_many_entries",
            ),
        ),
        (
            "expanded_size_limit",
            lambda: expect_archive_error(
                archive_with((("Stories/Story.xml", b"x" * 256, ZIP_STORED),)),
                settings.model_copy(update={"zip_max_uncompressed_bytes": 128}),
                "expanded_too_large",
            ),
        ),
        (
            "compression_ratio_limit",
            lambda: expect_archive_error(
                compressed,
                settings.model_copy(update={"zip_max_ratio": 2}),
                "compression_ratio",
            ),
        ),
        (
            "path_depth_limit",
            lambda: expect_archive_error(
                archive_with((("a/b/c/d.xml", b"<x/>", ZIP_STORED),)),
                settings.model_copy(update={"zip_max_depth": 3}),
                "path_too_deep",
            ),
        ),
        (
            "path_length_limit",
            lambda: expect_archive_error(
                archive_with(((f"Stories/{'a' * 80}.xml", b"<x/>", ZIP_STORED),)),
                settings.model_copy(update={"zip_max_path_bytes": 64}),
                "path_too_long",
            ),
        ),
        (
            "required_entries",
            lambda: expect_archive_error(
                archive_with(include_required=False), settings, "invalid_idml"
            ),
        ),
        (
            "mimetype",
            lambda: expect_archive_error(
                archive_with(mimetype=b"application/zip"), settings, "invalid_mimetype"
            ),
        ),
        (
            "crc_integrity",
            lambda: expect_archive_error(bytes(corrupted), settings, "corrupt_entry"),
        ),
        (
            "ascii_xxe",
            lambda: expect_xml_error(
                b'<!DOCTYPE x [<!ENTITY e SYSTEM "file:///private">]><x>&e;</x>'
            ),
        ),
        (
            "utf16_doctype",
            lambda: expect_xml_error(
                '<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE x><x/>'.encode("utf-16")
            ),
        ),
        ("malformed_binary_xml", lambda: expect_xml_error(b"\x00\x01binary")),
        ("safe_xml", safe_xml),
        ("incomplete_reference_classification", incomplete_references),
        ("malformed_internal_structure", malformed_structure),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--real-idml", type=Path, action="append", default=[])
    arguments = parser.parse_args()
    settings = Settings(environment="test")
    rows: list[dict[str, object]] = []
    for name, execute in security_cases(settings):
        try:
            execute()
        except Exception as exc:
            rows.append({"case": name, "passed": False, "error_type": type(exc).__name__})
        else:
            rows.append({"case": name, "passed": True, "error_type": None})

    synthetic_count = len(rows)
    real_verified = 0
    for index, path in enumerate(arguments.real_idml, start=1):
        try:
            inspect_idml(path.read_bytes(), settings)
        except (OSError, UnsafeArchiveError):
            rows.append(
                {
                    "case": f"real_idml_{index}",
                    "passed": False,
                    "error_type": "real_package_rejected",
                }
            )
        else:
            real_verified += 1
            rows.append({"case": f"real_idml_{index}", "passed": True, "error_type": None})

    approved = all(bool(row["passed"]) for row in rows) and real_verified == len(
        arguments.real_idml
    )
    report = {
        "version": "phase7-v02-gate-1.0",
        "family": "V-02",
        "approved": approved,
        "synthetic_cases": synthetic_count,
        "synthetic_passed": sum(bool(row["passed"]) for row in rows[:synthetic_count]),
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
