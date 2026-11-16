"""Local-only Crossref snapshot + native DOI comparison. No gold or remote upload."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen

from lxml import etree
from packtools.sps.validation import utils
from packtools.sps.validation.article_doi import ArticleDoiValidation

from idml_foundation.release.doi_snapshot import bind_doi_snapshot

ROOT = Path(__file__).resolve().parents[1]


def main():
    path = ROOT / "benchmarks/private/output/h1-country-codes-v1/esa-e20240086/candidate.xml"
    candidate = path.read_bytes()
    expected = "7081d302358f8c022114a0ebf568372af43e115bda38a748cc7c2ebbc1494ad0"
    if hashlib.sha256(candidate).hexdigest() != expected:
        raise ValueError("candidate differs from qualification")
    tree = etree.fromstring(candidate, etree.XMLParser(resolve_entities=False, no_network=True))
    doi = tree.xpath("string(front/article-meta/article-id[@pub-id-type='doi'])")
    url = "https://api.crossref.org/works/" + quote(doi, safe="")
    with urlopen(url, timeout=30) as response:
        if response.url != url:
            raise ValueError("unexpected authority redirect")
        snapshot = response.read(10 * 1024**2 + 1)
    retrieved = datetime.now(UTC)
    digest = hashlib.sha256(snapshot).hexdigest()
    bound = bind_doi_snapshot(
        candidate=candidate,
        snapshot=snapshot,
        expected_candidate_sha256=expected,
        expected_snapshot_sha256=digest,
        retrieved_at=retrieved,
        now=retrieved,
    )
    original = utils.get_doi_information
    try:
        utils.get_doi_information = lambda identifier: bound.lookup(
            identifier, candidate_sha256=expected, now=datetime.now(UTC)
        )
        rows = list(ArticleDoiValidation(tree, {}).validate_doi_registered())
        mismatched = json.loads(snapshot)
        mismatched["message"]["title"] = ["Unrelated synthetic control"]
        mismatched["message"]["author"] = [{"given": "Synthetic", "family": "Unrelated"}]
        utils.get_doi_information = lambda _: mismatched
        negative = list(ArticleDoiValidation(tree, {}).validate_doi_registered())
        if len(negative) != 1 or negative[0].get("response") == "OK":
            raise ValueError("native validator accepted unrelated metadata")
    finally:
        utils.get_doi_information = original
    if len(rows) != 1:
        raise ValueError("expected one native DOI comparison")
    result = rows[0]
    folder = ROOT / "benchmarks/private/output/h1-doi-snapshot-v1"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "crossref.json").write_bytes(snapshot)
    manifest = {
        "candidate_sha256": expected,
        "snapshot_sha256": digest,
        "retrieved_at": retrieved.isoformat(),
        "authority": "https://api.crossref.org/works/",
    }
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    report = {
        "version": "h1-doi-snapshot-local-1.0",
        **manifest,
        "scope": "local installed runtime; isolated VPS integration pending",
        "registered_metadata_present": bool(result.get("data", {}).get("registered")),
        "native_response": result.get("response"),
        "native_comparison_passed": result.get("response") == "OK",
        "synthetic_metadata_mismatch_rejected": True,
        "xml_changed": False,
        "gold_read": False,
        "snapshot_sent_to_vps": False,
        "formal_validation_passed": False,
    }
    (ROOT / "benchmarks/qualification/reports/h1-doi-snapshot-local-v1.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report))


if __name__ == "__main__":
    main()
