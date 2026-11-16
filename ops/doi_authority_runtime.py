"""Scoped native DOI lookup replacement: verified metadata, not a validation bypass."""

import hashlib
import json
from contextlib import contextmanager
from datetime import UTC, datetime

try:
    from idml_foundation.release.doi_snapshot import bind_doi_snapshot
except ModuleNotFoundError:
    from doi_snapshot import bind_doi_snapshot


@contextmanager
def authority_lookup(utils, candidate, folder, *, package=None):
    if not folder.exists():
        yield
        return
    manifest_path = folder / "manifest.json"
    snapshot_path = folder / "crossref.json"
    if manifest_path.stat().st_size > 8192 or snapshot_path.stat().st_size > 10 * 1024**2:
        raise ValueError("authority_file_budget")
    manifest = json.loads(manifest_path.read_bytes())
    if manifest.get("authority") != "https://api.crossref.org/works/":
        raise ValueError("authority_origin_invalid")
    if package is not None:
        try:
            from ops.doi_package_binding import bound_package_xml
        except ModuleNotFoundError:
            from doi_package_binding import bound_package_xml
        candidate = bound_package_xml(package, manifest)
    bound = bind_doi_snapshot(
        candidate=candidate,
        snapshot=snapshot_path.read_bytes(),
        expected_candidate_sha256=manifest["candidate_sha256"],
        expected_snapshot_sha256=manifest["snapshot_sha256"],
        retrieved_at=datetime.fromisoformat(manifest["retrieved_at"]),
        now=datetime.now(UTC),
    )
    digest = hashlib.sha256(candidate).hexdigest()
    original = utils.get_doi_information
    try:
        utils.get_doi_information = lambda doi: bound.lookup(
            doi, candidate_sha256=digest, now=datetime.now(UTC)
        )
        yield
    finally:
        utils.get_doi_information = original
