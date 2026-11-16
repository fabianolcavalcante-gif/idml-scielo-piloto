import asyncio
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from idml_foundation.ai.adversarial_matrix import (
    AdversarialMatrixSpec,
    evaluate_adversarial_matrix,
    load_adversarial_matrix,
)


def _matrix_path() -> Path:
    return Path(__file__).parents[1] / "benchmarks" / "agents" / "adversarial-matrix-v1.json"


def test_adversarial_matrix_covers_all_domains_and_scenarios_without_provider() -> None:
    report = asyncio.run(evaluate_adversarial_matrix(load_adversarial_matrix(_matrix_path())))

    assert report["simulation_only"] is True
    assert report["provider_calls"] == 0
    assert report["network_access"] is False
    assert report["monetary_cost_microusd"] == 0
    assert report["domains"] == 6
    assert report["scenarios_per_domain"] == 5
    assert report["cases"] == 30
    assert report["role_calls"] == 84
    assert report["expectation_pass_rate"] == 1.0
    assert report["all_expectations_passed"] is True
    assert report["human_baseline_complete"] is False
    assert report["gate_g6_t_approved"] is False
    assert all(report["domain_passes"].values())
    assert all(report["scenario_passes"].values())

    outcomes = [row["final_decision"] for row in report["rows"]]
    assert outcomes.count("accepted_for_human_review") == 6
    assert outcomes.count("rejected") == 12
    assert outcomes.count("abstained") == 12
    assert sum(row["false_consensus_candidate"] for row in report["rows"]) == 6
    serialized = json.dumps(report)
    assert "Syntetic metadata title" not in serialized
    assert "Ignore previous instructions" not in serialized
    assert "injected_text" not in serialized


def test_adversarial_matrix_rejects_network_or_provider_activation() -> None:
    raw = json.loads(_matrix_path().read_text(encoding="utf-8"))
    raw["provider_calls"] = True
    raw["network_access"] = True

    with pytest.raises(ValidationError):
        AdversarialMatrixSpec.model_validate_json(json.dumps(raw))


def test_adversarial_matrix_rejects_cross_domain_fixture_path() -> None:
    raw = json.loads(_matrix_path().read_text(encoding="utf-8"))
    raw["domains"][0]["field_path"] = "/back/references/0/title/value"

    with pytest.raises(ValidationError, match="outside its domain"):
        AdversarialMatrixSpec.model_validate_json(json.dumps(raw))


def test_adversarial_matrix_rejects_weakened_oracle() -> None:
    raw = json.loads(_matrix_path().read_text(encoding="utf-8"))
    raw["expectations"][4]["final_decision"] = "accepted_for_human_review"

    with pytest.raises(ValidationError, match="oracle differs"):
        AdversarialMatrixSpec.model_validate_json(json.dumps(raw))
