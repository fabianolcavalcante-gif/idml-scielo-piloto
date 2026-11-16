#!/usr/bin/env python3
"""Validate the content-safe 7C-02 figure and package-resolution gate."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any, cast

from lxml import etree

from idml_foundation.asset_identity import figure_asset_number
from idml_foundation.domain.corpus import CorpusManifest, load_manifest, verify_manifest
from idml_foundation.pipeline.profile import load_profile
from idml_foundation.pipeline.service import DeterministicPipeline
from idml_foundation.release.package_builder import AssetPayload, PackageBuilder
from idml_foundation.release.semantic_fidelity import XmlSemanticComparator

ROOT = Path(__file__).parents[1]
DEFAULT_MANIFEST = ROOT / "corpus/manifests/esa-e20240135.json"
DEFAULT_CONTRACT = ROOT / "benchmarks/qualification/contracts/e20240135-7c02-figures-v1.json"
XLINK_HREF = "{http://www.w3.org/1999/xlink}href"


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
        or contract.get("stage") != "7C-02"
        or contract.get("corpus_id") != manifest.corpus_id
        or not isinstance(contract.get("expected"), dict)
    ):
        raise ValueError("invalid 7C-02 corrective contract")
    return cast(dict[str, Any], contract)


def _figure_only_xml(hrefs: list[str]) -> bytes:
    root = etree.Element("article", nsmap={"xlink": "http://www.w3.org/1999/xlink"})
    body = etree.SubElement(root, "body")
    for href in hrefs:
        figure = etree.SubElement(body, "fig")
        etree.SubElement(figure, "graphic", **{XLINK_HREF: href})
    return etree.tostring(root, encoding="UTF-8", xml_declaration=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--corpus-root", type=Path)
    parser.add_argument("--private-candidate-output", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--metadata-only", action="store_true")
    arguments = parser.parse_args()

    manifest_path = arguments.manifest.resolve(strict=True)
    contract_path = arguments.contract.resolve(strict=True)
    manifest = load_manifest(manifest_path)
    contract = _load_contract(contract_path, manifest)
    role_counts = {
        role: sum(item.role == role for item in manifest.artifacts)
        for role in ("source_idml", "approved_xml_reference", "figure_asset")
    }
    metadata_approved = role_counts == {
        "source_idml": 1,
        "approved_xml_reference": 1,
        "figure_asset": 7,
    }
    report: dict[str, Any] = {
        "version": "phase7-7c02-gate-1.0",
        "stage": "7C-02",
        "corpus_id": manifest.corpus_id,
        "metadata": {
            "manifest_sha256": _sha256(manifest_path.read_bytes()),
            "contract_sha256": _sha256(contract_path.read_bytes()),
            "role_counts": role_counts,
            "approved": metadata_approved,
        },
        "network_required_by_gate": False,
        "restricted_content_emitted": False,
        "candidate_approved": False,
        "approved": metadata_approved,
    }

    if not arguments.metadata_only:
        if arguments.corpus_root is None:
            parser.error("--corpus-root is required unless --metadata-only is used")
        corpus_root = arguments.corpus_root.resolve(strict=True)
        verification = verify_manifest(manifest, corpus_root)
        source_path = _single_artifact(corpus_root, manifest, "source_idml")
        reference_path = _single_artifact(corpus_root, manifest, "approved_xml_reference")
        figure_paths = _artifact_paths(corpus_root, manifest, "figure_asset")
        figure_paths.sort(
            key=lambda path: (figure_asset_number(path.name) or 10**9, path.name.casefold())
        )

        source = source_path.read_bytes()
        first = DeterministicPipeline().run(source, logical_name=source_path.name)
        second = DeterministicPipeline().run(source, logical_name=source_path.name)
        semantic = XmlSemanticComparator().compare(reference_path.read_bytes(), first.xml)
        root = etree.fromstring(first.xml)
        figures = cast(list[etree._Element], root.xpath("body//fig"))
        labels = [figure.findtext("label") or "" for figure in figures]
        graphics = [graphic for figure in figures for graphic in figure.findall("graphic")]
        hrefs = [graphic.get(XLINK_HREF, "") for graphic in graphics]
        expected_labels = [f"Figure {number}" for number in range(1, 8)]
        figure_review_blockers = sorted(
            reason.split(":", 1)[0]
            for reason in first.canonical.review_reasons
            if reason.startswith(
                (
                    "unmatched_figure_asset:",
                    "ambiguous_figure_asset:",
                    "unmatched_source_figure_asset:",
                )
            )
        )

        payloads = tuple(
            AssetPayload(
                source_name=path.name,
                data=path.read_bytes(),
                media_type="image/jpeg",
            )
            for path in figure_paths
        )
        package_stem = load_profile().package_stem(first.canonical.article_id)
        figure_files = PackageBuilder().scielo_files(
            package_stem=package_stem,
            xml=_figure_only_xml(hrefs),
            pdf=b"figure-resolution-preflight",
            assets=payloads,
        )
        packaged_asset_names = [item.name for item in figure_files if item.role.value == "asset"]
        expected_package_names = [f"{package_stem}-gf{number:02}.jpg" for number in range(1, 8)]

        full_package_blocker_outside_figures = False
        try:
            PackageBuilder().scielo_files(
                package_stem=package_stem,
                xml=first.xml,
                pdf=b"full-package-preflight",
                assets=payloads,
            )
        except ValueError as exc:
            message = str(exc)
            if message.startswith("missing package asset: "):
                missing_name = message.removeprefix("missing package asset: ")
                full_package_blocker_outside_figures = missing_name not in set(hrefs)

        actual = {
            "source_idml_sha256": _sha256(source),
            "candidate_xml_sha256": _sha256(first.xml),
            "deterministic": first.xml == second.xml,
            "validation": {
                "valid": first.validation.valid,
                "issues": len(first.validation.issues),
            },
            "semantic_blocking_findings": semantic.blocking_findings,
            "figures": _domain(semantic, "figures"),
            "media": _domain(semantic, "media"),
            "structure": _domain(semantic, "structure"),
            "figure_xml": {
                "figures": len(figures),
                "graphics": len(graphics),
                "unique_hrefs": len(set(hrefs)),
                "labels_in_order": labels == expected_labels,
                "artificial_section_absent": not bool(
                    root.xpath("body//sec[title='Elementos gráficos']")
                ),
                "review_blockers": figure_review_blockers,
            },
            "package_preflight": {
                "figure_assets": len(payloads),
                "resolved_assets": len(packaged_asset_names),
                "final_names_in_order": packaged_asset_names == expected_package_names,
                "full_package_blocker_outside_figures": full_package_blocker_outside_figures,
            },
        }
        mismatches = _compare_expected(actual, contract["expected"])
        approved = bool(
            metadata_approved
            and verification.valid
            and actual["deterministic"]
            and actual["validation"]["valid"]
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
                "candidate_approved": semantic.passed,
                "approved": approved,
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
