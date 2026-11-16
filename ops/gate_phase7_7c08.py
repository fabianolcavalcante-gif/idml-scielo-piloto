"""Requalify the current code without exporting restricted article content."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from idml_foundation.ai.formula_catalog import FormulaTranscriptionCatalog
from idml_foundation.pipeline.service import DeterministicPipeline
from idml_foundation.release.crossref_authority import CrossrefMetadataAuthorityCatalog
from idml_foundation.release.formal_metadata import FormalMetadataAuthorityCatalog
from idml_foundation.release.semantic_fidelity import XmlSemanticComparator

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
DOMAINS = {
    "metadata",
    "authors",
    "affiliations",
    "body",
    "structure",
    "references",
    "figures",
    "tables",
    "formulas",
    "formula_content",
    "notes",
    "media",
}


def run_gate(name: str, arguments: list[str]) -> dict[str, Any]:
    completed = subprocess.run(  # noqa: S603 - fixed local Python gates
        [sys.executable, str(ROOT / "ops" / f"gate_phase7_{name}.py"), *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    report = json.loads(completed.stdout)
    # V-07 synthetic mode qualifies the comparator, not a real article candidate.
    approved = (
        report.get("qualification_approved")
        if name == "v07" and "--require-candidate-pass" not in arguments
        else report.get("approved")
    )
    result = {
        "gate": name,
        "passed": completed.returncode == 0 and approved is True,
        "exit_code": completed.returncode,
        "report_sha256": hashlib.sha256(completed.stdout.encode()).hexdigest(),
    }
    if name == "v03":
        result["real_packages_verified"] = report.get("real_packages_verified", 0)
        result["real_exact_stories"] = report.get("real_exact_stories", 0)
    if name == "v07" and "--require-candidate-pass" in arguments:
        corpus = report.get("authorized_corpus", {})
        result["corpus_id"] = corpus.get("corpus_id")
        result["candidate_xml_sha256"] = corpus.get("candidate_xml_sha256")
        result["semantic_blocking_findings"] = corpus.get("blocking_findings")
        result["passed"] = result["passed"] and corpus.get("blocking_findings") == 0
    return result


def final_candidate(root: Path) -> dict[str, Any]:
    private = ROOT / "benchmarks/private/output"
    formula = FormulaTranscriptionCatalog.model_validate_json(
        (private / "formula-transcription-catalog-e20240135-v1.json").read_bytes()
    )
    crossref = CrossrefMetadataAuthorityCatalog.model_validate_json(
        (private / "crossref-metadata-authority-e20240135-v1.json").read_bytes()
    )
    formal = FormalMetadataAuthorityCatalog.model_validate_json(
        (private / "formal-metadata-authority-e20240135-v1.json").read_bytes()
    )
    from idml_foundation.domain.corpus import load_manifest, verify_manifest
    from ops.gate_phase7_7c06 import DEFAULT_MANIFEST, _single_artifact

    manifest = load_manifest(DEFAULT_MANIFEST)
    verification = verify_manifest(manifest, root)
    source = _single_artifact(root, manifest, "source_idml")
    reference = _single_artifact(root, manifest, "approved_xml_reference")
    pipeline = DeterministicPipeline(
        formula_catalog=formula, crossref_metadata_catalog=crossref, formal_metadata_catalog=formal
    )
    first = pipeline.run(source.read_bytes(), logical_name=source.name)
    second = pipeline.run(source.read_bytes(), logical_name=source.name)
    before = XmlSemanticComparator().compare(reference.read_bytes(), first.xml)
    after, qualified = formula.reconcile_semantic_report(before)
    scores = {score.domain: score.passed for score in after.domains}
    actual = {
        "corpus_id": manifest.corpus_id,
        "physical_verification": verification.valid,
        "candidate_xml_sha256": hashlib.sha256(first.xml).hexdigest(),
        "deterministic": first.xml == second.xml,
        "offline_valid": first.validation.valid,
        "offline_issues": len(first.validation.issues),
        "semantic_blocking_findings": after.blocking_findings,
        "qualified_formula_alterations": qualified,
        "domains": scores,
    }
    actual["passed"] = bool(
        verification.valid
        and first.xml == second.xml
        and first.validation.valid
        and not first.validation.issues
        and after.passed
        and after.blocking_findings == 0
        and set(scores) == DOMAINS
        and all(scores.values())
    )
    return actual


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--with-private-corpus", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    rows = []
    for name in [*(f"v{i:02}" for i in range(1, 12)), *(f"7c{i:02}" for i in range(1, 8))]:
        try:
            rows.append(
                run_gate(
                    name, ["--metadata-only"] if name == "v01" or name.startswith("7c") else []
                )
            )
        except Exception as exc:
            rows.append({"gate": name, "passed": False, "error": type(exc).__name__})
    articles = []
    if args.with_private_corpus:
        private = ROOT / "benchmarks/private/output"
        try:
            articles.append(
                run_gate(
                    "v03",
                    [
                        "--real-idml",
                        str(ROOT / "tmp/sample/ESA_2024086_AOP.idml"),
                        "--real-idml",
                        str(ROOT / "tmp/ARQUIVOS TESTE/ESA_2024135_AOP.idml"),
                    ],
                )
            )
            articles.append(
                run_gate(
                    "v07",
                    [
                        "--corpus-root",
                        str(ROOT / "tmp/sample"),
                        "--formula-catalog",
                        str(private / "formula-transcription-catalog-v1.json"),
                        "--editorial-enrichment-catalog",
                        str(private / "editorial-enrichment-catalog-v1.json"),
                        "--source-authority-qualification",
                        str(ROOT / "config/source-authority-qualification-esa-e20240086-v1.json"),
                        "--require-candidate-pass",
                    ],
                )
            )
            articles.append(final_candidate((ROOT / "tmp/ARQUIVOS TESTE").resolve()))
            articles.append(
                run_gate(
                    "7c06",
                    [
                        "--corpus-root",
                        str(ROOT / "tmp/ARQUIVOS TESTE"),
                        "--formula-catalog",
                        str(private / "formula-transcription-catalog-e20240135-v1.json"),
                        "--metadata-authority-catalog",
                        str(private / "crossref-metadata-authority-e20240135-v1.json"),
                        "--formal-metadata-catalog",
                        str(private / "formal-metadata-authority-e20240135-v1.json"),
                        "--packtools-json",
                        str(private / "packtools-e20240135-7c06.json"),
                        "--spsvalidator-json",
                        str(private / "spsvalidator-e20240135-7c06.json"),
                    ],
                )
            )
        except Exception as exc:
            articles.append({"passed": False, "error": type(exc).__name__})
    approved = all(row["passed"] for row in rows) and all(row["passed"] for row in articles)
    report = {
        "version": "phase7-7c08-requalification-1.0",
        "stage": "7C-08",
        "approved": approved,
        "private_corpus_executed": args.with_private_corpus,
        "synthetic_gates": rows,
        "article_gates": articles,
        "external_validator_evidence": (
            "hash-bound replay; no new external validator run" if args.with_private_corpus else None
        ),
        "restricted_content_emitted": False,
        "release_ready": False,
        "human_review_required": True,
        "xpm_windows_pending": True,
    }
    serialized = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    else:
        print(serialized, end="")
    return 0 if approved else 2


if __name__ == "__main__":
    raise SystemExit(main())
