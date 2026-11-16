"""Production-shaped candidate adapter using ONLY server-mounted, bound evidence."""

import contextlib
import hashlib
import io
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

from affiliation_compat import install
from doi_model_compat import install as install_doi
from doi_package_binding import bound_package_xml
from doi_snapshot import bind_doi_snapshot
from doi_validation_evidence import observe_registered_doi
from editorial_authority import BoundEditorialAuthority, parse_candidate
from editorial_authority_runtime import editorial_parameters
from packtools.sps.validation import article_doi, utils, xml_validations


def read_source(name, limit):
    path = Path("/sources") / name
    if path.is_symlink() or not 0 < path.stat().st_size <= limit:
        raise ValueError("scoped_source_invalid")
    return path.read_bytes()


def main():
    logging.disable(logging.CRITICAL)
    install()
    install_doi()
    path = Path(sys.argv[1])
    if not 0 < path.stat().st_size <= 100 * 1024**2:
        raise ValueError("scoped_candidate_budget")
    payload = path.read_bytes()
    manifest = json.loads(read_source("doi-manifest.json", 8192))
    if manifest.get("authority") != "https://api.crossref.org/works/":
        raise ValueError("scoped_doi_origin_invalid")
    xml = bound_package_xml(payload, manifest) if path.suffix == ".zip" else payload
    crossref = bind_doi_snapshot(
        candidate=xml,
        snapshot=read_source("crossref.json", 10 * 1024**2),
        expected_candidate_sha256=manifest["candidate_sha256"],
        expected_snapshot_sha256=manifest["snapshot_sha256"],
        retrieved_at=datetime.fromisoformat(manifest["retrieved_at"]),
        now=datetime.now(UTC),
    )
    editorial = BoundEditorialAuthority(
        xml,
        json.loads(read_source("editorial-manifest.json", 32 * 1024)),
        lambda name: read_source(name, 1024**2),
        now=datetime.now(UTC),
        crossref=crossref,
    )
    if path.suffix == ".zip":
        import spsvalidator_pinned_adapter as adapter
        from sps_rendition_compat import validate_package

        adapter.validate_sps_zip = validate_package
    else:
        import packtools_pinned_adapter as adapter
    original = utils.get_doi_information
    utils.get_doi_information = lambda doi: crossref.lookup(
        doi, candidate_sha256=hashlib.sha256(xml).hexdigest(), now=datetime.now(UTC)
    )
    stdout = io.StringIO()
    try:
        with (
            editorial_parameters(xml_validations, editorial) as checks,
            observe_registered_doi(article_doi) as doi_checks,
            contextlib.redirect_stdout(stdout),
        ):
            result = adapter.main()
            if result:
                raise ValueError("scoped_native_adapter_failed")
    finally:
        utils.get_doi_information = original
    envelope = json.loads(stdout.getvalue())
    tree = parse_candidate(xml)
    expected_orcid = len(
        tree.xpath('.//contrib[not(anonymous) and name]/contrib-id[@contrib-id-type="orcid"]')
    )
    expected_sections = len(
        tree.xpath('.//article-categories/subj-group[@subj-group-type="heading"]/subject')
    )
    checks["doi"] = doi_checks
    envelope["result"]["authority_evidence"] = {
        "version": "scoped-authority-evidence-1.0",
        "binding": json.loads(read_source("binding.json", 8192)),
        "checks": checks,
        "expected": {"doi": 1, "issue": 1, "section": expected_sections, "orcid": expected_orcid},
    }
    print(json.dumps(envelope, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # The broker reports failure; no native traceback/article content is emitted.
        raise SystemExit(1) from None
