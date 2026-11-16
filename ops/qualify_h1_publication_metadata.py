"""Authorized metadata correction for one development article; never read the gold XML."""

import hashlib
import json
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen

from idml_foundation.pipeline.service import DeterministicPipeline
from idml_foundation.release.formal_metadata import build_formal_metadata_authority_catalog
from idml_foundation.services.enrichment import KINDS
from ops.qualify_h1_enrichment import CASES

ROOT = Path(__file__).resolve().parents[1]


def main():
    case, filename, catalogs, expected = CASES[0]
    source = ROOT / filename
    data = source.read_bytes()
    options = {
        kind: KINDS[kind].model_validate_json(
            (ROOT / "benchmarks/private/output" / name).read_bytes()
        )
        for kind, name in catalogs.items()
    }
    before = DeterministicPipeline(**options).run(data, logical_name=source.name)
    if hashlib.sha256(before.xml).hexdigest() != expected:
        raise ValueError("source baseline mismatch")
    dois = [
        item.value.value
        for item in before.canonical.front.article_identifiers
        if item.kind == "doi" and item.value.value
    ]
    if len(dois) != 1:
        raise ValueError("unique source DOI required")
    url = "https://api.crossref.org/works/" + quote(dois[0], safe="")
    with urlopen(url, timeout=30) as response:
        if not response.url.startswith("https://api.crossref.org/"):
            raise ValueError("unexpected metadata host")
        snapshot = response.read(10 * 1024**2 + 1)
    catalog, authority = build_formal_metadata_authority_catalog(
        article=before.canonical,
        source_idml_sha256=hashlib.sha256(data).hexdigest(),
        crossref_response=snapshot,
        corpus_id=case,
    )
    after = DeterministicPipeline(**options, formal_metadata_catalog=catalog).run(
        data, logical_name=source.name
    )
    folder = ROOT / "benchmarks/private/output/h1-publication-metadata-v1"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "crossref-snapshot.json").write_bytes(snapshot)
    (folder / "formal-metadata-catalog.json").write_text(
        catalog.model_dump_json(indent=2), encoding="utf-8"
    )
    (folder / "candidate.xml").write_bytes(after.xml)
    report = {
        "version": "h1-publication-metadata-1.0",
        "corpus_id": case,
        "before_xml_sha256": expected,
        "after_xml_sha256": hashlib.sha256(after.xml).hexdigest(),
        "catalog_id": catalog.catalog_id,
        "crossref_response_sha256": authority["crossref_response_sha256"],
        "publication_date_precision": "year",
        "offline_valid": after.validation.valid,
        "gold_read": False,
        "human_review_required": True,
        "external_validation_passed": False,
    }
    (ROOT / "benchmarks/qualification/reports/h1-publication-metadata-v1.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report))


if __name__ == "__main__":
    main()
