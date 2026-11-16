import copy
import hashlib
import json
from pathlib import Path

import pytest

from ops.gate_phase7_v08 import (
    SUMMARY,
    _contract_mutation_gate,
    _live_report_gate,
    _load,
    _plan_controls_gate,
    _published_evidence_gate,
)


def _role(*, materialized: bool = False) -> dict[str, object]:
    return {
        "tools_exposed": 0,
        "skills_exposed": 0,
        "output_materialized_from_evidence": materialized,
    }


def _row(
    case_id: str,
    domain: str,
    *,
    decision: str = "accepted_for_human_review",
    error_code: str | None = None,
) -> dict[str, object]:
    return {
        "case_id": case_id,
        "domain": domain,
        "final_decision": decision,
        "error_code": error_code,
        "critic_verdicts": (
            {"xml_critic": "reject", "editorial_critic": "pass"}
            if decision == "rejected" and error_code is None
            else {"xml_critic": "pass", "editorial_critic": "pass"}
        ),
        "adjudicator_decision": "accept" if decision != "rejected" else None,
        "adjudicator_agreement": "unanimous_accept" if decision != "rejected" else None,
        "deterministic_checks": {"evidence": True, "contract": True},
        "quality": {"exact": True, "improved": True},
        "roles": [_role(materialized=True), _role(), _role(), _role()],
    }


def _write(path: Path, payload: dict[str, object]) -> str:
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_v08_published_evidence_and_execution_controls_are_complete() -> None:
    published = _published_evidence_gate(_load(SUMMARY))
    controls = _plan_controls_gate()

    assert published["domains"] == 6
    assert published["formula_cases"] == 17
    assert controls == {
        "plans": 2,
        "maximum_attempts": 2,
        "maximum_timeout_seconds": 45,
        "maximum_concurrency": 1,
        "aggregate_budget_microusd": 3_300_000,
    }


def test_v08_contract_mutations_all_fail_closed() -> None:
    result = _contract_mutation_gate()

    assert result["positive_contracts"] == 1
    assert result["negative_contracts"] == 7
    assert set(result["rejected_mutations"]) == {
        "incorrect_evidence_hash",
        "forbidden_path",
        "schema_extra",
        "partial_rich_text",
        "invented_doi",
        "invented_author",
        "unsupported_expansion",
    }


def test_v08_live_reports_require_the_exact_repaired_case(tmp_path: Path) -> None:
    primary_rows = [_row(f"accepted-{index:03d}", "metadata") for index in range(8)]
    primary_rows.extend(
        [
            _row("semantic-rejected-001", "contributors_affiliations", decision="rejected"),
            _row(
                "contract-rejected-001",
                "figures_tables",
                decision="rejected",
                error_code="ADJUDICATION_AGREEMENT_MISMATCH",
            ),
        ]
    )
    primary = {
        "run_id": "phase7-v08-positive-v2",
        "completed": True,
        "cases": 10,
        "total_cost_microusd": 100,
        "max_total_cost_microusd": 200,
        "rows": primary_rows,
    }
    repaired = _row("contract-rejected-001", "figures_tables")
    regression = {
        "run_id": "phase7-v08-adjudicator-v1",
        "completed": True,
        "cases": 1,
        "total_cost_microusd": 10,
        "max_total_cost_microusd": 20,
        "rows": [repaired],
    }
    primary_path = tmp_path / "primary.json"
    regression_path = tmp_path / "regression.json"
    summary = copy.deepcopy(_load(SUMMARY))
    summary["live_positive"]["primary_report_sha256"] = _write(primary_path, primary)
    summary["live_positive"]["regression_report_sha256"] = _write(regression_path, regression)

    metrics = _live_report_gate(primary_path, regression_path, summary)

    assert metrics["effective_cases"] == 10
    assert metrics["effective_accepted_for_human_review"] == 9
    assert metrics["effective_semantic_safety_rejections"] == 1
    assert metrics["role_calls"] == 44

    regression["rows"][0]["case_id"] = "different-case"
    summary["live_positive"]["regression_report_sha256"] = _write(regression_path, regression)
    with pytest.raises(ValueError, match="contract regression"):
        _live_report_gate(primary_path, regression_path, summary)


def test_v08_rejects_hidden_correlated_model_or_production_authority() -> None:
    summary = copy.deepcopy(_load(SUMMARY))
    summary["safety"]["role_models_independent"] = True
    with pytest.raises(ValueError, match="correlated model limitation"):
        _published_evidence_gate(summary)

    summary = copy.deepcopy(_load(SUMMARY))
    summary["production_activation_authorized"] = True
    with pytest.raises(ValueError, match="cannot authorize production"):
        _published_evidence_gate(summary)
