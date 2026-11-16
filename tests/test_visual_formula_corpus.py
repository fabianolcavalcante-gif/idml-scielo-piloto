from __future__ import annotations

import json

import pytest

from idml_foundation.ai.evidence import visual_evidence_bytes
from idml_foundation.ai.visual_formula_corpus import (
    PdfFormulaCrop,
    attach_visual_formula_evidence,
)


def _dataset() -> dict[str, object]:
    return {
        "restricted": True,
        "cases": [
            {
                "case_id": "esa-math-notes-inline-001",
                "expected_value": "hidden gold MathML",
                "evidence": {"excerpt": "hidden gold MathML"},
                "alternatives": ["hidden gold MathML"],
                "atomic_formula": {
                    "current_representation": "unknown",
                    "display": False,
                },
                "fixture_provenance": {"kind": "gold"},
            }
        ],
    }


def test_attach_visual_formula_evidence_keeps_gold_hidden_from_agent_fields() -> None:
    image = b"\x89PNG\r\n\x1a\nformula"
    result = attach_visual_formula_evidence(
        _dataset(),
        case_id="esa-math-notes-inline-001",
        image_data=image,
        source_pdf_name="private/path/source.pdf",
        crop=PdfFormulaCrop(page_index=2, bbox=(35.0, 742.0, 290.0, 780.0)),
    )
    case = result["cases"][0]

    assert case["expected_value"] == "hidden gold MathML"
    assert case["grounding_policy"] == "visual_formula"
    assert visual_evidence_bytes(case["evidence"]) == image
    assert case["evidence"]["locator"].startswith("source.pdf#page=3&bbox=")
    agent_visible = json.dumps(
        {"evidence": case["evidence"], "alternatives": case["alternatives"]}
    ).replace(case["evidence"]["image_base64"], "")
    assert "hidden gold MathML" not in agent_visible
    assert case["fixture_provenance"]["gold_exposed_to_agent"] is False


def test_attach_visual_formula_evidence_rejects_missing_or_non_atomic_case() -> None:
    with pytest.raises(ValueError, match="exactly once"):
        attach_visual_formula_evidence(
            _dataset(),
            case_id="absent-case",
            image_data=b"\x89PNG\r\n\x1a\nformula",
            source_pdf_name="source.pdf",
            crop=PdfFormulaCrop(page_index=0, bbox=(1, 1, 2, 2)),
        )
    dataset = _dataset()
    del dataset["cases"][0]["atomic_formula"]
    with pytest.raises(ValueError, match="atomic formula"):
        attach_visual_formula_evidence(
            dataset,
            case_id="esa-math-notes-inline-001",
            image_data=b"\x89PNG\r\n\x1a\nformula",
            source_pdf_name="source.pdf",
            crop=PdfFormulaCrop(page_index=0, bbox=(1, 1, 2, 2)),
        )
