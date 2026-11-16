from __future__ import annotations

from dataclasses import dataclass

from idml_foundation.ai.outputs import AgentProposalOutput


@dataclass(frozen=True)
class AssistiveDecision:
    disposition: str
    requires_human: bool
    repair_cycles_allowed: int
    release_advice: str


def route_proposal(
    proposal: AgentProposalOutput,
    *,
    confidence_threshold: float = 0.85,
    max_repair_cycles: int = 2,
) -> AssistiveDecision:
    """Route a validated suggestion; agents never apply changes or approve release."""
    if not 0.0 <= confidence_threshold <= 1.0:
        raise ValueError("invalid confidence threshold")
    if not 0 <= max_repair_cycles <= 2:
        raise ValueError("semantic repair exceeds the policy cap")
    low_confidence = proposal.confidence < confidence_threshold or proposal.needs_human
    return AssistiveDecision(
        disposition="human_review_required",
        requires_human=True,
        repair_cycles_allowed=max_repair_cycles if not low_confidence else 0,
        release_advice="consultative_only_not_ready",
    )
