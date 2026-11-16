"""Supervisor resolves committed admin consent, then binds fresh public evidence."""

import json
import os
import subprocess
import tempfile
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

from idml_foundation.services.validation_scope import validate_scope
from ops.article_authority_collect import collect
from ops.doi_package_binding import bound_package_xml
from ops.scoped_authority_transport import digest, load_selection, scope_digest, trusted_read

API_CONTAINER = "idml-development-api-1"  # Fixed managed service; not configurable by a request.


def decision(scope):
    scope = validate_scope(scope)
    result = subprocess.run(  # noqa: S603 - fixed supervisor command; scoped JSON on stdin
        [
            "/usr/bin/docker",
            "exec",
            "-i",
            "--user",
            "10001:10001",
            API_CONTAINER,
            "python",
            "-m",
            "idml_foundation.services.article_source_access",
        ],
        input=json.dumps(scope).encode(),
        capture_output=True,
        timeout=15,
        check=False,
    )
    if result.returncode or not 0 < len(result.stdout) <= 4096:
        raise ValueError("article_source_consent_unavailable")
    selected = json.loads(result.stdout)
    if (
        set(selected) != {"version", "decision_id", "decision_sha256", "scope", "expires_at"}
        or selected["version"] != "public-validation-sources-1.0"
        or selected["scope"] != scope
        or str(UUID(selected["decision_id"])) != selected["decision_id"]
        or len(selected["decision_sha256"]) != 64
    ):
        raise ValueError("article_source_consent_invalid")
    expires = datetime.fromisoformat(selected["expires_at"])
    if expires.utcoffset() is None or expires <= datetime.now(timezone.utc):  # noqa: UP017
        raise ValueError("article_source_consent_expired")
    return selected


@contextmanager
def publication_lock(root):
    path = root / ".provision.lock"
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        yield
    finally:
        os.close(descriptor)
        path.unlink()


def prepare(root, scope, candidate, name):
    """Single broker process; a host lock also prevents another provisioner racing it."""
    root = Path(root)
    approved = decision(scope)  # Refuse before reading or fetching public records.
    payload = candidate.read_bytes()
    xml = (
        bound_package_xml(
            payload,
            dict(candidate_sha256=scope["xml_sha256"], package_sha256=scope["package_sha256"]),
        )
        if name == "spsvalidator"
        else payload
    )
    if name not in {"spsvalidator", "packtools"} or digest(xml) != scope["xml_sha256"]:
        raise ValueError("runtime_source_candidate_mismatch")
    with publication_lock(root):
        key = scope_digest(scope)
        target = root / "bundles" / key
        try:
            load_selection(root, scope)
            manifest = json.loads(trusted_read(target / "manifest.json", 32768))
            grant = json.loads(
                trusted_read(
                    root / "authorizations" / (manifest["authorization_id"] + ".json"), 16384
                )
            )
            if all(grant[k] == approved[k] for k in ("decision_id", "decision_sha256")):
                return approved
        except FileNotFoundError:
            pass
        except ValueError as error:
            # An expired record is refreshable; corrupt/tampered data is never silently replaced.
            if str(error) != "scoped_authority_expired":
                raise
        if sum(1 for _ in (root / "authorizations").glob("*.json")) >= 128:
            raise ValueError("article_source_retention_budget")
        files = collect(xml, scope)
        if decision(scope) != approved:
            raise ValueError("article_source_consent_changed")
        identifier = str(uuid4())
        now = datetime.now(timezone.utc)  # noqa: UP017
        expires = min(now + timedelta(days=1), datetime.fromisoformat(approved["expires_at"]))
        manifest = dict(
            version="validation-authority-bundle-1.0",
            authorization_id=identifier,
            scope=scope,
            files={n: digest(raw) for n, raw in files.items()},
        )
        raw_manifest = json.dumps(manifest, sort_keys=True).encode()
        grant = dict(
            version="validation-authority-grant-1.0",
            authorization_id=identifier,
            scope=scope,
            bundle_sha256=digest(raw_manifest),
            status="active",
            destination="vps",
            decision_id=approved["decision_id"],
            decision_sha256=approved["decision_sha256"],
            issued_at=now.isoformat(),
            expires_at=expires.isoformat(),
        )
        raw_grant = json.dumps(grant, sort_keys=True).encode()
        with tempfile.TemporaryDirectory(prefix="runtime-source-", dir=root) as temporary:
            staging = Path(temporary)
            (staging / "authorizations").mkdir(mode=0o700)
            (staging / "authorizations" / (identifier + ".json")).write_bytes(raw_grant)
            bundle = staging / "bundles" / key
            bundle.mkdir(parents=True, mode=0o700)
            (bundle / "manifest.json").write_bytes(raw_manifest)
            for filename, raw in files.items():
                # Names are checked by the existing contract before any file write.
                if filename not in {
                    "crossref.json",
                    "doi-manifest.json",
                    "editorial-manifest.json",
                    "journal.json",
                }:
                    from idml_foundation.services.xpm_query_targets import endpoint

                    endpoint("orcid", filename.removesuffix(".json"))
                    if not filename.endswith(".json"):
                        raise ValueError("runtime_source_name_invalid")
                (bundle / filename).write_bytes(raw)
            for path in [*bundle.iterdir(), *(staging / "authorizations").iterdir()]:
                path.chmod(0o600)
            load_selection(staging, scope)
            if decision(scope) != approved:
                raise ValueError("article_source_consent_changed")
            grant_path = root / "authorizations" / (identifier + ".json")
            with grant_path.open("xb") as stream:
                os.chmod(grant_path, 0o600)
                stream.write(raw_grant)
            historical = None
            if target.exists():
                history = root / "history"
                history.mkdir(mode=0o700, exist_ok=True)
                historical = history / (key + "-" + identifier)
                target.rename(historical)
            try:
                bundle.rename(target)
            except BaseException:
                if historical is not None:
                    historical.rename(target)
                raise
    return approved
