from __future__ import annotations

import base64
import hashlib

import pytest

from idml_foundation.ai.corrective_7c07 import (
    DATASET_VERSION,
    build_corrective_7c07_dataset,
    evaluate_corrective_negative_controls,
)
from idml_foundation.domain.canonical import Contributor, ContributorName, Reference
from tests.domain_helpers import RAW_SHA, canonical_article, rich, sourced


def _article():
    article = canonical_article()
    second = Contributor(
        id="contributor-2",
        contributor_type="person",
        name=ContributorName(given_names=sourced("Bruno"), surname=sourced("Souza Neto")),
        affiliation_ids=(article.front.affiliations[0].id,),
        evidence_ids=("evidence-source-1",),
    )
    reference = Reference(
        id="reference-1",
        mixed_citation=rich(
            "Silva A. Article title. Journal, 2025. https://doi.org/10.1234/example"
        ),
        evidence_ids=("evidence-source-1",),
    )
    return article.model_copy(
        update={
            "front": article.front.model_copy(
                update={"contributors": (*article.front.contributors, second)}
            ),
            "back": article.back.model_copy(update={"references": (reference,)}),
        }
    )


def _base_dataset() -> dict[str, object]:
    return {
        "corpus_id": "esa-e20240135",
        "source_idml_sha256": RAW_SHA,
        "cases": [
            {
                "case_id": "esa-structure-derived-001",
                "domain": "structure",
                "field_path": "/body/0/title/value",
                "current_value": "Introductio",
                "expected_value": "Introduction",
                "evidence": {"evidence_id": "structure"},
            },
            {
                "case_id": "esa-math-notes-observed-001",
                "domain": "math_notes",
                "field_path": "/body/0/blocks/2/source/value",
                "current_value": "equation.pdf",
                "expected_value": "<mml:math/>",
                "evidence": {
                    "evidence_id": "formula",
                    "image_base64": "iVBORw0KGgo=",
                },
                "atomic_formula": {},
            },
        ],
    }


def test_corrective_dataset_covers_each_domain_without_public_content() -> None:
    dataset, report = build_corrective_7c07_dataset(
        article=_article(),
        visual_dataset=_base_dataset(),
        corpus_id="esa-e20240135",
        source_idml_sha256=RAW_SHA,
        candidate_xml=b"<article/>",
    )

    assert dataset["version"] == DATASET_VERSION
    assert len(dataset["cases"]) == 6
    assert {case["domain"] for case in dataset["cases"]} == {
        "metadata",
        "contributors_affiliations",
        "structure",
        "references",
        "figures_tables",
        "math_notes",
    }
    assert all(case["current_value"] != case["expected_value"] for case in dataset["cases"])
    assert report["dataset_cases"] == 6
    assert report["visual_cases"] == 1
    assert report["hidden_gold_exposed_to_provider"] is False
    assert report["restricted_content_emitted"] is False
    assert "cases" not in report


def test_corrective_dataset_rejects_a_different_source() -> None:
    visual_dataset = _base_dataset()
    visual_dataset["source_idml_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="visual dataset source hash"):
        build_corrective_7c07_dataset(
            article=_article(),
            visual_dataset=visual_dataset,
            corpus_id="esa-e20240135",
            source_idml_sha256=RAW_SHA,
            candidate_xml=b"<article/>",
        )


def test_corrective_negative_controls_fail_closed_without_provider() -> None:
    dataset, _ = build_corrective_7c07_dataset(
        article=_article(),
        visual_dataset=_base_dataset(),
        corpus_id="esa-e20240135",
        source_idml_sha256=RAW_SHA,
        candidate_xml=b"<article/>",
    )
    image = b"\x89PNG\r\n\x1a\n"
    formula = next(case for case in dataset["cases"] if case["domain"] == "math_notes")
    formula["evidence"] = {
        "evidence_id": "formula",
        "source_kind": "pdf",
        "locator": "page=1;region=formula",
        "image_base64": base64.b64encode(image).decode("ascii"),
        "image_sha256": hashlib.sha256(image).hexdigest(),
        "media_type": "image/png",
        "page_index": 0,
        "bbox": [0.0, 0.0, 10.0, 10.0],
    }
    adversarial = {
        "rows": [
            {
                "domain": "math_notes",
                "scenario": "ambiguous",
                "final_decision": "abstained",
                "false_consensus_candidate": False,
                "expectation_passed": True,
            }
        ]
    }

    result = evaluate_corrective_negative_controls(dataset, adversarial)

    assert result["cases"] == 5
    assert result["all_failed_closed"] is True
    assert result["false_consensus_accepted"] == 0
    assert result["provider_calls"] == 0
    assert {row["name"] for row in result["rows"]} == {
        "omission",
        "invention",
        "author_swap",
        "ambiguous_visual_formula",
        "wrong_asset_association",
    }
