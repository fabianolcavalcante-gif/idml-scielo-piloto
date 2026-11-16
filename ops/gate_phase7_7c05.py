#!/usr/bin/env python3
"""Validate the content-safe 7C-05 metadata, author, and citation gate."""

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
from idml_foundation.release.crossref_authority import CrossrefMetadataAuthorityCatalog
from idml_foundation.release.semantic_fidelity import XmlSemanticComparator

ROOT = Path(__file__).parents[1]
DEFAULT_MANIFEST = ROOT / "corpus/manifests/esa-e20240135.json"
DEFAULT_CONTRACT = ROOT / "benchmarks/qualification/contracts/e20240135-7c05-metadata-v1.json"
DEFAULT_FORMULA_REPORT = (
    ROOT / "benchmarks/agents/reports/formula-transcription-qualification-e20240135-v1.json"
)
DEFAULT_AUTHORITY_REPORT = (
    ROOT / "benchmarks/qualification/reports/crossref-metadata-authority-e20240135-v1.json"
)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path.name}")
    return value


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
    contract = _load_object(path)
    if (
        contract.get("contract_version") != "1.0.0"
        or contract.get("stage") != "7C-05"
        or contract.get("corpus_id") != manifest.corpus_id
        or not isinstance(contract.get("expected"), dict)
    ):
        raise ValueError("invalid 7C-05 corrective contract")
    return contract


def _artifact_path(root: Path, manifest: CorpusManifest, role: str) -> Path:
    descriptors = [item for item in manifest.artifacts if item.role == role]
    if len(descriptors) != 1:
        raise ValueError(f"manifest must contain exactly one {role} artifact")
    descriptor = descriptors[0]
    path = (root / Path(*PurePosixPath(descriptor.logical_path).parts)).resolve()
    if not path.is_relative_to(root) or path.is_symlink() or not path.is_file():
        raise ValueError(f"restricted artifact is unavailable: {role}")
    payload = path.read_bytes()
    if len(payload) != descriptor.size_bytes or _sha256(payload) != descriptor.sha256:
        raise ValueError(f"restricted artifact integrity failed: {role}")
    return path


def _private_file(path: Path, description: str) -> Path:
    resolved = path.resolve(strict=True)
    if "private" not in {part.casefold() for part in resolved.parts}:
        raise ValueError(f"{description} must remain inside a private directory")
    return resolved


def _score(report: Any, domain: str) -> dict[str, Any]:
    score = next(item for item in report.domains if item.domain == domain)
    return cast(dict[str, Any], score.model_dump(mode="json"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--formula-report", type=Path, default=DEFAULT_FORMULA_REPORT)
    parser.add_argument("--authority-report", type=Path, default=DEFAULT_AUTHORITY_REPORT)
    parser.add_argument("--formula-catalog", type=Path)
    parser.add_argument("--authority-catalog", type=Path)
    parser.add_argument("--corpus-root", type=Path)
    parser.add_argument("--private-candidate-output", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--metadata-only", action="store_true")
    arguments = parser.parse_args()

    manifest_path = arguments.manifest.resolve(strict=True)
    contract_path = arguments.contract.resolve(strict=True)
    formula_report_path = arguments.formula_report.resolve(strict=True)
    authority_report_path = arguments.authority_report.resolve(strict=True)
    manifest = load_manifest(manifest_path)
    contract = _load_contract(contract_path, manifest)
    formula_report = _load_object(formula_report_path)
    authority_report = _load_object(authority_report_path)
    role_counts = {
        role: sum(item.role == role for item in manifest.artifacts)
        for role in ("source_idml", "approved_xml_reference", "approved_pdf_reference")
    }
    metadata_actual = {
        "role_counts": role_counts,
        "formula_qualification": {
            "report_sha256": _sha256(formula_report_path.read_bytes()),
            "catalog_id": formula_report.get("catalog_id"),
            "formula_cases": formula_report.get("formula_cases"),
            "human_review_required": formula_report.get("human_review_required"),
            "restricted_content_emitted": formula_report.get("restricted_content_emitted"),
        },
        "metadata_authority": {
            "report_sha256": _sha256(authority_report_path.read_bytes()),
            "catalog_id": authority_report.get("catalog_id"),
            "crossref_response_sha256": authority_report.get("crossref_response_sha256"),
            "authors": authority_report.get("authors"),
            "journal_titles": authority_report.get("journal_titles"),
            "article_identifiers": authority_report.get("article_identifiers"),
            "human_review_required": authority_report.get("human_review_required"),
            "restricted_content_emitted": authority_report.get("restricted_content_emitted"),
        },
    }
    metadata_expected = {
        key: contract["expected"][key]
        for key in ("role_counts", "formula_qualification", "metadata_authority")
    }
    metadata_mismatches = _compare_expected(metadata_actual, metadata_expected)
    metadata_approved = not metadata_mismatches
    report: dict[str, Any] = {
        "version": "phase7-7c05-gate-1.0",
        "stage": "7C-05",
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
        "metadata_authors_citations_approved": False,
        "approved": metadata_approved,
    }

    if not arguments.metadata_only:
        if (
            arguments.corpus_root is None
            or arguments.formula_catalog is None
            or arguments.authority_catalog is None
        ):
            parser.error(
                "--corpus-root, --formula-catalog, and --authority-catalog are required "
                "unless --metadata-only is used"
            )
        corpus_root = arguments.corpus_root.resolve(strict=True)
        formula_path = _private_file(arguments.formula_catalog, "formula catalog")
        authority_path = _private_file(arguments.authority_catalog, "metadata authority catalog")
        verification = verify_manifest(manifest, corpus_root)
        source_path = _artifact_path(corpus_root, manifest, "source_idml")
        reference_path = _artifact_path(corpus_root, manifest, "approved_xml_reference")
        source = source_path.read_bytes()
        formula_catalog = FormulaTranscriptionCatalog.model_validate(_load_object(formula_path))
        authority_catalog = CrossrefMetadataAuthorityCatalog.model_validate(
            _load_object(authority_path)
        )
        pipeline = DeterministicPipeline(
            formula_catalog=formula_catalog,
            crossref_metadata_catalog=authority_catalog,
        )
        first = pipeline.run(source, logical_name=source_path.name)
        second = pipeline.run(source, logical_name=source_path.name)
        semantic_before = XmlSemanticComparator().compare(reference_path.read_bytes(), first.xml)
        semantic_after, qualified = formula_catalog.reconcile_semantic_report(semantic_before)
        candidate_root = etree.fromstring(first.xml)
        identifiers = {
            str(node.get("pub-id-type")): _sha256(str(node.text or "").encode("utf-8"))
            for node in candidate_root.xpath("front/article-meta/article-id")
        }
        preserved_domains = {
            domain: _score(semantic_after, domain)["passed"]
            for domain in (
                "affiliations",
                "structure",
                "references",
                "figures",
                "tables",
                "formulas",
                "formula_content",
                "notes",
                "media",
            )
        }
        actual = {
            **metadata_actual,
            "source_idml_sha256": _sha256(source),
            "formula_catalog_id": formula_catalog.catalog_id,
            "metadata_authority_catalog_id": authority_catalog.catalog_id,
            "candidate_xml_sha256": _sha256(first.xml),
            "deterministic": first.xml == second.xml,
            "validation": {
                "valid": first.validation.valid,
                "issues": len(first.validation.issues),
            },
            "semantic_blocking_findings_before_qualification": (semantic_before.blocking_findings),
            "semantic_blocking_findings_after_qualification": semantic_after.blocking_findings,
            "qualified_formula_alterations": qualified,
            "metadata": _score(semantic_after, "metadata"),
            "authors": _score(semantic_after, "authors"),
            "body": _score(semantic_after, "body"),
            "emitted_identifiers": identifiers,
            "source_authenticated_orcids": sum(
                contributor.orcid is not None
                and contributor.orcid.transformation == "source-authenticated-orcid-hyperlink"
                for contributor in first.canonical.front.contributors
            ),
            "cross_references": semantic_after.cross_references.model_dump(mode="json"),
            "preserved_domains": preserved_domains,
            "authority_pending_human_review": any(
                reason
                == f"crossref_metadata_authority_pending_human:{authority_catalog.catalog_id}"
                for reason in first.canonical.review_reasons
            ),
            "general_candidate_approved": semantic_after.passed,
        }
        mismatches = _compare_expected(actual, contract["expected"])
        gate_approved = bool(
            metadata_approved
            and verification.valid
            and actual["deterministic"]
            and actual["validation"]["valid"]
            and actual["metadata"]["passed"]
            and actual["authors"]["passed"]
            and actual["body"]["passed"]
            and actual["source_authenticated_orcids"] == 4
            and actual["cross_references"]["decision"] == "pass"
            and all(preserved_domains.values())
            and actual["authority_pending_human_review"]
            and actual["general_candidate_approved"]
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
                "metadata_authors_citations_approved": gate_approved,
                "approved": gate_approved,
            }
        )
        if arguments.private_candidate_output is not None:
            private_output = arguments.private_candidate_output.resolve()
            if "private" not in {part.casefold() for part in private_output.parts}:
                raise ValueError("candidate output must be inside a private directory")
            private_output.parent.mkdir(parents=True, exist_ok=True)
            private_output.write_bytes(first.xml)

    output = json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    if arguments.output is not None:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 0 if report["approved"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
