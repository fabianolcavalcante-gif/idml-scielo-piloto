"""Safely vendor the pinned official JATS 1.3 MathML3 DTD bundle."""

import argparse
import hashlib
import json
import os
import stat
import zipfile
from pathlib import Path, PurePosixPath

EXPECTED_ARCHIVE_SHA256 = "41ddeaf6eeb04eb64244e9894212e0aaeafdbb9114d20602da2d855ad39b9b7b"
SOURCE_URL = (
    "https://public.nlm.nih.gov/projects/jats/publishing/1.3/JATS-Publishing-1-3-MathML3-DTD.zip"
)
UPSTREAM_ROOT = PurePosixPath("JATS-Publishing-1-3-MathML3-DTD")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    archive_data = args.archive.read_bytes()
    if digest(archive_data) != EXPECTED_ARCHIVE_SHA256:
        raise SystemExit("official JATS archive hash mismatch")
    if args.destination.exists():
        raise SystemExit("destination already exists")
    args.destination.mkdir(parents=True)

    files: dict[str, str] = {}
    with zipfile.ZipFile(args.archive) as source:
        for info in source.infolist():
            path = PurePosixPath(info.filename)
            mode = (info.external_attr >> 16) & 0xFFFF
            if path.is_absolute() or ".." in path.parts or "\\" in info.filename:
                raise SystemExit("unsafe path in JATS archive")
            if stat.S_IFMT(mode) not in {0, stat.S_IFREG, stat.S_IFDIR}:
                raise SystemExit("special entry in JATS archive")
            if not path.parts or path.parts[0] != str(UPSTREAM_ROOT):
                continue
            relative = PurePosixPath(*path.parts[1:])
            if not relative.parts or relative.name == ".DS_Store" or relative.name.startswith("._"):
                continue
            target = args.destination.joinpath(*relative.parts)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            data = source.read(info)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            files[relative.as_posix()] = digest(data)

    provenance = {
        "source_url": SOURCE_URL,
        "archive_sha256": EXPECTED_ARCHIVE_SHA256,
        "retrieved_at": "2026-08-24",
        "files": dict(sorted(files.items())),
    }
    source_path = args.destination / "SOURCE.json"
    source_path.write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.chmod(source_path, 0o644)
    print(f"vendored {len(files)} JATS files")


if __name__ == "__main__":
    main()
