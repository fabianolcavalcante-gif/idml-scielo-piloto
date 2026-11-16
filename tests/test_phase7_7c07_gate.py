from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from ops.gate_phase7_7c07 import (
    DEFAULT_CONTRACT,
    DOMAINS,
    LIVE_DATASET_VERSION,
    _contract,
    _live_evidence_gate,
    _load,
)

ROOT = Path(__file__).parents[1]
GATE = ROOT / "ops/gate_phase7_7c07.py"
DATASET_REPORT = ROOT / "benchmarks/qualification/reports/assistive-dataset-e20240135-7c07-v1.json"


def _run_gate(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed interpreter/gate and test-controlled arguments
        [sys.executable, str(GATE), *arguments],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_phase7_7c07_metadata_gate_is_content_safe_and_approved() -> None:
    completed = _run_gate("--metadata-only")
    report = json.loads(completed.stdout)

    assert completed.returncode == 0
    assert report["approved"] is True
    assert report["metadata"]["approved"] is True
    assert report["metadata"]["actual"]["dataset_qualification"]["dataset_cases"] == 6
    assert report["metadata"]["actual"]["execution_plan"]["roles"] == 4
    assert report["metadata"]["actual"]["vps_postcheck"]["services_healthy"] == 3
    assert report["restricted_content_emitted"] is False
    assert report["release_ready"] is False
    assert report["human_review_required"] is True


def test_phase7_7c07_metadata_gate_rejects_tampered_dataset_report(
    tmp_path: Path,
) -> None:
    dataset = _load(DATASET_REPORT)
    dataset["dataset_cases"] = 5
    tampered = tmp_path / "dataset-report.json"
    tampered.write_text(json.dumps(dataset), encoding="utf-8")

    completed = _run_gate("--metadata-only", "--dataset-report", str(tampered))
    report = json.loads(completed.stdout)

    assert completed.returncode == 2
    assert report["approved"] is False
    assert "expected_public.dataset_qualification.report_sha256" in report["metadata"]["mismatches"]
    assert "expected_public.dataset_qualification.dataset_cases" in report["metadata"]["mismatches"]


def test_phase7_7c07_metadata_gate_rejects_weakened_contract(tmp_path: Path) -> None:
    contract = _load(DEFAULT_CONTRACT)
    contract["negative_controls"]["names"].remove("wrong_asset_association")
    tampered = tmp_path / "contract.json"
    tampered.write_text(json.dumps(contract), encoding="utf-8")

    completed = _run_gate("--metadata-only", "--contract", str(tampered))
    report = json.loads(completed.stdout)

    assert completed.returncode == 2
    assert report["approved"] is False
    assert report["metadata"]["error"] == "ValueError"


@pytest.mark.parametrize("mutation", [None, "false_consensus", "missing_quality"])
def test_phase7_7c07_live_contract_with_synthetic_evidence(
    tmp_path: Path, mutation: str | None
) -> None:
    contract = _contract(DEFAULT_CONTRACT)
    expected = contract["private_evidence"]
    plan = contract["expected_public"]["execution_plan"]
    private = tmp_path / "private"
    private.mkdir()

    def save(name: str, value: dict, hash_key: str) -> Path:
        path = private / name
        path.write_text(json.dumps(value), encoding="utf-8")
        expected[hash_key] = hashlib.sha256(path.read_bytes()).hexdigest()
        return path

    cases = [{"case_id": f"synthetic-{i}", "domain": d} for i, d in enumerate(sorted(DOMAINS))]
    dataset = save(
        "dataset.json",
        {
            "version": LIVE_DATASET_VERSION,
            "corpus_id": contract["corpus_id"],
            "restricted": True,
            "cases": cases,
        },
        "dataset_sha256",
    )
    manifest = save(
        "manifest.json",
        {
            "manifest_id": expected["manifest_id"],
            "execution_authorized": False,
            "human_review_required": True,
            "application_flags_required_false": True,
            "artifact_hashes": {"dataset": expected["dataset_sha256"], "plan": plan["plan_sha256"]},
        },
        "validated_manifest_sha256",
    )
    roles = []
    for i in range(24):
        duration = 11609 if i == 0 else 5414 + (i <= 14)
        roles.append(
            {
                "status": "succeeded",
                "tools_exposed": 0,
                "skills_exposed": 0,
                "input_tokens": 121676 if i == 0 else 0,
                "cached_input_tokens": 0,
                "output_tokens": 10929 if i == 0 else 0,
                "duration_ms": duration,
            }
        )
    rows = [
        {
            **case,
            "status": "completed",
            "error_code": None,
            "final_decision": "accepted_for_human_review",
            "false_consensus_candidate": False,
            "shared_model_across_roles": True,
            "deterministic_checks": {"synthetic": True},
            "quality": {"exact": i != 5, "semantically_equivalent": True, "improved": True},
            "critic_verdicts": {"xml_critic": "pass", "editorial_critic": "pass"},
            "adjudicator_decision": "accept",
            "adjudicator_agreement": "unanimous_accept",
            "roles": roles[i * 4 : i * 4 + 4],
            "repair_cycles_used": 0,
        }
        for i, case in enumerate(cases)
    ]
    if mutation == "false_consensus":
        rows[0]["false_consensus_candidate"] = True
    elif mutation == "missing_quality":
        rows[0]["quality"] = None
    report = save(
        "report.json",
        {
            "version": "openclaw-multi-agent-lab-report-1.0",
            "dataset_version": LIVE_DATASET_VERSION,
            "corpus_id": contract["corpus_id"],
            "run_id": expected["run_id"],
            "completed": True,
            "cases": 6,
            "model": plan["model_key"],
            "thinking_level": "medium",
            "role_models_independent": False,
            "human_baseline_complete": False,
            "gate_g6_t_approved": False,
            "total_cost_microusd": expected["cost_microusd"],
            "max_total_cost_microusd": expected["cost_microusd"],
            "max_repair_cycles": 2,
            "rows": rows,
            "metrics": {
                "case_completion_rate": 1.0,
                "accepted_for_human_review_rate": 1.0,
                "abstention_rate": 0.0,
                "rejection_rate": 0.0,
                "false_consensus_candidate_rate": 0.0,
            },
        },
        "live_report_sha256",
    )
    arguments = dict(
        dataset_path=dataset, manifest_path=manifest, live_report_path=report, contract=contract
    )
    if mutation:
        with pytest.raises(ValueError, match="live case"):
            _live_evidence_gate(**arguments)
    else:
        assert _live_evidence_gate(**arguments)["all_deterministic_checks_passed"] is True
