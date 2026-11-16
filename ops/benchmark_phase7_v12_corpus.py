"""Local-only timing of the two authenticated articles; output contains no content."""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

from idml_foundation.ai.formula_catalog import FormulaTranscriptionCatalog
from idml_foundation.domain.corpus import load_manifest
from idml_foundation.pipeline.profile import load_profile
from idml_foundation.pipeline.service import DeterministicPipeline
from idml_foundation.release.crossref_authority import CrossrefMetadataAuthorityCatalog
from idml_foundation.release.editorial_enrichment import EditorialEnrichmentCatalog
from idml_foundation.release.formal_metadata import FormalMetadataAuthorityCatalog
from idml_foundation.release.package_builder import AssetPayload, PackageBuilder

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
from ops.benchmark_phase7_v12 import measure, percentile  # noqa: E402
from ops.gate_phase7_7c06 import _artifact_paths, _single_artifact  # noqa: E402
from ops.gate_phase7_v07 import _artifact_path  # noqa: E402


def main() -> int:
    private = ROOT / "benchmarks/private/output"
    rows = []
    package_rows = []
    for article in ("e20240086", "e20240135"):
        manifest_path = ROOT / f"corpus/manifests/esa-{article}.json"
        if article == "e20240086":
            manifest_dict = json.loads(manifest_path.read_text(encoding="utf-8"))
            source_path = _artifact_path(ROOT / "tmp/sample", manifest_dict, "source_idml")
            catalogs = {
                "formula_catalog": FormulaTranscriptionCatalog.model_validate_json(
                    (private / "formula-transcription-catalog-v1.json").read_bytes()
                ),
                "editorial_enrichment_catalog": EditorialEnrichmentCatalog.model_validate_json(
                    (private / "editorial-enrichment-catalog-v1.json").read_bytes()
                ),
            }
            expected = "15287f774bed60a62f0c5734aa7082234cbc7b69b86effeecc7a1e9ea991bc20"
        else:
            manifest = load_manifest(manifest_path)
            corpus_root = (ROOT / "tmp/ARQUIVOS TESTE").resolve()
            source_path = _single_artifact(corpus_root, manifest, "source_idml")
            catalogs = {
                "formula_catalog": FormulaTranscriptionCatalog.model_validate_json(
                    (private / "formula-transcription-catalog-e20240135-v1.json").read_bytes()
                ),
                "crossref_metadata_catalog": CrossrefMetadataAuthorityCatalog.model_validate_json(
                    (private / "crossref-metadata-authority-e20240135-v1.json").read_bytes()
                ),
                "formal_metadata_catalog": FormalMetadataAuthorityCatalog.model_validate_json(
                    (private / "formal-metadata-authority-e20240135-v1.json").read_bytes()
                ),
            }
            expected = "20a03a91496ac0b447bd2abe589c2be6c231547793dcf5289bd3e66cc1990880"
        source = source_path.read_bytes()
        samples = [
            measure(
                source,
                time.perf_counter(),
                pipeline=DeterministicPipeline(**catalogs),
                logical_name=source_path.name,
            )
            for _ in range(3)
        ]
        for sample in samples:
            # There is no queue in this local sequential corpus measurement.
            sample.pop("queue_ms")
        rows.append(
            {
                "corpus_id": f"esa-{article}",
                "samples": samples,
                "candidate_matches_qualification": all(
                    s["xml_sha256"] == expected for s in samples
                ),
                "all_valid": all(s["status"] == "valid" for s in samples),
                "p95_duration_ms": percentile([s["duration_ms"] for s in samples]),
            }
        )
        if article == "e20240135":
            result = DeterministicPipeline(**catalogs).run(source, logical_name=source_path.name)
            pdf = _single_artifact(corpus_root, manifest, "approved_pdf_reference").read_bytes()
            assets = tuple(
                AssetPayload(source_name=p.name, data=p.read_bytes(), media_type="image/jpeg")
                for p in _artifact_paths(corpus_root, manifest, "figure_asset")
            )
            profile = load_profile()
            for _ in range(3):
                started = time.perf_counter()
                builder = PackageBuilder()
                files = builder.scielo_files(
                    package_stem=profile.package_stem(result.canonical.article_id),
                    xml=result.xml,
                    pdf=pdf,
                    assets=assets,
                )
                package = builder.build(
                    article_id=result.canonical.article_id,
                    profile_id=profile.profile_id,
                    source_idml_sha256=hashlib.sha256(source).hexdigest(),
                    files=files,
                    validator_versions={
                        "offline-jats": "jats-1.3-mathml3+sps-baseline-1.1.0",
                        "packtools": "4.17.2+ef0e6f874ea7",
                        "spsvalidator": "0.3.0+d1aa774d4e33",
                    },
                )
                package_rows.append(
                    {
                        "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                        "bytes": package.package_size_bytes,
                        "sha256": package.package_sha256,
                    }
                )
    report = {
        "version": "phase7-v12-local-corpus-1.0",
        "environment": "local-windows-not-vps",
        "approved": all(r["candidate_matches_qualification"] and r["all_valid"] for r in rows)
        and all(
            p["sha256"] == "e86f51a83a1f5d7cc869e51f4e13d18bb68fcf6c758016dd99bead032b0559ee"
            for p in package_rows
        ),
        "articles": rows,
        "package_samples": package_rows,
        "excluded_from_timing": [
            "pipeline initialization",
            "catalog loading",
            "source file reads",
            "external validators",
            "AI",
        ],
        "stage_timing_note": "total also includes enrichment and cross-reference resolution",
        "provider_calls": 0,
        "restricted_content_emitted": False,
        "release_ready": False,
    }
    (ROOT / "benchmarks/qualification/reports/v12-local-corpus-v1.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "approved": report["approved"],
                "articles": len(rows),
                "package_runs": len(package_rows),
            }
        )
    )
    return 0 if report["approved"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
