"""Execute the content-free V-05 JATS/SPS construction gate."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path

from lxml import etree

from idml_foundation.pipeline.jats_builder import JatsBuilder
from idml_foundation.pipeline.service import DeterministicPipeline
from idml_foundation.pipeline.validation import OfflineJatsValidator, ValidationStage

sys.path.insert(0, str(Path(__file__).parents[1]))
from ops.v05_fixture import complete_article

Mutation = Callable[[bytes], bytes]
BROKEN_REFERENCE_CODES = {
    "orphan-rid",
    "invalid-bibliography-rid-target",
    "invalid-xref-target",
}


def _insert_before_first_paragraph_end(xml: bytes, value: bytes) -> bytes:
    return xml.replace(b"</p>", value + b"</p>", 1)


def mutation_cases() -> tuple[tuple[str, Mutation, str], ...]:
    return (
        (
            "xml_declaration",
            lambda xml: xml.replace(b" encoding='UTF-8'", b"", 1),
            "invalid-xml-declaration",
        ),
        (
            "doctype",
            lambda xml: xml.replace(b"JATS (Z39.96)", b"UNKNOWN", 1),
            "unexpected-doctype",
        ),
        (
            "sps_version",
            lambda xml: xml.replace(b"sps-1.10", b"sps-9.99", 1),
            "unsupported-sps-version",
        ),
        (
            "issn",
            lambda xml: xml.replace(b"1234-5678", b"invalid"),
            "invalid-issn",
        ),
        (
            "doi",
            lambda xml: xml.replace(b"10.1234/example.article", b"invalid-doi", 1),
            "invalid-doi",
        ),
        (
            "orphan_rid",
            lambda xml: xml.replace(b'rid="figure-1"', b'rid="missing"', 1),
            "orphan-rid",
        ),
        (
            "wrong_rid_type",
            lambda xml: xml.replace(b'ref-type="fig"', b'ref-type="bibr"', 1),
            "invalid-bibliography-rid-target",
        ),
        (
            "asset_traversal",
            lambda xml: xml.replace(b"article-gf01.jpg", b"../escape.jpg", 1),
            "unsafe-asset-reference",
        ),
        (
            "unknown_asset",
            lambda xml: xml.replace(b"article-gf01.jpg", b"unknown.png", 1),
            "unknown-asset-reference",
        ),
        (
            "external_scheme",
            lambda xml: _insert_before_first_paragraph_end(
                xml,
                b'<ext-link ext-link-type="uri" xlink:href="javascript:alert(1)">x</ext-link>',
            ),
            "unsafe-external-link",
        ),
        (
            "invisible_character",
            lambda xml: xml.replace(b"Synthetic title", "Synthetic\u200b title".encode(), 1),
            "forbidden-invisible-character",
        ),
        (
            "duplicate_id",
            lambda xml: xml.replace(b'<table-wrap id="table-1"', b'<table-wrap id="figure-1"', 1),
            "duplicate-xml-id",
        ),
        (
            "invalid_content_model",
            lambda xml: xml.replace(b"</journal-meta>", b"<unknown/></journal-meta>", 1),
            "dtd-dtd-content-model",
        ),
    )


def synthetic_gate(vendor: Path) -> dict[str, int]:
    article = complete_article()
    builder = JatsBuilder()
    validator = OfflineJatsValidator(vendor)
    first = builder.build(article)
    second = builder.build(article)
    if first != second:
        raise AssertionError("same canonical input produced different XML bytes")
    baseline = validator.validate(
        first,
        asset_names={asset.logical_name for asset in article.assets},
    )
    if not baseline.valid:
        raise AssertionError("complete synthetic article did not pass JATS/SPS validation")
    for name, mutate, expected_code in mutation_cases():
        report = validator.validate(
            mutate(first),
            asset_names={asset.logical_name for asset in article.assets},
        )
        if report.valid or expected_code not in {issue.code for issue in report.issues}:
            raise AssertionError(f"negative mutation was not rejected: {name}")
    root = etree.fromstring(first)
    return {
        "negative_cases": len(mutation_cases()),
        "deterministic_builds": 2,
        "xml_ids": len(root.xpath("//*[@id]")),
        "resolved_rids": len(root.xpath("//*[@rid]")),
        "structured_references": len(root.xpath("back/ref-list/ref/element-citation")),
        "merged_cells": len(root.xpath("body//td[@rowspan or @colspan]")),
    }


def verify_real(path: Path, vendor: Path) -> dict[str, object]:
    pipeline = DeterministicPipeline()
    source = path.read_bytes()
    first = pipeline.run(source, logical_name=path.name)
    second = pipeline.run(source, logical_name=path.name)
    if first.xml != second.xml:
        raise AssertionError("real candidate XML is not byte deterministic")
    report = OfflineJatsValidator(vendor).validate(
        first.xml,
        asset_names={asset.logical_name for asset in first.canonical.assets},
    )
    broken_references = sum(issue.code in BROKEN_REFERENCE_CODES for issue in report.issues)
    if broken_references:
        raise AssertionError("real candidate contains a broken XML reference")
    profile_match = path.name.casefold().startswith("esa_")
    if profile_match and not report.valid:
        raise AssertionError("ESA profile candidate did not pass JATS/SPS validation")
    if not profile_match and not first.canonical.review_reasons:
        raise AssertionError("contrast candidate was not explicitly marked for review")
    root = etree.fromstring(first.xml)
    expected_spans = sum(
        len(block.cell_spans)
        for section in first.canonical.body
        for block in section.blocks
        if block.kind == "table"
    )
    actual_spans = len(root.xpath("body//td[@rowspan or @colspan]"))
    if expected_spans != actual_spans:
        raise AssertionError("canonical table spans were not preserved in XML")
    return {
        "profile_match": profile_match,
        "jats_sps_valid": report.valid,
        "xml_well_formed": not any(issue.stage == ValidationStage.XML for issue in report.issues),
        "broken_references": broken_references,
        "canonical_sections": len(first.canonical.body),
        "table_spans": actual_spans,
        "review_reasons": len(first.canonical.review_reasons),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--vendor",
        type=Path,
        default=Path(__file__).parents[1] / "vendor" / "jats" / "1.3",
    )
    parser.add_argument("--real-idml", type=Path, action="append", default=[])
    arguments = parser.parse_args()
    rows: list[dict[str, object]] = []
    try:
        metrics = synthetic_gate(arguments.vendor)
    except Exception as exc:
        rows.append({"case": "synthetic_v05", "passed": False, "error_type": type(exc).__name__})
    else:
        rows.append({"case": "synthetic_v05", "passed": True, "metrics": metrics})

    verified = 0
    profile_matches = 0
    valid_profile_matches = 0
    contrasts = 0
    for index, path in enumerate(arguments.real_idml, start=1):
        try:
            metrics = verify_real(path, arguments.vendor)
        except Exception as exc:
            rows.append(
                {
                    "case": f"real_idml_{index}",
                    "passed": False,
                    "error_type": type(exc).__name__,
                }
            )
        else:
            verified += 1
            profile_matches += int(bool(metrics["profile_match"]))
            valid_profile_matches += int(
                bool(metrics["profile_match"]) and bool(metrics["jats_sps_valid"])
            )
            contrasts += int(not bool(metrics["profile_match"]))
            rows.append({"case": f"real_idml_{index}", "passed": True, "metrics": metrics})

    approved = all(bool(row["passed"]) for row in rows) and verified == len(arguments.real_idml)
    report = {
        "version": "phase7-v05-gate-1.0",
        "family": "V-05",
        "approved": approved,
        "real_packages_requested": len(arguments.real_idml),
        "real_packages_verified": verified,
        "profile_matches": profile_matches,
        "valid_profile_matches": valid_profile_matches,
        "contrast_packages": contrasts,
        "rows": rows,
        "network_required": False,
        "restricted_content_emitted": False,
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if approved else 2


if __name__ == "__main__":
    raise SystemExit(main())
