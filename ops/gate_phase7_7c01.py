#!/usr/bin/env python3
"""Reproduce the content-safe 7C-01 corrective baseline for e20240135."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any

from idml_foundation.domain.corpus import CorpusManifest, load_manifest, verify_manifest
from idml_foundation.pipeline.service import DeterministicPipeline
from idml_foundation.release.corrective_inventory import build_corrective_inventory
from idml_foundation.release.semantic_fidelity import XmlSemanticComparator

ROOT = Path(__file__).parents[1]
DEFAULT_MANIFEST = ROOT / "corpus/manifests/esa-e20240135.json"
DEFAULT_CONTRACT = ROOT / "benchmarks/qualification/contracts/e20240135-7c01-baseline-v1.json"


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _artifact_path(root: Path, manifest: CorpusManifest, role: str) -> Path:
    artifacts = [item for item in manifest.artifacts if item.role == role]
    if len(artifacts) != 1:
        raise ValueError(f"manifest must contain exactly one {role} artifact")
    descriptor = artifacts[0]
    candidate = (root / Path(*PurePosixPath(descriptor.logical_path).parts)).resolve()
    if not candidate.is_relative_to(root) or candidate.is_symlink() or not candidate.is_file():
        raise ValueError(f"restricted artifact is unavailable: {role}")
    payload = candidate.read_bytes()
    if len(payload) != descriptor.size_bytes or _sha256(payload) != descriptor.sha256:
        raise ValueError(f"restricted artifact integrity failed: {role}")
    return candidate


def _semantic_metrics(report: Any) -> dict[str, Any]:
    return {
        "passed": report.passed,
        "blocking_findings": report.blocking_findings,
        "domains": {
            item.domain: {
                "expected": item.expected,
                "actual": item.actual,
                "altered": item.altered,
                "omissions": item.omissions,
                "inventions": item.inventions,
                "duplications": item.duplications,
                "displacements": item.displacements,
            }
            for item in report.domains
        },
        "cross_references": {
            "decision": report.cross_references.decision,
            "expected": report.cross_references.expected,
            "actual": report.cross_references.actual,
            "matched_targets": report.cross_references.matched_targets,
            "expected_unique_targets": report.cross_references.expected_unique_targets,
            "actual_unique_targets": report.cross_references.actual_unique_targets,
        },
    }


def _compare_expected(
    actual: Any,
    expected: Any,
    *,
    path: str = "expected",
) -> list[str]:
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
    if contract.get("contract_version") != "1.0.0":
        raise ValueError("unsupported corrective baseline contract")
    if contract.get("stage") != "7C-01" or contract.get("corpus_id") != manifest.corpus_id:
        raise ValueError("corrective baseline contract identity mismatch")
    if not isinstance(contract.get("expected"), dict):
        raise ValueError("corrective baseline contract has no expected metrics")
    return contract


def _metadata_report(
    manifest_path: Path,
    manifest: CorpusManifest,
    contract_path: Path,
    contract: dict[str, Any],
) -> dict[str, Any]:
    required_roles = {
        "source_idml": 1,
        "approved_xml_reference": 1,
        "approved_pdf_reference": 1,
        "figure_asset": 7,
        "xpm_report": 1,
        "validator_exception_evidence": 1,
    }
    role_counts = {
        role: sum(item.role == role for item in manifest.artifacts) for role in required_roles
    }
    approved = (
        manifest.split.value == "development"
        and manifest.policy.confidentiality.value == "restricted"
        and manifest.policy.redistribution_allowed is False
        and role_counts == required_roles
    )
    return {
        "manifest_sha256": _sha256(manifest_path.read_bytes()),
        "contract_sha256": _sha256(contract_path.read_bytes()),
        "role_counts": role_counts,
        "expected_metric_groups": sorted(contract["expected"]),
        "approved": approved,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--corpus-root", type=Path)
    parser.add_argument("--private-inventory-output", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--metadata-only", action="store_true")
    arguments = parser.parse_args()

    manifest_path = arguments.manifest.resolve(strict=True)
    contract_path = arguments.contract.resolve(strict=True)
    manifest = load_manifest(manifest_path)
    contract = _load_contract(contract_path, manifest)
    metadata = _metadata_report(
        manifest_path,
        manifest,
        contract_path,
        contract,
    )
    report: dict[str, Any] = {
        "version": "phase7-7c01-gate-1.0",
        "stage": "7C-01",
        "corpus_id": manifest.corpus_id,
        "metadata": metadata,
        "network_required_by_gate": False,
        "restricted_content_emitted": False,
        "candidate_approved": False,
        "baseline_reproduced": None,
        "approved": metadata["approved"],
    }

    if not arguments.metadata_only:
        if arguments.corpus_root is None:
            parser.error("--corpus-root is required unless --metadata-only is used")
        corpus_root = arguments.corpus_root.resolve(strict=True)
        verification = verify_manifest(manifest, corpus_root)
        source_path = _artifact_path(corpus_root, manifest, "source_idml")
        reference_path = _artifact_path(corpus_root, manifest, "approved_xml_reference")
        source = source_path.read_bytes()
        reference = reference_path.read_bytes()
        first = DeterministicPipeline().run(source, logical_name=source_path.name)
        second = DeterministicPipeline().run(source, logical_name=source_path.name)
        inventory, private_inventory = build_corrective_inventory(
            first.raw,
            review_reasons=first.canonical.review_reasons,
        )
        semantic = XmlSemanticComparator().compare(reference, first.xml)
        actual = {
            "source_idml_sha256": _sha256(source),
            "candidate_xml_sha256": _sha256(first.xml),
            "deterministic": first.xml == second.xml,
            "validation": {
                "valid": first.validation.valid,
                "issues": len(first.validation.issues),
            },
            "inventory": inventory.model_dump(mode="json"),
            "semantic": _semantic_metrics(semantic),
        }
        mismatches = _compare_expected(actual, contract["expected"])
        report.update(
            {
                "physical_verification": {
                    "valid": verification.valid,
                    "artifacts": len(verification.artifacts),
                    "verified": sum(item.valid for item in verification.artifacts),
                },
                "actual": actual,
                "baseline_mismatches": mismatches,
                "baseline_reproduced": not mismatches,
                "candidate_approved": semantic.passed,
                "approved": bool(
                    metadata["approved"]
                    and verification.valid
                    and actual["deterministic"]
                    and first.validation.valid
                    and not mismatches
                ),
            }
        )
        if arguments.private_inventory_output is not None:
            private_path = arguments.private_inventory_output.resolve()
            if "private" not in {part.casefold() for part in private_path.parts}:
                raise ValueError("private inventory output must be inside a private directory")
            private_path.parent.mkdir(parents=True, exist_ok=True)
            private_path.write_text(
                json.dumps(private_inventory, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

    output = json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    if arguments.output is not None:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 0 if report["approved"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
