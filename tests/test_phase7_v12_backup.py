import hashlib
import io
import tarfile

import pytest

from ops.verify_backup import PAYLOADS, restore_tar, verify_checksums


def backup(tmp_path):
    lines = []
    for name in PAYLOADS:
        data = b"synthetic"
        (tmp_path / name).write_bytes(data)
        lines.append(f"{hashlib.sha256(data).hexdigest()}  /historical/path/{name}")
    (tmp_path / "SHA256SUMS").write_text("\n".join(lines))
    return tmp_path


def test_manifest_uses_local_payloads_not_recorded_paths(tmp_path):
    assert verify_checksums(backup(tmp_path))["checksums_verified"]


@pytest.mark.parametrize("kind", ["mismatch", "missing", "duplicate", "budget"])
def test_manifest_fails_closed(tmp_path, kind):
    backup(tmp_path)
    if kind == "mismatch":
        (tmp_path / PAYLOADS[0]).write_bytes(b"damaged")
    elif kind == "missing":
        (tmp_path / PAYLOADS[0]).unlink()
    elif kind == "duplicate":
        manifest = tmp_path / "SHA256SUMS"
        manifest.write_text(manifest.read_text() + "\n" + manifest.read_text().splitlines()[0])
    with pytest.raises(ValueError):
        verify_checksums(tmp_path, max_bytes=1 if kind == "budget" else 1000)


def make_tar(tmp_path, name="./nested/data", kind=tarfile.REGTYPE, size=4):
    archive = tmp_path / "test.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        member = tarfile.TarInfo(name)
        member.type = kind
        member.linkname = "../escape"
        member.size = size if kind == tarfile.REGTYPE else 0
        tar.addfile(member, io.BytesIO(b"a" * member.size))
    return archive


def test_safe_extract_preserves_payload(tmp_path):
    target = tmp_path / "restore"
    result = restore_tar(make_tar(tmp_path), target)
    assert result == {"files": 1, "bytes": 4}
    assert (target / "nested/data").read_bytes() == b"aaaa"


@pytest.mark.parametrize("name", ["../escape", "/absolute", "nested/../../escape", "a\\b"])
def test_archive_paths_rejected(tmp_path, name):
    with pytest.raises(ValueError):
        restore_tar(make_tar(tmp_path, name=name), tmp_path / "restore")


@pytest.mark.parametrize("kind", [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE])
def test_special_members_rejected(tmp_path, kind):
    with pytest.raises(ValueError):
        restore_tar(make_tar(tmp_path, kind=kind), tmp_path / "restore")


def test_archive_expansion_budget(tmp_path):
    with pytest.raises(ValueError, match="archive_size_budget"):
        restore_tar(make_tar(tmp_path), tmp_path / "restore", max_bytes=3)


def test_existing_destination_never_overwritten(tmp_path):
    with pytest.raises(ValueError, match="destination_exists"):
        restore_tar(make_tar(tmp_path), tmp_path)
