from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from idml_foundation.pipeline.service import DeterministicPipeline
from idml_foundation.release.editorial_enrichment import (
    build_editorial_enrichment_catalog,
)


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
    parser.add_argument("--approved-xml", type=Path, required=True)
    parser.add_argument("--corpus-id", required=True)
    parser.add_argument("--catalog-output", type=Path, required=True)
    parser.add_argument("--report-output", type=Path, required=True)
    args = parser.parse_args()
    source = args.idml.read_bytes()
    approved_xml = args.approved_xml.read_bytes()
    article = DeterministicPipeline().run(source, logical_name=args.idml.name).canonical
    catalog, report = build_editorial_enrichment_catalog(
        article=article,
        source_idml_sha256=hashlib.sha256(source).hexdigest(),
        approved_xml=approved_xml,
        corpus_id=args.corpus_id,
    )
    _private_json(args.catalog_output, catalog.model_dump(mode="json"))
    args.report_output.parent.mkdir(parents=True, exist_ok=True)
    args.report_output.write_text(
        json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "catalog_id": catalog.catalog_id,
                "article_identifiers": report["article_identifiers"],
                "editorial_orcids": report["editorial_orcids"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
