#!/usr/bin/env python3
"""Build a private fail-closed formal metadata catalog from a Crossref snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from idml_foundation.pipeline.service import DeterministicPipeline
from idml_foundation.release.formal_metadata import build_formal_metadata_authority_catalog


def _private_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as target:
        json.dump(value, target, ensure_ascii=False, indent=2)
        target.write("\n")
    os.replace(temporary, path)
    os.chmod(path, 0o600)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--idml", type=Path, required=True)
    parser.add_argument("--crossref-response", type=Path, required=True)
    parser.add_argument("--formal-reference-xml", type=Path)
    parser.add_argument("--corpus-id", required=True)
    parser.add_argument("--catalog-output", type=Path, required=True)
    parser.add_argument("--report-output", type=Path, required=True)
    arguments = parser.parse_args()

    source = arguments.idml.read_bytes()
    response = arguments.crossref_response.read_bytes()
    article = DeterministicPipeline().run(source, logical_name=arguments.idml.name).canonical
    catalog, report = build_formal_metadata_authority_catalog(
        article=article,
        source_idml_sha256=hashlib.sha256(source).hexdigest(),
        crossref_response=response,
        corpus_id=arguments.corpus_id,
        formal_reference_xml=(
            arguments.formal_reference_xml.read_bytes()
            if arguments.formal_reference_xml is not None
            else None
        ),
    )
    _private_json(arguments.catalog_output, catalog.model_dump(mode="json"))
    arguments.report_output.parent.mkdir(parents=True, exist_ok=True)
    arguments.report_output.write_text(
        json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"catalog_id": catalog.catalog_id, "publication_fields": 3}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
