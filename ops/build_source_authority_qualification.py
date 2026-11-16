from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from idml_foundation.ai.formula_catalog import FormulaTranscriptionCatalog
from idml_foundation.pipeline.profile import load_profile
from idml_foundation.pipeline.service import DeterministicPipeline
from idml_foundation.release.editorial_enrichment import EditorialEnrichmentCatalog
from idml_foundation.release.semantic_fidelity import XmlSemanticComparator
from idml_foundation.release.source_authority import (
    build_source_authority_qualification,
)


def _object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path.name}")
    return value


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--idml", type=Path, required=True)
    parser.add_argument("--approved-xml", type=Path, required=True)
    parser.add_argument("--corpus-id", required=True)
    parser.add_argument("--formula-catalog", type=Path, required=True)
    parser.add_argument("--editorial-enrichment-catalog", type=Path, required=True)
    parser.add_argument("--crossref-evidence", type=Path, required=True)
    parser.add_argument("--qualification-output", type=Path, required=True)
    parser.add_argument("--report-output", type=Path, required=True)
    args = parser.parse_args()
    source = args.idml.read_bytes()
    reference = args.approved_xml.read_bytes()
    formula_catalog = FormulaTranscriptionCatalog.model_validate(_object(args.formula_catalog))
    editorial_catalog = EditorialEnrichmentCatalog.model_validate(
        _object(args.editorial_enrichment_catalog)
    )
    pipeline_result = DeterministicPipeline(
        formula_catalog=formula_catalog,
        editorial_enrichment_catalog=editorial_catalog,
    ).run(source, logical_name=args.idml.name)
    semantic = XmlSemanticComparator().compare(reference, pipeline_result.xml)
    profile = load_profile()
    primary_title = pipeline_result.canonical.front.titles[0].text.value
    if primary_title is None:
        raise ValueError("source authority primary article title is unavailable")
    crossref_payload = args.crossref_evidence.read_bytes()
    qualification, report = build_source_authority_qualification(
        report=semantic,
        corpus_id=args.corpus_id,
        journal_profile_id=profile.profile_id,
        source_idml_sha256=_sha256(source),
        journal_title=profile.journal_title,
        primary_article_title=primary_title,
        crossref_evidence=json.loads(crossref_payload),
        crossref_evidence_sha256=_sha256(crossref_payload),
    )
    for path, value in (
        (args.qualification_output, qualification.model_dump(mode="json")),
        (args.report_output, report),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(
        json.dumps(
            {
                "qualification_id": qualification.qualification_id,
                "metadata_differences": report["metadata_differences"],
                "bibliographic_occurrences": report["bibliographic_occurrences"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
