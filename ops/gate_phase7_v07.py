#!/usr/bin/env python3
"""Run the content-safe V-07 semantic-fidelity qualification gate."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from idml_foundation.ai.formula_catalog import FormulaTranscriptionCatalog
from idml_foundation.pipeline.service import DeterministicPipeline
from idml_foundation.release.editorial_enrichment import EditorialEnrichmentCatalog
from idml_foundation.release.semantic_fidelity import (
    SemanticChangeKind,
    XmlSemanticComparator,
)
from idml_foundation.release.source_authority import SourceAuthorityQualification

_CORPUS_ID = "esa-e20240086"
_ROOT = Path(__file__).parents[1]


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _synthetic_article(*paragraphs: str) -> bytes:
    body = "".join(f"<p>{paragraph}</p>" for paragraph in paragraphs)
    return f"""<article>
      <front><journal-meta><journal-title-group><journal-title>Journal</journal-title>
      </journal-title-group></journal-meta><article-meta>
        <article-id pub-id-type="doi">10.1000/fixture</article-id>
        <title-group><article-title>Qualification fixture</article-title></title-group>
        <contrib-group><contrib contrib-type="author"><name><surname>Silva</surname>
        <given-names>Ana</given-names></name></contrib></contrib-group>
        <aff><institution content-type="original">Fixture Institute</institution></aff>
      </article-meta></front><body><sec><title>Results</title>{body}
        <p><xref ref-type="bibr" rid="ref1">1</xref></p>
      </sec></body><back><ref-list><ref id="ref1"><mixed-citation>
        Silva A. Fixture source. 2024.</mixed-citation></ref></ref-list></back>
    </article>""".encode()


def _mutation_gate() -> dict[str, Any]:
    comparator = XmlSemanticComparator()
    base = _synthetic_article(
        "Alpha paragraph reports a unique source result.",
        "Beta paragraph reports a second source result.",
    )
    mutations = {
        "omission": _synthetic_article(),
        "invention": _synthetic_article(
            "Alpha paragraph reports a unique source result.",
            "Beta paragraph reports a second source result.",
            "An unsupported statement was invented.",
        ),
        "alteration": _synthetic_article(
            "Alpha paragraph reports a changed source result.",
            "Beta paragraph reports a second source result.",
        ),
        "duplication": _synthetic_article(
            "Alpha paragraph reports a unique source result.",
            "Beta paragraph reports a second source result.",
            "Beta paragraph reports a second source result.",
        ),
        "displacement": _synthetic_article(
            "Beta paragraph reports a second source result.",
            "Alpha paragraph reports a unique source result.",
        ),
    }
    detected: dict[str, int] = {}
    for name, candidate in mutations.items():
        report = comparator.compare(base, candidate)
        expected = SemanticChangeKind(name)
        count = sum(finding.kind == expected for finding in report.findings)
        if report.passed or count == 0:
            raise AssertionError(f"semantic mutation was not blocked: {name}")
        detected[name] = count
    normalization = comparator.compare(
        base.replace(b"unique source", b"unique   source"),
        base,
    )
    if not normalization.passed or not any(
        finding.kind == SemanticChangeKind.NORMALIZATION for finding in normalization.findings
    ):
        raise AssertionError("safe whitespace normalization was not classified")
    identical = comparator.compare(base, base)
    if not identical.passed or identical.findings:
        raise AssertionError("identical semantic fixture did not pass")
    return {
        "positive_cases": 2,
        "negative_cases": len(mutations),
        "detected": detected,
        "fixture_sha256": _sha256(base),
    }


def _artifact_path(corpus_root: Path, manifest: dict[str, Any], role: str) -> Path:
    artifact = next(item for item in manifest["artifacts"] if item["role"] == role)
    hint = Path(str(manifest.get("source_root_hint", ""))).name
    candidates = (
        corpus_root / artifact["logical_path"],
        corpus_root / hint / artifact["logical_path"],
    )
    for candidate in candidates:
        if candidate.is_file():
            payload = candidate.read_bytes()
            if len(payload) != artifact["size_bytes"] or _sha256(payload) != artifact["sha256"]:
                raise ValueError(f"authorized artifact integrity failed: {role}")
            return candidate
    raise FileNotFoundError(f"authorized artifact is unavailable: {role}")


def _visual_evidence(path: Path, *, pdf_sha256: str, expected_pages: int) -> dict[str, Any]:
    evidence = json.loads(path.read_text(encoding="utf-8"))
    expected = list(range(1, expected_pages + 1))
    if evidence.get("source_pdf_sha256") != pdf_sha256:
        raise ValueError("visual evidence PDF hash mismatch")
    if evidence.get("expected_pages") != expected_pages:
        raise ValueError("visual evidence page count mismatch")
    if evidence.get("rendered_pages") != expected or evidence.get("inspected_pages") != expected:
        raise ValueError("visual evidence does not cover every page exactly once")
    if evidence.get("issues") or evidence.get("decision") != "pass":
        raise ValueError("visual evidence did not pass")
    if evidence.get("restricted_content_emitted") is not False:
        raise ValueError("visual evidence is not content-safe")
    return {
        "evidence_sha256": _sha256(path.read_bytes()),
        "pdf_sha256": pdf_sha256,
        "pages": expected_pages,
        "checks": len(evidence.get("checks", [])),
        "decision": "pass",
    }


def _domain_summary(domain: Any) -> dict[str, Any]:
    return domain.model_dump(mode="json")


def _authorized_corpus_gate(
    corpus_root: Path,
    visual_path: Path,
    formula_catalog_path: Path | None,
    editorial_enrichment_catalog_path: Path | None,
    source_authority_qualification_path: Path | None,
) -> dict[str, Any]:
    manifest_path = _ROOT / "corpus" / "manifests" / f"{_CORPUS_ID}.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["corpus_id"] != _CORPUS_ID or manifest["split"] != "development":
        raise ValueError("V-07 can only use the frozen development corpus")
    if manifest["policy"]["confidentiality"] != "restricted":
        raise ValueError("authorized corpus confidentiality policy changed")
    source_path = _artifact_path(corpus_root, manifest, "source_idml")
    reference_path = _artifact_path(corpus_root, manifest, "approved_xml_reference")
    pdf_path = _artifact_path(corpus_root, manifest, "approved_pdf_reference")
    source = source_path.read_bytes()
    reference = reference_path.read_bytes()
    formula_catalog = (
        FormulaTranscriptionCatalog.model_validate(
            json.loads(formula_catalog_path.read_text(encoding="utf-8"))
        )
        if formula_catalog_path is not None
        else None
    )
    editorial_enrichment_catalog = (
        EditorialEnrichmentCatalog.model_validate(
            json.loads(editorial_enrichment_catalog_path.read_text(encoding="utf-8"))
        )
        if editorial_enrichment_catalog_path is not None
        else None
    )
    candidate = (
        DeterministicPipeline(
            formula_catalog=formula_catalog,
            editorial_enrichment_catalog=editorial_enrichment_catalog,
        )
        .run(
            source,
            logical_name=source_path.name,
        )
        .xml
    )
    semantic = XmlSemanticComparator().compare(reference, candidate)
    qualified_formula_alterations = 0
    if formula_catalog is not None:
        semantic, qualified_formula_alterations = formula_catalog.reconcile_semantic_report(
            semantic
        )
    source_authority_qualification = (
        SourceAuthorityQualification.model_validate(
            json.loads(source_authority_qualification_path.read_text(encoding="utf-8"))
        )
        if source_authority_qualification_path is not None
        else None
    )
    source_authority_counts = None
    if source_authority_qualification is not None:
        semantic, source_authority_counts = source_authority_qualification.apply(
            semantic,
            source_idml_sha256=_sha256(source),
        )
    visual = _visual_evidence(
        visual_path,
        pdf_sha256=_sha256(pdf_path.read_bytes()),
        expected_pages=manifest["expected"]["pages"],
    )
    serialized = json.dumps(semantic.model_dump(mode="json"), sort_keys=True)
    if semantic.content_emitted or len(serialized) > 200_000:
        raise AssertionError("semantic report violated the content-safe contract")
    return {
        "corpus_id": _CORPUS_ID,
        "split": "development",
        "manifest_sha256": _sha256(manifest_path.read_bytes()),
        "source_sha256": _sha256(source),
        "reference_xml_sha256": semantic.reference_xml_sha256,
        "candidate_xml_sha256": semantic.candidate_xml_sha256,
        "domains": [_domain_summary(domain) for domain in semantic.domains],
        "cross_references": semantic.cross_references.model_dump(mode="json"),
        "finding_counts": {
            kind.value: sum(finding.kind == kind for finding in semantic.findings)
            for kind in SemanticChangeKind
        },
        "blocking_findings": semantic.blocking_findings,
        "candidate_approved": semantic.passed,
        "visual": visual,
        "restricted_content_emitted": False,
        "formula_catalog_id": formula_catalog.catalog_id if formula_catalog else None,
        "formula_source_qualification": (
            {
                "catalog_id": formula_catalog.catalog_id,
                "formula_cases": formula_catalog.expected_formula_count,
                "qualified_alterations": qualified_formula_alterations,
                "human_review_required": True,
            }
            if formula_catalog
            else None
        ),
        "editorial_enrichment_catalog_id": (
            editorial_enrichment_catalog.catalog_id if editorial_enrichment_catalog else None
        ),
        "source_authority_qualification": (
            {
                "qualification_id": source_authority_qualification.qualification_id,
                **(source_authority_counts or {}),
                "human_review_required": True,
            }
            if source_authority_qualification
            else None
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus-root", type=Path)
    parser.add_argument(
        "--visual-evidence",
        type=Path,
        default=_ROOT / "benchmarks" / "qualification" / "evidence" / "v07-esa-pdf-visual-v1.json",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--formula-catalog", type=Path)
    parser.add_argument("--editorial-enrichment-catalog", type=Path)
    parser.add_argument("--source-authority-qualification", type=Path)
    parser.add_argument("--require-candidate-pass", action="store_true")
    args = parser.parse_args()

    report: dict[str, Any] = {
        "version": "phase7-v07-gate-1.0",
        "family": "V-07",
        "comparison_contract": "semantic-fidelity-1.0.0",
        "synthetic": _mutation_gate(),
        "network_required_by_gate": False,
        "restricted_content_emitted": False,
        "qualification_approved": True,
        "release_candidate_approved": False,
    }
    if args.corpus_root is not None:
        corpus = _authorized_corpus_gate(
            args.corpus_root,
            args.visual_evidence,
            args.formula_catalog,
            args.editorial_enrichment_catalog,
            args.source_authority_qualification,
        )
        report["authorized_corpus"] = corpus
        report["release_candidate_approved"] = corpus["candidate_approved"]
    report["approved"] = bool(
        report["qualification_approved"] and report["release_candidate_approved"]
    )
    output = json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    if args.require_candidate_pass and not report["release_candidate_approved"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
