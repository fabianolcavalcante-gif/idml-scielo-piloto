#!/usr/bin/env python3
"""Validate the content-safe 7C-04 hierarchy, flow, and notes gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any, cast

from lxml import etree

from idml_foundation.ai.formula_catalog import FormulaTranscriptionCatalog
from idml_foundation.domain.corpus import CorpusManifest, load_manifest, verify_manifest
from idml_foundation.domain.metrics import normalize_text
from idml_foundation.pipeline.idml_parser import style_prefix
from idml_foundation.pipeline.profile import load_profile
from idml_foundation.pipeline.service import DeterministicPipeline
from idml_foundation.release.semantic_fidelity import (
    XmlSemanticComparator,
    extract_semantic_fields,
)

ROOT = Path(__file__).parents[1]
DEFAULT_MANIFEST = ROOT / "corpus/manifests/esa-e20240135.json"
DEFAULT_CONTRACT = ROOT / "benchmarks/qualification/contracts/e20240135-7c04-structure-v1.json"
DEFAULT_QUALIFICATION = (
    ROOT / "benchmarks/agents/reports/formula-transcription-qualification-e20240135-v1.json"
)


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
        or contract.get("stage") != "7C-04"
        or contract.get("corpus_id") != manifest.corpus_id
        or not isinstance(contract.get("expected"), dict)
    ):
        raise ValueError("invalid 7C-04 corrective contract")
    return cast(dict[str, Any], contract)


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path.name}")
    return value


def _tokens(values: list[str]) -> Counter[str]:
    return Counter(
        re.findall(r"\w+", " ".join(normalize_text(value).casefold() for value in values))
    )


def _source_body_tokens(result: Any) -> Counter[str]:
    profile = load_profile()
    style_names = {style.id: style.source_name for style in result.raw.styles}
    values: list[str] = []
    for story in result.raw.stories:
        runs = {run.id: run for run in story.runs}
        for paragraph in story.paragraphs:
            role = profile.role_for_prefix(
                style_prefix(style_names.get(paragraph.paragraph_style_id or "", ""))
            )
            if role != "paragraph" or paragraph.table_cell_id:
                continue
            values.append("".join(runs[run_id].text for run_id in paragraph.text_run_ids))
    return _tokens(values)


def _qualified_formula_tokens(catalog: FormulaTranscriptionCatalog) -> Counter[str]:
    return _tokens(
        [
            " ".join(etree.fromstring(entry.mathml.encode("utf-8")).itertext())
            for entry in catalog.entries
        ]
    )


def _hierarchy(root: etree._Element) -> list[dict[str, Any]]:
    return [
        {
            "depth": len(section.xpath("ancestor::sec")) + 1,
            "title": normalize_text(section.xpath("string(title)")),
            "section_type": section.get("sec-type"),
        }
        for section in cast(list[etree._Element], root.xpath("body//sec"))
    ]


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
        "human_review_required": qualification.get("human_review_required"),
        "restricted_content_emitted": qualification.get("restricted_content_emitted"),
    }
    metadata_actual = {
        "role_counts": role_counts,
        "qualification": qualification_summary,
    }
    metadata_expected = {
        "role_counts": contract["expected"]["role_counts"],
        "qualification": contract["expected"]["qualification"],
    }
    metadata_mismatches = _compare_expected(metadata_actual, metadata_expected)
    metadata_approved = not metadata_mismatches
    report: dict[str, Any] = {
        "version": "phase7-7c04-gate-1.0",
        "stage": "7C-04",
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
        "structure_notes_approved": False,
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
        candidate_root = etree.fromstring(first.xml)
        reference_root = etree.fromstring(reference_path.read_bytes())
        candidate_hierarchy = _hierarchy(candidate_root)
        reference_hierarchy = _hierarchy(reference_root)
        hierarchy_levels = Counter(item["depth"] for item in candidate_hierarchy)
        body_score = _domain(semantic_after, "body")
        candidate_body_tokens = _tokens(
            [field.raw for field in extract_semantic_fields(candidate_root)["body"]]
        )
        reference_body_tokens = _tokens(
            [field.raw for field in extract_semantic_fields(reference_root)["body"]]
        )
        authenticated_tokens = (
            _source_body_tokens(first) + _qualified_formula_tokens(catalog) + reference_body_tokens
        )
        unauthenticated_tokens = candidate_body_tokens - authenticated_tokens
        body_flow = {
            **body_score,
            "unauthenticated_tokens": sum(unauthenticated_tokens.values()),
            "passed": bool(
                body_score["omissions"] == 0
                and body_score["inventions"] == 0
                and body_score["altered"] == 0
                and body_score["displacements"] == 0
                and not unauthenticated_tokens
            ),
        }
        structural_notes = {
            "author_notes": len(candidate_root.xpath("front/article-meta/author-notes/fn")),
            "table_footnotes": len(candidate_root.xpath("body//table-wrap-foot/fn")),
            "table_footnote_paragraphs": len(candidate_root.xpath("body//table-wrap-foot/fn/p")),
            "funding_disclosures": len(
                candidate_root.xpath("back/fn-group/fn[@fn-type='financial-disclosure']")
            ),
        }
        structural_notes["total"] = (
            structural_notes["author_notes"]
            + structural_notes["table_footnotes"]
            + structural_notes["funding_disclosures"]
        )
        actual = {
            "role_counts": role_counts,
            "qualification": qualification_summary,
            "source_idml_sha256": _sha256(source),
            "catalog_id": catalog.catalog_id,
            "candidate_xml_sha256": _sha256(first.xml),
            "deterministic": first.xml == second.xml,
            "validation": {
                "valid": first.validation.valid,
                "issues": len(first.validation.issues),
            },
            "semantic_blocking_findings_before_qualification": semantic_before.blocking_findings,
            "semantic_blocking_findings_after_qualification": semantic_after.blocking_findings,
            "qualified_formula_alterations": qualified_alterations,
            "hierarchy": {
                "expected": len(reference_hierarchy),
                "actual": len(candidate_hierarchy),
                "levels": {
                    str(level): hierarchy_levels[level] for level in sorted(hierarchy_levels)
                },
                "reference_sha256": _sha256(
                    json.dumps(reference_hierarchy, ensure_ascii=False).encode("utf-8")
                ),
                "candidate_sha256": _sha256(
                    json.dumps(candidate_hierarchy, ensure_ascii=False).encode("utf-8")
                ),
                "passed": candidate_hierarchy == reference_hierarchy,
            },
            "structure": _domain(semantic_after, "structure"),
            "notes": _domain(semantic_after, "notes"),
            "structural_notes": structural_notes,
            "body_flow": body_flow,
            "tables": _domain(semantic_after, "tables"),
            "references": _domain(semantic_after, "references"),
            "formulas": _domain(semantic_after, "formulas"),
            "formula_content": _domain(semantic_after, "formula_content"),
            "cross_references": {
                "expected": semantic_after.cross_references.expected,
                "actual": semantic_after.cross_references.actual,
                "decision": semantic_after.cross_references.decision,
            },
            "general_candidate_blocked": not semantic_after.passed,
        }
        mismatches = _compare_expected(actual, contract["expected"])
        structure_notes_approved = bool(
            metadata_approved
            and verification.valid
            and actual["deterministic"]
            and actual["validation"]["valid"]
            and actual["hierarchy"]["passed"]
            and actual["structure"]["passed"]
            and actual["notes"]["passed"]
            and actual["structural_notes"]["total"] == 7
            and actual["structural_notes"]["table_footnote_paragraphs"] == 6
            and actual["body_flow"]["passed"]
            and actual["tables"]["passed"]
            and actual["references"]["passed"]
            and actual["formulas"]["passed"]
            and actual["formula_content"]["passed"]
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
                "structure_notes_approved": structure_notes_approved,
                "approved": structure_notes_approved,
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
