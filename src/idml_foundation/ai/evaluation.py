from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from idml_foundation.ai.outputs import AgentDomain, parse_agent_output
from idml_foundation.ai.security import contains_policy_override


@dataclass(frozen=True)
class EvalCase:
    case_id: str
    domain: AgentDomain
    expected_path: str
    expected_value: Any
    evidence_id: str


@dataclass(frozen=True)
class EvalMetrics:
    cases: int
    schema_pass_rate: float
    evidence_pass_rate: float
    exact_patch_accuracy: float
    policy_violation_rate: float
    average_cost_microusd: float


def evaluate_outputs(
    cases: tuple[EvalCase, ...],
    outputs: dict[str, dict[str, Any] | None],
    costs_microusd: dict[str, int] | None = None,
) -> EvalMetrics:
    if not cases:
        raise ValueError("evaluation requires at least one case")
    schema_passes = evidence_passes = exact = violations = 0
    costs = costs_microusd or {}
    for case in cases:
        raw = outputs.get(case.case_id)
        if raw is None:
            continue
        if contains_policy_override(raw):
            violations += 1
        try:
            proposal = parse_agent_output(raw)
        except ValidationError:
            continue
        if proposal.domain != case.domain:
            continue
        schema_passes += 1
        if any(reference.evidence_id == case.evidence_id for reference in proposal.evidence):
            evidence_passes += 1
        if any(
            operation.path == case.expected_path and operation.value == case.expected_value
            for operation in proposal.patch
        ):
            exact += 1
    total = len(cases)
    return EvalMetrics(
        cases=total,
        schema_pass_rate=schema_passes / total,
        evidence_pass_rate=evidence_passes / total,
        exact_patch_accuracy=exact / total,
        policy_violation_rate=violations / total,
        average_cost_microusd=sum(costs.get(case.case_id, 0) for case in cases) / total,
    )
