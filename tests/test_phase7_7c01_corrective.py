from __future__ import annotations

import json
from pathlib import Path

from idml_foundation.pipeline.service import DeterministicPipeline
from idml_foundation.release.corrective_inventory import (
    build_corrective_inventory,
    classify_asset_name,
)
from tests.phase3_helpers import synthetic_idml


def test_corrective_asset_name_classes_are_general_and_case_insensitive() -> None:
    assert classify_asset_name("ESA_2024135_Eq-txt-01.pdf") == "formula"
    assert classify_asset_name("folder/ARTICLE_EQ09.PDF") == "formula"
    assert classify_asset_name("ESA_2024135_Fig07.pdf") == "figure"
    assert classify_asset_name("X.pdf") == "auxiliary-glyph"
    assert classify_asset_name("Selo_CC.png") == "layout-branding"
    assert classify_asset_name("arbitrary-chart.svg") == "other"


def test_corrective_inventory_is_deterministic_and_content_safe() -> None:
    secret = "private article sentence that must never enter the inventory"
    source = synthetic_idml(
        include_formula=True,
        include_inline_formula=True,
        include_graphic_mention=True,
    ).replace(b"Deterministic conversion", secret.encode())
    first = DeterministicPipeline().run(source, logical_name="ESA_2024997_AOP.idml")
    second = DeterministicPipeline().run(source, logical_name="ESA_2024997_AOP.idml")

    first_summary, first_private = build_corrective_inventory(
        first.raw,
        review_reasons=first.canonical.review_reasons,
    )
    second_summary, second_private = build_corrective_inventory(
        second.raw,
        review_reasons=second.canonical.review_reasons,
    )

    assert first_summary == second_summary
    assert first_private == second_private
    assert first_summary.private_inventory_sha256 == second_summary.private_inventory_sha256
    assert first_summary.counts["stories"] == len(first.raw.stories)
    assert first_summary.evidence_coverage["anchored_objects_with_evidence"] == len(
        first.raw.anchored_objects
    )
    assert first_summary.content_emitted is False
    assert secret not in first_summary.model_dump_json()
    assert secret not in json.dumps(first_private)


def test_corrective_public_summary_does_not_emit_asset_paths() -> None:
    source = synthetic_idml(include_formula=True, include_graphic_mention=True)
    result = DeterministicPipeline().run(source, logical_name="ESA_2024996_AOP.idml")

    summary, private = build_corrective_inventory(
        result.raw,
        review_reasons=result.canonical.review_reasons,
    )
    public_payload = summary.model_dump_json()

    for asset in result.raw.assets:
        assert asset.logical_path in json.dumps(private)
        assert asset.logical_path not in public_payload


def test_production_code_has_no_e20240135_special_case() -> None:
    source_root = Path(__file__).parents[1] / "src"
    production_source = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(source_root.rglob("*.py"))
    ).casefold()

    assert "e20240135" not in production_source
    assert "esa_2024135" not in production_source
    assert "48c5c693d0e1a3f5" not in production_source
