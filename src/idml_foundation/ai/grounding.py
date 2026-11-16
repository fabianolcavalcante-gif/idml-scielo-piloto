from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Any, Literal

from idml_foundation.domain.metrics import normalize_text

GroundingPolicy = Literal["normalized_exact"]
DEFAULT_GROUNDING_POLICY: GroundingPolicy = "normalized_exact"


@dataclass(frozen=True)
class GroundingAssessment:
    supported: bool
    policy: GroundingPolicy
    reason: Literal["normalized_exact", "value_type_unsupported", "content_not_supported"]


def _normalized_grounding_text(value: str) -> str:
    return normalize_text(unicodedata.normalize("NFKC", value))


def assess_evidence_grounding(
    proposed_value: Any,
    evidence_excerpt: str,
    *,
    policy: GroundingPolicy = DEFAULT_GROUNDING_POLICY,
) -> GroundingAssessment:
    """Prove lexical support without consulting the hidden evaluation target."""
    if policy != DEFAULT_GROUNDING_POLICY:
        raise ValueError("unsupported evidence grounding policy")
    if not isinstance(proposed_value, str):
        return GroundingAssessment(
            supported=False,
            policy=policy,
            reason="value_type_unsupported",
        )
    proposed = _normalized_grounding_text(proposed_value)
    evidence = _normalized_grounding_text(evidence_excerpt)
    supported = bool(proposed) and proposed == evidence
    return GroundingAssessment(
        supported=supported,
        policy=policy,
        reason="normalized_exact" if supported else "content_not_supported",
    )
