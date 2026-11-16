#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from idml_foundation.ai.corrective_7c07 import build_corrective_7c07_dataset
from idml_foundation.ai.formula_catalog import FormulaTranscriptionCatalog
from idml_foundation.pipeline.service import DeterministicPipeline
from idml_foundation.release.crossref_authority import CrossrefMetadataAuthorityCatalog
from idml_foundation.release.formal_metadata import FormalMetadataAuthorityCatalog

DATASET_VERSION = "idml-agent-e20240135-7c07-1.0"
CASE_ID_PREFIX = "e20240135-7c07"


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path.name}")
    return value


def _write_private(path: Path, value: dict[str, Any]) -> None:
    resolved = path.resolve()
    if "private" not in {part.casefold() for part in resolved.parts}:
        raise ValueError("restricted 7C-07 dataset must remain in a private directory")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    temporary = resolved.with_name(f".{resolved.name}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as target:
        json.dump(value, target, ensure_ascii=False, indent=2)
        target.write("\n")
    os.replace(temporary, resolved)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--idml", type=Path, required=True)
    parser.add_argument("--formula-catalog", type=Path, required=True)
    parser.add_argument("--metadata-authority-catalog", type=Path, required=True)
    parser.add_argument("--formal-metadata-catalog", type=Path, required=True)
    parser.add_argument("--visual-dataset", type=Path, required=True)
    parser.add_argument("--corpus-id", required=True)
    parser.add_argument("--source-idml-sha256", required=True)
    parser.add_argument("--dataset-output", type=Path, required=True)
    parser.add_argument("--report-output", type=Path, required=True)
    arguments = parser.parse_args()

    source = arguments.idml.read_bytes()
    if hashlib.sha256(source).hexdigest() != arguments.source_idml_sha256:
        raise ValueError("source IDML hash differs from the 7C-07 declaration")
    pipeline = DeterministicPipeline(
        formula_catalog=FormulaTranscriptionCatalog.model_validate(
            _load(arguments.formula_catalog)
        ),
        crossref_metadata_catalog=CrossrefMetadataAuthorityCatalog.model_validate(
            _load(arguments.metadata_authority_catalog)
        ),
        formal_metadata_catalog=FormalMetadataAuthorityCatalog.model_validate(
            _load(arguments.formal_metadata_catalog)
        ),
    )
    result = pipeline.run(source, logical_name=arguments.idml.name)
    dataset, report = build_corrective_7c07_dataset(
        article=result.canonical,
        visual_dataset=_load(arguments.visual_dataset),
        corpus_id=arguments.corpus_id,
        source_idml_sha256=arguments.source_idml_sha256,
        candidate_xml=result.xml,
        dataset_version=DATASET_VERSION,
        case_id_prefix=CASE_ID_PREFIX,
    )
    _write_private(arguments.dataset_output, dataset)
    arguments.report_output.parent.mkdir(parents=True, exist_ok=True)
    arguments.report_output.write_text(
        json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
