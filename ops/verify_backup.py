"""Bounded backup verification; no secret-bearing names/content in the result."""

import hashlib
import re
import tarfile
from pathlib import Path, PurePosixPath

PAYLOADS = ("database.dump", "artifacts.tar.gz", "openclaw-state.tar.gz")


def verify_checksums(directory, *, max_bytes=256 * 1024**2):
    directory = directory.resolve(strict=True)
    manifest = directory / "SHA256SUMS"
    if manifest.is_symlink() or manifest.stat().st_size > 16384:
        raise ValueError("invalid_manifest")
    expected = {}
    for line in manifest.read_text().splitlines():
        match = re.fullmatch(r"([0-9a-f]{64}) [ *](.+)", line)
        if not match:
            raise ValueError("invalid_manifest")
        name = Path(match[2]).name
        # Historical manifests contain absolute paths; never follow those paths.
        if name not in PAYLOADS or name in expected:
            raise ValueError("invalid_manifest")
        expected[name] = match[1]
    if set(expected) != set(PAYLOADS):
        raise ValueError("incomplete_manifest")
    total = 0
    for name in PAYLOADS:
        path = directory / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("unsafe_payload")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError("compressed_budget")
                digest.update(chunk)
        if digest.hexdigest() != expected[name]:
            raise ValueError("checksum_mismatch")
    return {"checksums_verified": True, "payload_bytes": total, "payload_sha256": expected}


def restore_tar(archive, destination, *, max_bytes=128 * 1024**2, max_entries=10000):
    """Extract regular files only, to a newly-created private directory, without tar metadata."""
    if destination.exists():
        raise ValueError("destination_exists")
    destination.mkdir(mode=0o700)
    total, count, names = 0, 0, set()
    with tarfile.open(archive, "r:gz") as tar:
        for index, member in enumerate(tar):
            if index >= max_entries:
                raise ValueError("archive_entry_budget")
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or "\\" in member.name:
                raise ValueError("unsafe_archive_path")
            if path.as_posix() in names or not (member.isdir() or member.isfile()):
                raise ValueError("unsafe_archive_member")
            names.add(path.as_posix())
            target = destination.joinpath(*path.parts)
            if not target.resolve().is_relative_to(destination.resolve()):
                raise ValueError("unsafe_archive_path")
            if member.isdir():
                target.mkdir(mode=0o700, parents=True, exist_ok=True)
                continue
            total += member.size
            if total > max_bytes:
                raise ValueError("archive_size_budget")
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            source = tar.extractfile(member)
            if source is None:
                raise ValueError("unreadable_member")
            with source, target.open("xb") as output:
                while chunk := source.read(1024 * 1024):
                    output.write(chunk)
            target.chmod(0o600)
            count += 1
    return {"files": count, "bytes": total}
