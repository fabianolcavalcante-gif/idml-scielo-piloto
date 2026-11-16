import stat
import unicodedata
import zlib
from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePosixPath
from zipfile import ZIP_DEFLATED, ZIP_STORED, BadZipFile, LargeZipFile, ZipFile, ZipInfo

from idml_foundation.ingest.xml_security import MAX_IDML_XML_BYTES, MAX_UNTRUSTED_XML_BYTES
from idml_foundation.settings import Settings

NESTED_ARCHIVE_SUFFIXES = {
    ".7z",
    ".bz2",
    ".gz",
    ".idml",
    ".rar",
    ".tar",
    ".tgz",
    ".xz",
    ".zip",
}

FORBIDDEN_PAYLOAD_SUFFIXES = {
    ".bat",
    ".cmd",
    ".com",
    ".dll",
    ".exe",
    ".js",
    ".msi",
    ".ps1",
    ".scr",
}


class UnsafeArchiveError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ArchiveInspection:
    entry_count: int
    total_uncompressed_bytes: int
    max_compression_ratio: float


def _validate_name(name: str) -> PurePosixPath:
    if (
        "\x00" in name
        or "\\" in name
        or "//" in name
        or any(unicodedata.category(character) in {"Cc", "Cf", "Cs"} for character in name)
    ):
        raise UnsafeArchiveError("invalid_path", "archive contains an invalid path")
    raw_parts = name.rstrip("/").split("/")
    if not raw_parts or any(part in {"", ".", ".."} for part in raw_parts):
        raise UnsafeArchiveError("path_traversal", "archive contains path traversal")
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise UnsafeArchiveError("path_traversal", "archive contains path traversal")
    if path.parts[0].endswith(":"):
        raise UnsafeArchiveError("absolute_path", "archive contains an absolute path")
    return path


def _canonical_name(path: PurePosixPath) -> str:
    return unicodedata.normalize("NFKC", path.as_posix().rstrip("/")).casefold()


def _validate_entry_type(info: ZipInfo) -> None:
    mode = (info.external_attr >> 16) & 0xFFFF
    if not mode:
        return
    kind = stat.S_IFMT(mode)
    if kind not in {0, stat.S_IFREG, stat.S_IFDIR}:
        raise UnsafeArchiveError("special_entry", "symlinks and special entries are forbidden")


def inspect_idml(data: bytes, settings: Settings) -> ArchiveInspection:
    if len(data) > settings.upload_max_bytes:
        raise UnsafeArchiveError("upload_too_large", "upload exceeds configured size limit")
    try:
        archive = ZipFile(BytesIO(data))
    except (BadZipFile, LargeZipFile) as exc:
        raise UnsafeArchiveError("invalid_zip", "IDML is not a valid ZIP package") from exc

    with archive:
        infos = archive.infolist()
        if len(infos) > settings.zip_max_entries:
            raise UnsafeArchiveError("too_many_entries", "archive has too many entries")

        names: set[str] = set()
        exact_names: set[str] = set()
        entry_types: dict[str, str] = {}
        total = 0
        xml_total = 0
        max_ratio = 1.0
        for info in infos:
            path = _validate_name(info.filename)
            normalized = _canonical_name(path)
            if normalized in names:
                raise UnsafeArchiveError("duplicate_entry", "archive has duplicate entry names")
            names.add(normalized)
            exact_names.add(path.as_posix())
            _validate_entry_type(info)
            if len(path.parts) > settings.zip_max_depth:
                raise UnsafeArchiveError("path_too_deep", "archive path exceeds depth limit")
            if len(info.filename.encode("utf-8")) > settings.zip_max_path_bytes:
                raise UnsafeArchiveError("path_too_long", "archive path exceeds length limit")
            kind = "directory" if info.is_dir() else "file"
            prefixes = [
                "/".join(normalized.split("/")[:index]) for index in range(1, len(path.parts))
            ]
            if any(entry_types.get(prefix) == "file" for prefix in prefixes):
                raise UnsafeArchiveError(
                    "path_type_conflict", "archive path conflicts with a file entry"
                )
            if kind == "file" and any(name.startswith(f"{normalized}/") for name in entry_types):
                raise UnsafeArchiveError(
                    "path_type_conflict", "archive file conflicts with a directory entry"
                )
            entry_types[normalized] = kind
            if info.flag_bits & 0x1:
                raise UnsafeArchiveError("encrypted_entry", "encrypted entries are forbidden")
            if info.compress_type not in {ZIP_STORED, ZIP_DEFLATED}:
                raise UnsafeArchiveError(
                    "unsupported_compression", "archive uses unsupported compression"
                )
            total += info.file_size
            if total > settings.zip_max_uncompressed_bytes:
                raise UnsafeArchiveError("expanded_too_large", "expanded archive exceeds limit")
            if path.suffix.casefold() == ".xml" and info.file_size > MAX_UNTRUSTED_XML_BYTES:
                raise UnsafeArchiveError("unsafe_xml", "XML exceeds the ingestion size limit")
            if path.suffix.casefold() == ".xml":
                xml_total += info.file_size
                if xml_total > MAX_IDML_XML_BYTES:
                    raise UnsafeArchiveError("expanded_xml_too_large", "combined XML exceeds limit")
            if info.filename == "mimetype" and info.file_size != len(
                b"application/vnd.adobe.indesign-idml-package"
            ):
                raise UnsafeArchiveError("invalid_mimetype", "unexpected IDML mimetype size")
            ratio = info.file_size / max(info.compress_size, 1)
            max_ratio = max(max_ratio, ratio)
            if ratio > settings.zip_max_ratio and info.file_size > 1024:
                raise UnsafeArchiveError("compression_ratio", "suspicious compression ratio")
            if path.suffix.casefold() in NESTED_ARCHIVE_SUFFIXES:
                raise UnsafeArchiveError("nested_archive", "nested archives are forbidden")
            if path.suffix.casefold() in FORBIDDEN_PAYLOAD_SUFFIXES:
                raise UnsafeArchiveError(
                    "forbidden_payload", "archive contains a forbidden executable payload"
                )

        required = {"mimetype", "designmap.xml"}
        if not required.issubset(exact_names):
            raise UnsafeArchiveError("invalid_idml", "required IDML entries are missing")
        try:
            bad_entry = archive.testzip()
        except (BadZipFile, EOFError, RuntimeError, zlib.error) as exc:
            raise UnsafeArchiveError("corrupt_entry", "archive contains a corrupt entry") from exc
        if bad_entry is not None:
            raise UnsafeArchiveError("corrupt_entry", "archive contains a corrupt entry")
        try:
            mime = archive.read("mimetype")
        except (BadZipFile, KeyError, RuntimeError) as exc:
            raise UnsafeArchiveError("invalid_idml", "IDML mimetype cannot be read") from exc
        if mime != b"application/vnd.adobe.indesign-idml-package":
            raise UnsafeArchiveError("invalid_mimetype", "unexpected IDML mimetype")

    return ArchiveInspection(
        entry_count=len(infos),
        total_uncompressed_bytes=total,
        max_compression_ratio=max_ratio,
    )
