"""Administrative bundle selection; no paths, grants or expected values from the client."""

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

try:
    from idml_foundation.services.validation_scope import scope_digest, validate_scope
except ModuleNotFoundError:
    from validation_scope import scope_digest, validate_scope

try:
    from ops.doi_authority_transport import trusted_read
    from ops.doi_package_binding import bound_package_xml
except ModuleNotFoundError:
    from doi_authority_transport import trusted_read
    from doi_package_binding import bound_package_xml

SHA = re.compile("[0-9a-f]{64}")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def instant():
    return datetime.now(timezone.utc)  # noqa: UP017 - VPS host Python 3.10


def read_selection(root, scope, *, reader=trusted_read, now=None):
    scope = validate_scope(scope)
    key = scope_digest(scope)
    root = Path(root)
    raw = reader(root / "bundles" / key / "manifest.json", 32 * 1024)
    manifest = json.loads(raw)
    if (
        set(manifest) != {"version", "authorization_id", "scope", "files"}
        or manifest["version"] != "validation-authority-bundle-1.0"
        or manifest["scope"] != scope
        or not isinstance(manifest["files"], dict)
    ):
        raise ValueError("scoped_authority_bundle_invalid")
    authorization_id = manifest["authorization_id"]
    if not isinstance(authorization_id, str) or str(UUID(authorization_id)) != authorization_id:
        raise ValueError("scoped_authority_grant_invalid")
    grant_raw = reader(root / "authorizations" / (authorization_id + ".json"), 16 * 1024)
    grant = json.loads(grant_raw)
    if (
        set(grant)
        != {
            "version",
            "authorization_id",
            "scope",
            "bundle_sha256",
            "status",
            "destination",
            "decision_id",
            "decision_sha256",
            "issued_at",
            "expires_at",
        }
        or grant["version"] != "validation-authority-grant-1.0"
        or grant["authorization_id"] != authorization_id
        or grant["scope"] != scope
        or grant["status"] != "active"
        or grant["destination"] != "vps"
        or grant["bundle_sha256"] != digest(raw)
        or str(UUID(grant["decision_id"])) != grant["decision_id"]
        or not isinstance(grant["decision_sha256"], str)
        or not SHA.fullmatch(grant["decision_sha256"])
    ):
        raise ValueError("scoped_authority_grant_invalid")
    current = now or instant()
    issued, expires = (datetime.fromisoformat(grant[k]) for k in ("issued_at", "expires_at"))
    if (
        issued.utcoffset() is None
        or expires.utcoffset() is None
        or not issued <= current < expires
        or expires - issued > timedelta(days=30)
    ):
        raise ValueError("scoped_authority_expired")
    required = {"doi-manifest.json", "crossref.json", "editorial-manifest.json", "journal.json"}
    files = manifest["files"]
    if not required <= files.keys() or not 4 <= len(files) <= 68:
        raise ValueError("scoped_authority_files_invalid")
    for name, sha in files.items():
        if name not in required and not re.fullmatch(
            r"[0-9]{4}-[0-9]{4}-[0-9]{4}-[0-9]{3}[0-9X]\.json", name
        ):
            raise ValueError("scoped_authority_files_invalid")
        if not isinstance(sha, str) or not SHA.fullmatch(sha):
            raise ValueError("scoped_authority_files_invalid")
    return manifest, {
        "scope_sha256": key,
        "bundle_sha256": digest(raw),
        "grant_sha256": digest(grant_raw),
    }


def load_selection(root, scope, *, reader=trusted_read, now=None):
    manifest, binding = read_selection(root, scope, reader=reader, now=now)
    current = now or instant()
    data = {}
    for filename, expected in manifest["files"].items():
        raw = reader(Path(root) / "bundles" / binding["scope_sha256"] / filename, 10 * 1024**2)
        if digest(raw) != expected:
            raise ValueError("scoped_authority_snapshot_mismatch")
        data[filename] = raw
    doi = json.loads(data["doi-manifest.json"])
    editorial = json.loads(data["editorial-manifest.json"])
    if (
        doi.get("candidate_sha256") != scope["xml_sha256"]
        or doi.get("package_sha256") != scope["package_sha256"]
        or doi.get("snapshot_sha256") != digest(data["crossref.json"])
        or editorial.get("candidate_sha256") != scope["xml_sha256"]
        or editorial.get("profile_id") != scope["journal_profile_id"]
    ):
        raise ValueError("scoped_authority_candidate_mismatch")
    sources = editorial["sources"]
    if set(data) != {"doi-manifest.json", "crossref.json", "editorial-manifest.json"} | {
        key + ".json" for key, item in sources.items() if item["status"] == "available"
    }:
        raise ValueError("scoped_authority_files_invalid")
    for value in [doi, *sources.values()]:
        collected = datetime.fromisoformat(value["retrieved_at"])
        if collected.utcoffset() is None or not timedelta(0) <= current - collected <= timedelta(
            days=7
        ):
            raise ValueError("scoped_authority_expired")
    return data, binding


def stage_selection(root, scope, candidate, name, *, reader=trusted_read, now=None):
    data, binding = load_selection(root, scope, reader=reader, now=now)
    doi = json.loads(data["doi-manifest.json"])
    payload = candidate.read_bytes()
    if name == "spsvalidator":
        bound_package_xml(payload, doi)
    elif name != "packtools" or digest(payload) != scope["xml_sha256"]:
        raise ValueError("scoped_authority_candidate_mismatch")
    folder = candidate.parent / "scoped-authority"
    folder.mkdir(mode=0o700)
    data["binding.json"] = json.dumps(binding, sort_keys=True).encode()
    for filename, raw in data.items():
        path = folder / filename
        with path.open("xb") as stream:
            stream.write(raw)
        path.chmod(0o444)
    return folder, binding


def mount_selection(arguments, folder):
    mounts = []
    for path in sorted(folder.iterdir()):
        if any(c in str(path) for c in (",", "\r", "\n")):
            raise ValueError("scoped_authority_mount_invalid")
        mounts.extend(["--mount", f"type=bind,src={path},dst=/sources/{path.name},readonly"])
    index = arguments.index("--entrypoint=python")
    return arguments[:index] + mounts + arguments[index:]
