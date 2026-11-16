from typing import Any

from ops.score_openclaw_eval import score


def _payloads(version: str) -> tuple[dict[str, Any], dict[str, Any]]:
    dataset = {
        "version": version,
        "cases": [
            {
                "case_id": "case-1",
                "domain": "metadata",
                "field_path": "/front/titles/0/text/value",
                "expected_value": "Expected",
                "evidence": {
                    "evidence_id": "evidence-1",
                    "source_kind": "canonical",
                    "locator": "fixture",
                    "excerpt_sha256": "a" * 64,
                },
            }
        ],
    }
    results = {
        "version": version,
        "agent": "fixture-agent",
        "model": "fixture-model",
        "max_input_tokens": 100,
        "max_output_tokens": 100,
        "cost_observed": False,
        "cases": [
            {
                "case_id": "case-1",
                "status": "failed",
                "output": None,
                "tools_exposed": None,
                "skills_exposed": None,
                "input_tokens": 0,
                "output_tokens": 0,
                "duration_ms": 1,
            }
        ],
    }
    return dataset, results


def test_score_distinguishes_restricted_real_corpus_from_synthetic() -> None:
    real = score(*_payloads("idml-agent-initial-corpus-eval-1.1"))
    synthetic = score(*_payloads("idml-agent-synthetic-pilot-1.0"))

    assert real["dataset_version"] == "idml-agent-initial-corpus-eval-1.1"
    assert real["restricted"] is True
    assert real["synthetic_only"] is False
    assert synthetic["restricted"] is False
    assert synthetic["synthetic_only"] is True


def test_score_requires_both_sides_of_atomic_rich_text_patch() -> None:
    dataset, results = _payloads("idml-agent-initial-corpus-eval-1.2")
    case = dataset["cases"][0]
    case["domain"] = "figures_tables"
    case["field_path"] = "/body/0/blocks/1/caption/plain/value"
    case["atomic_rich_text"] = {
        "root_path": "/body/0/blocks/1/caption",
        "current_inlines": [],
        "required_patch_paths": [
            "/body/0/blocks/1/caption/plain/value",
            "/body/0/blocks/1/caption/inlines",
        ],
    }
    result = results["cases"][0]
    result.update(
        status="succeeded",
        tools_exposed=0,
        skills_exposed=0,
        output={
            "schema_version": "agent-proposal-1.1",
            "domain": "figures_tables",
            "patch": [
                {
                    "op": "replace",
                    "path": case["field_path"],
                    "value": "Expected",
                    "evidence_ids": ["evidence-1"],
                }
            ],
            "confidence": 0.9,
            "evidence": [case["evidence"]],
            "alternatives": ["Keep current"],
            "reason": "The supplied evidence supports the corrected complete caption.",
            "needs_human": True,
        },
    )
    assert score(dataset, results)["metrics"]["exact_patch_accuracy"] == 0

    result["output"]["patch"].append(
        {
            "op": "replace",
            "path": case["atomic_rich_text"]["required_patch_paths"][1],
            "value": [{"id": "inline-1", "kind": "text", "text": "Expected"}],
            "evidence_ids": ["evidence-1"],
        }
    )
    assert score(dataset, results)["metrics"]["exact_patch_accuracy"] == 1
