"""Admin-registry-only authority staging; never accept paths from socket clients."""

import hashlib
import json
import os
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path


def trusted_read(path, limit):
    path = Path(path)
    if not path.is_absolute():
        raise ValueError("authority_absolute_path_required")
    for item in (path, *path.parents):
        info = item.lstat()
        if stat.S_ISLNK(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError("authority_untrusted_path")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= limit:
            raise ValueError("authority_file_budget")
        value = stream.read(limit + 1)
    if not 0 < len(value) <= limit:
        raise ValueError("authority_file_budget")
    return value


def stage_authority(spec, candidate, *, reader=trusted_read, now=None):
    """Return private staged directory. Missing configuration preserves legacy mode."""
    config = spec.get("doi_authority")
    if config is None:
        return None
    if (
        spec["name"] not in {"packtools", "spsvalidator"}
        or not isinstance(config, dict)
        or set(config) != {"manifest_path", "manifest_sha256", "snapshot_path"}
    ):
        raise ValueError("authority_config_invalid")
    manifest_bytes = reader(config["manifest_path"], 8192)
    if hashlib.sha256(manifest_bytes).hexdigest() != config["manifest_sha256"]:
        raise ValueError("authority_manifest_mismatch")
    manifest = json.loads(manifest_bytes)
    fields = {"candidate_sha256", "snapshot_sha256", "retrieved_at", "authority"}
    if spec["name"] == "spsvalidator":
        fields.add("package_sha256")
    if (
        not isinstance(manifest, dict)
        or set(manifest) != fields
        or manifest["authority"] != "https://api.crossref.org/works/"
    ):
        raise ValueError("authority_manifest_invalid")
    retrieved = datetime.fromisoformat(manifest["retrieved_at"])
    current = now or datetime.now(timezone.utc)  # noqa: UP017 - VPS host Python 3.10
    if retrieved.utcoffset() is None or not timedelta(0) <= current - retrieved <= timedelta(
        days=7
    ):
        raise ValueError("authority_expired")
    payload = candidate.read_bytes()
    if spec["name"] == "spsvalidator":
        try:
            from ops.doi_package_binding import bound_package_xml
        except ModuleNotFoundError:
            from doi_package_binding import bound_package_xml
        bound_package_xml(payload, manifest)
    elif hashlib.sha256(payload).hexdigest() != manifest["candidate_sha256"]:
        raise ValueError("authority_candidate_mismatch")
    snapshot = reader(config["snapshot_path"], 10 * 1024**2)
    if hashlib.sha256(snapshot).hexdigest() != manifest["snapshot_sha256"]:
        raise ValueError("authority_snapshot_mismatch")
    folder = candidate.parent / "doi-authority"
    folder.mkdir(mode=0o700)
    for name, value in (("manifest.json", manifest_bytes), ("crossref.json", snapshot)):
        path = folder / name
        with path.open("xb") as stream:
            stream.write(value)
        path.chmod(0o444)
    return folder


def mount_arguments(arguments, folder):
    if folder is None:
        return arguments
    index = arguments.index("--entrypoint=python")
    mounts = []
    for name in ("manifest.json", "crossref.json"):
        path = folder / name
        if any(char in str(path) for char in (",", "\n", "\r")):
            raise ValueError("authority_mount_path_invalid")
        mounts.extend(["--mount", f"type=bind,src={path},dst=/authority/{name},readonly"])
    return arguments[:index] + mounts + arguments[index:]
