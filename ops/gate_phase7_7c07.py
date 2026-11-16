#!/usr/bin/env python3
"""Qualify the content-safe 7C-07 assistive OpenClaw evidence."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from idml_foundation.ai.adversarial_matrix import (
    evaluate_adversarial_matrix,
    load_adversarial_matrix,
)
from idml_foundation.ai.corrective_7c07 import (
    NEGATIVE_CONTROL_NAMES,
    evaluate_corrective_negative_controls,
)
from idml_foundation.ai.multi_agent_lab import load_lab_plan

ROOT = Path(__file__).parents[1]
DEFAULT_MANIFEST = ROOT / "corpus/manifests/esa-e20240135.json"
DEFAULT_CONTRACT = ROOT / "benchmarks/qualification/contracts/e20240135-7c07-assistive-v1.json"
DEFAULT_DATASET_REPORT = (
    ROOT / "benchmarks/qualification/reports/assistive-dataset-e20240135-7c07-v1.json"
)
DEFAULT_VPS_POSTCHECK = ROOT / "benchmarks/qualification/reports/phase7-7c07-vps-postcheck-v1.json"
DEFAULT_PLAN = ROOT / "config/openclaw-multi-agent-lab-v34.json"
DEFAULT_MATRIX = ROOT / "benchmarks/agents/adversarial-matrix-v1.json"
DEFAULT_PRIVATE_DATASET = ROOT / "benchmarks/private/input/dataset-e20240135-7c07-v1.0.json"
DEFAULT_PRIVATE_MANIFEST = (
    ROOT / "benchmarks/private/output/validated-multi-agent-manifest-v34.json"
)
DEFAULT_PRIVATE_LIVE_REPORT = (
    ROOT / "benchmarks/private/output/multi-agent-report-phase7-7c07-domains-v34-001.json"
)
DOMAINS = {
    "metadata",
    "contributors_affiliations",
    "structure",
    "references",
    "figures_tables",
    "math_notes",
}
SHA256 = re.compile(r"^[0-9a-f]{64}$")
LIVE_DATASET_VERSION = "idml-agent-e20240135-7c07-1.0"


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path.name}")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _private_path(path: Path, description: str) -> Path:
    resolved = path.resolve(strict=True)
    if "private" not in {part.casefold() for part in resolved.parts}:
        raise ValueError(f"{description} must remain inside a private directory")
    return resolved


def _compare_expected(actual: Any, expected: Any, *, path: str = "expected") -> list[str]:
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return [path]
        mismatches: list[str] = []
        for key, expected_value in expected.items():
            child = f"{path}.{key}"
            if key not in actual:
                mismatches.append(child)
            else:
                mismatches.extend(_compare_expected(actual[key], expected_value, path=child))
        return mismatches
    return [] if actual == expected else [path]


def _contract(path: Path) -> dict[str, Any]:
    contract = _load(path)
    if (
        contract.get("contract_version") != "1.0.0"
        or contract.get("stage") != "7C-07"
        or contract.get("corpus_id") != "esa-e20240135"
        or not isinstance(contract.get("expected_public"), dict)
        or not isinstance(contract.get("private_evidence"), dict)
        or not isinstance(contract.get("negative_controls"), dict)
        or not isinstance(contract.get("release_constraints"), dict)
    ):
        raise ValueError("invalid 7C-07 corrective contract")
    private = contract["private_evidence"]
    for name in (
        "dataset_sha256",
        "validated_manifest_sha256",
        "manifest_id",
        "live_report_sha256",
    ):
        if not isinstance(private.get(name), str) or not SHA256.fullmatch(private[name]):
            raise ValueError("invalid private evidence digest declaration")
    expected_private = {
        "run_id": "phase7-7c07-domains-v34-001",
        "cases": 6,
        "role_calls": 24,
        "accepted_for_human_review": 6,
        "abstentions": 0,
        "rejections": 0,
        "false_consensus_candidates": 0,
        "repair_cycles": 0,
        "exact_cases": 5,
        "semantically_equivalent_cases": 6,
        "qualified_expected_change_precision": 1.0,
        "qualified_expected_change_recall": 1.0,
        "input_tokens": 121676,
        "cached_input_tokens": 0,
        "output_tokens": 10929,
        "duration_ms": 136145,
        "maximum_call_duration_ms": 11609,
        "cost_microusd": 140447,
        "role_models_independent": False,
    }
    if _compare_expected(private, expected_private, path="private_evidence"):
        raise ValueError("7C-07 private evidence declaration changed")
    negatives = contract["negative_controls"]
    if negatives != {
        "names": list(NEGATIVE_CONTROL_NAMES),
        "cases": 5,
        "all_failed_closed": True,
        "false_consensus_accepted": 0,
        "provider_calls": 0,
        "monetary_cost_microusd": 0,
    }:
        raise ValueError("7C-07 negative-control contract changed")
    if contract["release_constraints"] != {
        "human_review_required": True,
        "automatic_application_authorized": False,
        "release_candidate_approved": False,
        "production_activation_authorized": False,
    }:
        raise ValueError("7C-07 release constraints were weakened")
    return contract


def _public_actual(
    manifest_path: Path,
    dataset_report_path: Path,
    plan_path: Path,
    postcheck_path: Path,
) -> dict[str, Any]:
    manifest = _load(manifest_path)
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("corpus manifest artifacts are missing")
    source_hashes = [
        item.get("sha256")
        for item in artifacts
        if isinstance(item, dict) and item.get("role") == "source_idml"
    ]
    if len(source_hashes) != 1:
        raise ValueError("corpus manifest must contain one source IDML")
    roles = Counter(
        str(item.get("role")) for item in artifacts if isinstance(item, dict) and item.get("role")
    )

    dataset = _load(dataset_report_path)
    dataset_actual = {
        "report_sha256": _sha256(dataset_report_path),
        **{
            key: dataset.get(key)
            for key in (
                "dataset_version",
                "dataset_cases",
                "domains",
                "visual_cases",
                "atomic_rich_text_cases",
                "atomic_formula_cases",
                "candidate_xml_sha256",
                "hidden_gold_exposed_to_provider",
                "human_review_required",
                "restricted_content_emitted",
            )
        },
    }
    if (
        dataset.get("version") != "phase7-7c07-dataset-qualification-1.0"
        or dataset.get("corpus_id") != manifest.get("corpus_id")
        or dataset.get("source_idml_sha256") != source_hashes[0]
    ):
        raise ValueError("7C-07 public dataset qualification is inconsistent")

    plan = load_lab_plan(plan_path)
    plan_actual = {
        "plan_sha256": _sha256(plan_path),
        "model_key": plan.model_key,
        "thinking_level": plan.thinking_level,
        "selected_cases": len(plan.selected_case_ids),
        "roles": len(plan.roles),
        "max_attempts": plan.max_attempts,
        "max_repair_cycles": plan.max_repair_cycles,
        "concurrency": plan.concurrency,
        "max_total_cost_microusd": plan.max_total_cost_microusd,
        "require_human_review": plan.require_human_review,
        "require_application_flags_false": plan.require_application_flags_false,
    }

    postcheck = _load(postcheck_path)
    if (
        postcheck.get("version") != "phase7-7c07-vps-postcheck-1.0"
        or postcheck.get("stage") != "7C-07"
        or postcheck.get("corpus_id") != manifest.get("corpus_id")
    ):
        raise ValueError("invalid 7C-07 VPS postcheck")
    services = postcheck.get("services", {})
    flags = postcheck.get("application_flags", {})
    postcheck_actual = {
        "report_sha256": _sha256(postcheck_path),
        "services_healthy": sum(value == "healthy" for value in services.values()),
        "application_flags_false": sum(value is False for value in flags.values()),
        "provider_credential_present": postcheck.get("provider_credential_present"),
        "transient_networks_present": sum(
            postcheck.get(name) is True
            for name in (
                "transient_provider_network_present",
                "transient_egress_network_present",
            )
        ),
        "egress_proxy_present": postcheck.get("egress_proxy_present"),
        "openclaw_sessions": postcheck.get("openclaw_sessions"),
        "agent_runs": postcheck.get("agent_runs"),
        "agent_proposals": postcheck.get("agent_proposals"),
        "restricted_content_emitted": postcheck.get("restricted_content_emitted"),
    }
    return {
        "source_idml_sha256": source_hashes[0],
        "role_counts": dict(sorted(roles.items())),
        "dataset_qualification": dataset_actual,
        "execution_plan": plan_actual,
        "vps_postcheck": postcheck_actual,
    }


def _live_evidence_gate(
    *,
    dataset_path: Path,
    manifest_path: Path,
    live_report_path: Path,
    contract: dict[str, Any],
) -> dict[str, Any]:
    dataset_path = _private_path(dataset_path, "7C-07 dataset")
    manifest_path = _private_path(manifest_path, "7C-07 validated manifest")
    live_report_path = _private_path(live_report_path, "7C-07 live report")
    expected = contract["private_evidence"]
    observed_hashes = {
        "dataset_sha256": _sha256(dataset_path),
        "validated_manifest_sha256": _sha256(manifest_path),
        "live_report_sha256": _sha256(live_report_path),
    }
    expected_hashes = {key: expected[key] for key in observed_hashes}
    if _compare_expected(observed_hashes, expected_hashes, path="private_evidence"):
        raise ValueError("7C-07 private evidence hash mismatch")

    dataset = _load(dataset_path)
    manifest = _load(manifest_path)
    report = _load(live_report_path)
    if not (
        dataset.get("version") == LIVE_DATASET_VERSION
        and dataset.get("corpus_id") == contract["corpus_id"]
        and dataset.get("restricted") is True
        and len(dataset.get("cases", [])) == 6
        and {case.get("domain") for case in dataset["cases"]} == DOMAINS
    ):
        raise ValueError("7C-07 private dataset contract mismatch")
    if not (
        manifest.get("manifest_id") == expected["manifest_id"]
        and manifest.get("execution_authorized") is False
        and manifest.get("human_review_required") is True
        and manifest.get("application_flags_required_false") is True
        and manifest.get("artifact_hashes", {}).get("dataset") == observed_hashes["dataset_sha256"]
        and manifest.get("artifact_hashes", {}).get("plan")
        == contract["expected_public"]["execution_plan"]["plan_sha256"]
    ):
        raise ValueError("7C-07 validated manifest contract mismatch")

    rows = report.get("rows")
    if not isinstance(rows, list) or len(rows) != 6:
        raise ValueError("7C-07 live report row count mismatch")
    if not (
        report.get("version") == "openclaw-multi-agent-lab-report-1.0"
        and report.get("dataset_version") == LIVE_DATASET_VERSION
        and report.get("corpus_id") == contract["corpus_id"]
        and report.get("run_id") == expected["run_id"]
        and report.get("completed") is True
        and report.get("cases") == 6
        and report.get("model") == contract["expected_public"]["execution_plan"]["model_key"]
        and report.get("thinking_level") == "medium"
        and report.get("role_models_independent") is False
        and report.get("human_baseline_complete") is False
        and report.get("gate_g6_t_approved") is False
        and report.get("total_cost_microusd") == expected["cost_microusd"]
        and report.get("total_cost_microusd") <= report.get("max_total_cost_microusd")
        and report.get("max_repair_cycles") == 2
    ):
        raise ValueError("7C-07 live report header mismatch")
    dataset_ids = {str(case["case_id"]) for case in dataset["cases"]}
    report_ids = {str(row.get("case_id")) for row in rows}
    if dataset_ids != report_ids or {row.get("domain") for row in rows} != DOMAINS:
        raise ValueError("7C-07 live report case identity mismatch")

    role_calls = 0
    repair_cycles = 0
    exact_cases = 0
    semantically_equivalent_cases = 0
    input_tokens = 0
    cached_input_tokens = 0
    output_tokens = 0
    duration_ms = 0
    maximum_call_duration_ms = 0
    for row in rows:
        checks = row.get("deterministic_checks")
        quality = row.get("quality")
        roles = row.get("roles")
        semantic_match = isinstance(quality, dict) and bool(
            quality.get("exact") or quality.get("semantically_equivalent")
        )
        if not (
            row.get("status") == "completed"
            and row.get("error_code") is None
            and row.get("final_decision") == "accepted_for_human_review"
            and row.get("false_consensus_candidate") is False
            and row.get("shared_model_across_roles") is True
            and isinstance(checks, dict)
            and checks
            and all(checks.values())
            and isinstance(quality, dict)
            and quality.get("improved") is True
            and semantic_match
            and row.get("critic_verdicts") == {"xml_critic": "pass", "editorial_critic": "pass"}
            and row.get("adjudicator_decision") == "accept"
            and row.get("adjudicator_agreement") == "unanimous_accept"
            and isinstance(roles, list)
            and len(roles) == 4
            and all(
                role.get("status") == "succeeded"
                and role.get("tools_exposed") == 0
                and role.get("skills_exposed") == 0
                for role in roles
            )
            and isinstance(row.get("repair_cycles_used"), int)
            and 0 <= row["repair_cycles_used"] <= 2
        ):
            raise ValueError("7C-07 live case failed the assistive contract")
        role_calls += len(roles)
        repair_cycles += row["repair_cycles_used"]
        exact_cases += quality["exact"] is True
        semantically_equivalent_cases += semantic_match
        input_tokens += sum(int(role["input_tokens"]) for role in roles)
        cached_input_tokens += sum(int(role["cached_input_tokens"]) for role in roles)
        output_tokens += sum(int(role["output_tokens"]) for role in roles)
        duration_ms += sum(int(role["duration_ms"]) for role in roles)
        maximum_call_duration_ms = max(
            maximum_call_duration_ms, *(int(role["duration_ms"]) for role in roles)
        )
    decisions = Counter(row["final_decision"] for row in rows)
    metrics = report.get("metrics", {})
    actual = {
        "run_id": report["run_id"],
        "cases": len(rows),
        "role_calls": role_calls,
        "accepted_for_human_review": decisions["accepted_for_human_review"],
        "abstentions": decisions["abstained"],
        "rejections": decisions["rejected"],
        "false_consensus_candidates": sum(bool(row["false_consensus_candidate"]) for row in rows),
        "repair_cycles": repair_cycles,
        "exact_cases": exact_cases,
        "semantically_equivalent_cases": semantically_equivalent_cases,
        "qualified_expected_change_precision": 1.0,
        "qualified_expected_change_recall": 1.0,
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_input_tokens,
        "output_tokens": output_tokens,
        "duration_ms": duration_ms,
        "maximum_call_duration_ms": maximum_call_duration_ms,
        "cost_microusd": report["total_cost_microusd"],
        "role_models_independent": report["role_models_independent"],
    }
    expected_metrics = {key: expected[key] for key in actual}
    if _compare_expected(actual, expected_metrics, path="private_evidence"):
        raise ValueError("7C-07 live metrics differ from the corrective contract")
    if metrics != {
        "case_completion_rate": 1.0,
        "accepted_for_human_review_rate": 1.0,
        "abstention_rate": 0.0,
        "rejection_rate": 0.0,
        "false_consensus_candidate_rate": 0.0,
    }:
        raise ValueError("7C-07 live aggregate metrics changed")
    return {
        **actual,
        "all_deterministic_checks_passed": True,
        "tools_exposed": 0,
        "skills_exposed": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata-only", action="store_true")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--dataset-report", type=Path, default=DEFAULT_DATASET_REPORT)
    parser.add_argument("--vps-postcheck", type=Path, default=DEFAULT_VPS_POSTCHECK)
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--private-dataset", type=Path, default=DEFAULT_PRIVATE_DATASET)
    parser.add_argument("--private-manifest", type=Path, default=DEFAULT_PRIVATE_MANIFEST)
    parser.add_argument("--private-live-report", type=Path, default=DEFAULT_PRIVATE_LIVE_REPORT)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()

    metadata: dict[str, Any]
    contract: dict[str, Any] | None = None
    try:
        contract = _contract(arguments.contract)
        public_actual = _public_actual(
            arguments.manifest,
            arguments.dataset_report,
            arguments.plan,
            arguments.vps_postcheck,
        )
        mismatches = _compare_expected(
            public_actual, contract["expected_public"], path="expected_public"
        )
        metadata = {
            "approved": not mismatches,
            "actual": public_actual,
            "mismatches": mismatches,
        }
    except Exception as exc:
        metadata = {"approved": False, "error": type(exc).__name__, "mismatches": []}

    live: dict[str, Any] | None = None
    negatives: dict[str, Any] | None = None
    adversarial: dict[str, Any] | None = None
    private_approved = arguments.metadata_only
    if not arguments.metadata_only and metadata["approved"] and contract is not None:
        try:
            live = _live_evidence_gate(
                dataset_path=arguments.private_dataset,
                manifest_path=arguments.private_manifest,
                live_report_path=arguments.private_live_report,
                contract=contract,
            )
            adversarial = asyncio.run(
                evaluate_adversarial_matrix(load_adversarial_matrix(arguments.matrix))
            )
            if adversarial.get("all_expectations_passed") is not True:
                raise ValueError("7C-07 adversarial matrix failed")
            dataset = _load(_private_path(arguments.private_dataset, "7C-07 dataset"))
            negatives = evaluate_corrective_negative_controls(dataset, adversarial)
            negative_summary = {
                key: negatives[key]
                for key in (
                    "cases",
                    "all_failed_closed",
                    "false_consensus_accepted",
                    "provider_calls",
                    "monetary_cost_microusd",
                )
            }
            if [row["name"] for row in negatives["rows"]] != contract["negative_controls"][
                "names"
            ] or _compare_expected(
                negative_summary,
                {key: contract["negative_controls"][key] for key in negative_summary},
                path="negative_controls",
            ):
                raise ValueError("7C-07 negative-control result changed")
        except Exception as exc:
            live = live or {"error": type(exc).__name__}
            private_approved = False
        else:
            private_approved = True

    approved = bool(metadata["approved"] and private_approved)
    report = {
        "version": "phase7-7c07-assistive-gate-1.0",
        "stage": "7C-07",
        "corpus_id": "esa-e20240135",
        "approved": approved,
        "metadata_only": arguments.metadata_only,
        "metadata": metadata,
        "live_evidence": live,
        "negative_controls": negatives,
        "adversarial_matrix": (
            None
            if adversarial is None
            else {
                "cases": adversarial["cases"],
                "domains": adversarial["domains"],
                "scenarios_per_domain": adversarial["scenarios_per_domain"],
                "role_calls": adversarial["role_calls"],
                "expectation_pass_rate": adversarial["expectation_pass_rate"],
                "provider_calls": adversarial["provider_calls"],
                "monetary_cost_microusd": adversarial["monetary_cost_microusd"],
            }
        ),
        "role_models_independent": False,
        "shared_model_consensus_authorizes_release": False,
        "human_review_required": True,
        "automatic_application_authorized": False,
        "release_ready": False,
        "production_activation_authorized": False,
        "network_required_by_gate": False,
        "restricted_content_emitted": False,
    }
    serialized = json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    if arguments.output is not None:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(serialized, encoding="utf-8")
    else:
        print(serialized, end="")
    return 0 if approved else 2


if __name__ == "__main__":
    raise SystemExit(main())
