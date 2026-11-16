#!/usr/bin/env python3
"""Inspect a restricted ESA reference bundle without emitting article content."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from collections import Counter
from pathlib import Path
from typing import Any, BinaryIO

from lxml import etree
from pypdf import PdfReader

from idml_foundation.pipeline.service import DeterministicPipeline
from idml_foundation.pipeline.validation import OfflineJatsValidator
from idml_foundation.release.xpm import XpmReportParser


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _resolve(root: Path, artifact: dict[str, Any]) -> Path | None:
    direct = root / artifact["logical_path"]
    if direct.is_file() and _digest(direct.read_bytes()) == artifact["sha256"]:
        return direct
    matches = [
        candidate
        for candidate in root.rglob(Path(artifact["logical_path"]).name)
        if candidate.is_file() and _digest(candidate.read_bytes()) == artifact["sha256"]
    ]
    if len(matches) > 1:
        raise ValueError(f"ambiguous artifact: {artifact['role']}")
    return matches[0] if matches else None


def _jpeg_dimensions(stream: BinaryIO) -> tuple[int, int]:
    if stream.read(2) != b"\xff\xd8":
        raise ValueError("not a JPEG image")
    while marker := stream.read(2):
        if len(marker) != 2 or marker[0] != 0xFF:
            raise ValueError("invalid JPEG marker")
        while marker[1] == 0xFF:
            marker = bytes((0xFF, stream.read(1)[0]))
        if marker[1] in {0xD8, 0xD9}:
            continue
        length_data = stream.read(2)
        if len(length_data) != 2:
            raise ValueError("truncated JPEG segment")
        length = struct.unpack(">H", length_data)[0]
        if marker[1] in {
            0xC0,
            0xC1,
            0xC2,
            0xC3,
            0xC5,
            0xC6,
            0xC7,
            0xC9,
            0xCA,
            0xCB,
            0xCD,
            0xCE,
            0xCF,
        }:
            dimensions = stream.read(5)
            if len(dimensions) != 5:
                raise ValueError("truncated JPEG dimensions")
            _, height, width = struct.unpack(">BHH", dimensions)
            return width, height
        stream.seek(length - 2, 1)
    raise ValueError("JPEG dimensions not found")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    resolved = [
        (_resolve(args.sample_root, artifact), artifact) for artifact in manifest["artifacts"]
    ]
    present = [(path, artifact) for path, artifact in resolved if path is not None]
    roles_present = {artifact["role"] for path, artifact in present}
    required = {
        "source_idml",
        "approved_xml_reference",
        "approved_pdf_reference",
        "xpm_report",
    }
    missing_required = sorted(required - roles_present)
    if missing_required:
        raise ValueError(f"required reference artifacts missing: {missing_required}")

    def by_role(role: str) -> Path:
        return next(path for path, artifact in present if artifact["role"] == role)

    source_path = by_role("source_idml")
    xml_path = by_role("approved_xml_reference")
    pdf_path = by_role("approved_pdf_reference")
    xpm_path = by_role("xpm_report")
    source = source_path.read_bytes()
    pipeline = DeterministicPipeline().run(source, logical_name=source_path.name)

    xml_parser = etree.XMLParser(
        resolve_entities=False,
        load_dtd=False,
        no_network=True,
        recover=False,
    )
    gold_xml = xml_path.read_bytes()
    gold = etree.fromstring(gold_xml, parser=xml_parser)
    xml_counts = {
        "contributors": len(gold.xpath("//contrib[@contrib-type='author']")),
        "affiliations": len(gold.xpath("//article-meta/aff")),
        "top_level_sections": len(gold.xpath("body/sec")),
        "all_sections": len(gold.xpath("body//sec")),
        "body_paragraphs": len(gold.xpath("body//sec/p")),
        "figures": len(gold.xpath("body//fig")),
        "tables": len(gold.xpath("body//table-wrap")),
        "inline_formulas": len(gold.xpath("body//inline-formula")),
        "display_formulas": len(gold.xpath("body//disp-formula")),
        "references": len(gold.xpath("back//ref")),
        "notes": len(gold.xpath("//fn")),
        "back_notes": len(gold.xpath("back//fn")),
    }
    xlink = "http://www.w3.org/1999/xlink"
    graphic_names = sorted(
        Path(str(value)).name
        for value in gold.xpath("body//fig/graphic/@xlink:href", namespaces={"xlink": xlink})
    )
    image_paths = sorted(path for path, artifact in present if artifact["role"] == "figure_asset")
    image_dimensions: dict[str, dict[str, int]] = {}
    for path in image_paths:
        with path.open("rb") as stream:
            width, height = _jpeg_dimensions(stream)
        image_dimensions[path.name] = {"width": width, "height": height}
    gold_validation = OfflineJatsValidator(
        Path(__file__).parents[1] / "vendor" / "jats" / "1.3"
    ).validate(gold_xml, asset_names={path.name for path in image_paths})
    gold_issue_counts = Counter(issue.code for issue in gold_validation.issues)

    package_artifact = next(
        artifact
        for artifact in manifest["artifacts"]
        if artifact["role"] == "approved_delivery_package"
    )
    xpm = XpmReportParser().parse(
        xpm_path.read_bytes(),
        candidate_package_sha256=package_artifact["sha256"],
        tool_sha256=None,
    )
    pdf = PdfReader(pdf_path, strict=True)
    report = {
        "version": "esa-reference-bundle-inspection-1.0",
        "restricted": True,
        "corpus_id": manifest["corpus_id"],
        "provided_artifacts": len(present),
        "manifest_artifacts": len(manifest["artifacts"]),
        "missing_artifacts": sorted(
            artifact["logical_path"] for path, artifact in resolved if path is None
        ),
        "hashes_verified": all(
            _digest(path.read_bytes()) == artifact["sha256"] for path, artifact in present
        ),
        "idml": {
            "stories": len(pipeline.raw.stories),
            "frames": len(pipeline.raw.frames),
            "spreads": len(pipeline.raw.spreads),
            "tables": len(pipeline.raw.tables),
            "canonical_contributors": len(pipeline.canonical.front.contributors),
            "canonical_affiliations": len(pipeline.canonical.front.affiliations),
            "canonical_sections": len(pipeline.canonical.body),
            "canonical_references": len(pipeline.canonical.back.references),
            "review_reasons": len(pipeline.canonical.review_reasons),
            "offline_jats_valid": pipeline.validation.valid,
        },
        "approved_xml": {
            **xml_counts,
            "offline_valid": gold_validation.valid,
            "offline_issue_codes": sorted({issue.code for issue in gold_validation.issues}),
            "offline_issue_counts": dict(sorted(gold_issue_counts.items())),
        },
        "pdf": {
            "pages": len(pdf.pages),
            "encrypted": pdf.is_encrypted,
        },
        "figures": {
            "assets": len(image_paths),
            "xml_graphics": len(graphic_names),
            "xml_assets_match": graphic_names == sorted(path.name for path in image_paths),
            "dimensions": image_dimensions,
        },
        "xpm": {
            "version": xpm.xpm_version,
            "blocking_errors": xpm.blocking_errors,
            "fatal_errors": xpm.fatal_errors,
            "errors": xpm.errors,
            "warnings": xpm.warnings,
            "passed": xpm.passed,
            "report_sha256": xpm.report_sha256,
        },
        "expected": manifest["expected"],
    }
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
