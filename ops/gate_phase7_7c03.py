#!/usr/bin/env python3
"""Validate the content-safe 7C-03 formula and MathML gate."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any, cast

from lxml import etree

from idml_foundation.ai.formula_catalog import FormulaTranscriptionCatalog
from idml_foundation.domain.corpus import CorpusManifest, load_manifest, verify_manifest
from idml_foundation.pipeline.service import DeterministicPipeline
from idml_foundation.release.semantic_fidelity import XmlSemanticComparator

ROOT = Path(__file__).parents[1]
DEFAULT_MANIFEST = ROOT / "corpus/manifests/esa-e20240135.json"
DEFAULT_CONTRACT = ROOT / "benchmarks/qualification/contracts/e20240135-7c03-formulas-v1.json"
DEFAULT_QUALIFICATION = (
    ROOT / "benchmarks/agents/reports/formula-transcription-qualification-e20240135-v1.json"
)
MML_NS = "http://www.w3.org/1998/Math/MathML"


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _artifact_paths(root: Path, manifest: CorpusManifest, role: str) -> list[Path]:
    paths: list[Path] = []
    for descriptor in manifest.artifacts:
        if descriptor.role != role:
            continue
        candidate = (root / Path(*PurePosixPath(descriptor.logical_path).parts)).resolve()
        if not candidate.is_relative_to(root) or candidate.is_symlink() or not candidate.is_file():
            raise ValueError(f"restricted artifact is unavailable: {role}")
        payload = candidate.read_bytes()
        if len(payload) != descriptor.size_bytes or _sha256(payload) != descriptor.sha256:
            raise ValueError(f"restricted artifact integrity failed: {role}")
        paths.append(candidate)
    return paths


def _single_artifact(root: Path, manifest: CorpusManifest, role: str) -> Path:
    paths = _artifact_paths(root, manifest, role)
    if len(paths) != 1:
        raise ValueError(f"manifest must contain exactly one {role} artifact")
    return paths[0]


def _domain(report: Any, name: str) -> dict[str, Any]:
    score = next(item for item in report.domains if item.domain == name)
    return {
        "expected": score.expected,
        "actual": score.actual,
        "omissions": score.omissions,
        "inventions": score.inventions,
        "duplications": score.duplications,
        "displacements": score.displacements,
        "exact": score.exact,
        "normalized": score.normalized,
        "altered": score.altered,
        "precision": score.precision,
        "recall": score.recall,
        "f1": score.f1,
        "text_fidelity": score.text_fidelity,
        "passed": score.passed,
    }


def _compare_expected(actual: Any, expected: Any, *, path: str = "expected") -> list[str]:
    mismatches: list[str] = []
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return [path]
        for key, expected_value in expected.items():
            child = f"{path}.{key}"
            if key not in actual:
                mismatches.append(child)
            else:
                mismatches.extend(_compare_expected(actual[key], expected_value, path=child))
        return mismatches
    if actual != expected:
        mismatches.append(path)
    return mismatches


def _load_contract(path: Path, manifest: CorpusManifest) -> dict[str, Any]:
    contract = json.loads(path.read_text(encoding="utf-8"))
    if (
        contract.get("contract_version") != "1.0.0"
        or contract.get("stage") != "7C-03"
        or contract.get("corpus_id") != manifest.corpus_id
        or not isinstance(contract.get("expected"), dict)
    ):
        raise ValueError("invalid 7C-03 corrective contract")
    return cast(dict[str, Any], contract)


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path.name}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--qualification-report", type=Path, default=DEFAULT_QUALIFICATION)
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--corpus-root", type=Path)
    parser.add_argument("--private-candidate-output", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--metadata-only", action="store_true")
    arguments = parser.parse_args()

    manifest_path = arguments.manifest.resolve(strict=True)
    contract_path = arguments.contract.resolve(strict=True)
    qualification_path = arguments.qualification_report.resolve(strict=True)
    manifest = load_manifest(manifest_path)
    contract = _load_contract(contract_path, manifest)
    qualification = _load_object(qualification_path)
    role_counts = {
        role: sum(item.role == role for item in manifest.artifacts)
        for role in ("source_idml", "approved_xml_reference", "approved_pdf_reference")
    }
    qualification_summary = {
        "report_sha256": _sha256(qualification_path.read_bytes()),
        "catalog_id": qualification.get("catalog_id"),
        "dataset_sha256": qualification.get("dataset_sha256"),
        "formula_cases": qualification.get("formula_cases"),
        "inline_formulas": qualification.get("inline_formulas"),
        "display_formulas": qualification.get("display_formulas"),
        "critic_passes": qualification.get("critic_passes"),
        "adjudicator_accepts": qualification.get("adjudicator_accepts"),
        "controlled_abstentions": qualification.get("controlled_abstentions"),
        "human_review_required": qualification.get("human_review_required"),
        "restricted_content_emitted": qualification.get("restricted_content_emitted"),
    }
    metadata_actual = {
        "role_counts": role_counts,
        "qualification": qualification_summary,
    }
    metadata_mismatches = _compare_expected(
        metadata_actual,
        {
            "role_counts": contract["expected"]["role_counts"],
            "qualification": contract["expected"]["qualification"],
        },
    )
    metadata_approved = not metadata_mismatches
    report: dict[str, Any] = {
        "version": "phase7-7c03-gate-1.0",
        "stage": "7C-03",
        "corpus_id": manifest.corpus_id,
        "metadata": {
            "manifest_sha256": _sha256(manifest_path.read_bytes()),
            "contract_sha256": _sha256(contract_path.read_bytes()),
            **metadata_actual,
            "mismatches": metadata_mismatches,
            "approved": metadata_approved,
        },
        "network_required_by_gate": False,
        "restricted_content_emitted": False,
        "general_candidate_approved": False,
        "formulas_approved": False,
        "approved": metadata_approved,
    }

    if not arguments.metadata_only:
        if arguments.corpus_root is None or arguments.catalog is None:
            parser.error("--corpus-root and --catalog are required unless --metadata-only is used")
        corpus_root = arguments.corpus_root.resolve(strict=True)
        catalog_path = arguments.catalog.resolve(strict=True)
        if "private" not in {part.casefold() for part in catalog_path.parts}:
            raise ValueError("formula catalog must remain inside a private directory")
        verification = verify_manifest(manifest, corpus_root)
        source_path = _single_artifact(corpus_root, manifest, "source_idml")
        reference_path = _single_artifact(corpus_root, manifest, "approved_xml_reference")
        source = source_path.read_bytes()
        catalog = FormulaTranscriptionCatalog.model_validate(_load_object(catalog_path))
        pipeline = DeterministicPipeline(formula_catalog=catalog)
        first = pipeline.run(source, logical_name=source_path.name)
        second = pipeline.run(source, logical_name=source_path.name)
        semantic_before = XmlSemanticComparator().compare(reference_path.read_bytes(), first.xml)
        semantic_after, qualified_alterations = catalog.reconcile_semantic_report(semantic_before)
        xml_root = etree.fromstring(first.xml)
        formulas = cast(
            list[etree._Element],
            xml_root.xpath("//mml:math", namespaces={"mml": MML_NS}),
        )
        graphic_formulas = cast(
            list[etree._Element],
            xml_root.xpath(
                "//disp-formula//graphic | //disp-formula//inline-graphic | "
                "//inline-formula//graphic | //inline-formula//inline-graphic"
            ),
        )
        formula_review_reasons = [
            reason for reason in first.canonical.review_reasons if "formula" in reason
        ]
        transcription_blockers = sorted(
            reason
            for reason in formula_review_reasons
            if "requires_mathml_transcription" in reason
            or reason.startswith("possible_missing_inline_formula:")
        )
        actual = {
            "role_counts": role_counts,
            "qualification": qualification_summary,
            "source_idml_sha256": _sha256(source),
            "catalog_id": catalog.catalog_id,
            "dataset_sha256": catalog.dataset_sha256,
            "candidate_xml_sha256": _sha256(first.xml),
            "deterministic": first.xml == second.xml,
            "validation": {
                "valid": first.validation.valid,
                "issues": len(first.validation.issues),
            },
            "semantic_blocking_findings_before_qualification": (semantic_before.blocking_findings),
            "semantic_blocking_findings_after_qualification": (semantic_after.blocking_findings),
            "qualified_formula_alterations": qualified_alterations,
            "formulas": _domain(semantic_after, "formulas"),
            "formula_content": _domain(semantic_after, "formula_content"),
            "formula_xml": {
                "total": len(formulas),
                "inline": sum(item.get("display") == "inline" for item in formulas),
                "display": sum(item.get("display") == "block" for item in formulas),
                "graphic_formulas": len(graphic_formulas),
            },
            "review": {
                "transcription_blockers": transcription_blockers,
                "pending_human_marker": sum(
                    reason.startswith("ai_qualified_formula_transcriptions_pending_human:")
                    for reason in formula_review_reasons
                ),
            },
            "general_candidate_blocked": not semantic_after.passed,
        }
        mismatches = _compare_expected(actual, contract["expected"])
        formulas_approved = bool(
            metadata_approved
            and verification.valid
            and actual["deterministic"]
            and actual["validation"]["valid"]
            and actual["formulas"]["passed"]
            and actual["formula_content"]["passed"]
            and actual["formula_xml"]
            == {
                "total": 43,
                "inline": 32,
                "display": 11,
                "graphic_formulas": 0,
            }
            and not transcription_blockers
            and not mismatches
        )
        report.update(
            {
                "physical_verification": {
                    "valid": verification.valid,
                    "artifacts": len(verification.artifacts),
                    "verified": sum(item.valid for item in verification.artifacts),
                },
                "actual": actual,
                "contract_mismatches": mismatches,
                "general_candidate_approved": semantic_after.passed,
                "formulas_approved": formulas_approved,
                "approved": formulas_approved,
            }
        )
        if arguments.private_candidate_output is not None:
            private_path = arguments.private_candidate_output.resolve()
            if "private" not in {part.casefold() for part in private_path.parts}:
                raise ValueError("candidate output must be inside a private directory")
            private_path.parent.mkdir(parents=True, exist_ok=True)
            private_path.write_bytes(first.xml)

    output = json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    if arguments.output is not None:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 0 if report["approved"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
