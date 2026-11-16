from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from idml_foundation.domain.common import SHA256_PATTERN, StrictModel
from idml_foundation.release.fidelity import FidelityReport
from idml_foundation.release.validation_engine import UnifiedValidationReport
from idml_foundation.release.xpm import XpmResult, XpmStatus


class ReleaseDecision(StrEnum):
    READY_FOR_SCIELO = "ready-for-scielo"
    NEEDS_REVIEW = "needs-review"
    BLOCKED = "blocked"
    VALIDATION_UNAVAILABLE = "validation-unavailable"


class ReleaseAssessment(StrictModel):
    policy_version: str = "1.0.0"
    decision: ReleaseDecision
    reasons: tuple[str, ...]
    human_override_id: str | None = None


class HumanReleaseOverride(StrictModel):
    override_id: str
    approved_by_user_id: str
    company_id: str
    justification: str = Field(min_length=20, max_length=2000)
    evidence_sha256: str = Field(pattern=SHA256_PATTERN)
    policy_version: str = "1.0.0"


class ReleasePolicy:
    """Fail closed. No AI or operator may turn missing evidence into READY."""

    def assess(
        self,
        *,
        package_sha256: str,
        validation: UnifiedValidationReport,
        fidelity: FidelityReport,
        xpm: XpmResult,
        review_reasons: tuple[str, ...] = (),
        human_override: HumanReleaseOverride | None = None,
    ) -> ReleaseAssessment:
        if xpm.candidate_package_sha256 != package_sha256:
            return ReleaseAssessment(
                decision=ReleaseDecision.BLOCKED,
                reasons=("xpm-candidate-hash-mismatch",),
            )
        if xpm.status != XpmStatus.COMPLETED or not validation.complete:
            reasons = []
            if xpm.status != XpmStatus.COMPLETED:
                reasons.append(xpm.failure_code or "xpm-unavailable")
            if not validation.complete:
                reasons.append("required-validator-unavailable")
            return ReleaseAssessment(
                decision=ReleaseDecision.VALIDATION_UNAVAILABLE,
                reasons=tuple(reasons),
            )
        blocking: list[str] = []
        if not validation.valid:
            blocking.append("validator-errors")
        if not xpm.passed:
            blocking.append("xpm-errors")
        if not fidelity.passed:
            blocking.append("fidelity-threshold-not-met")
        if blocking:
            return ReleaseAssessment(
                decision=ReleaseDecision.BLOCKED,
                reasons=tuple(blocking),
            )
        if review_reasons:
            if human_override is not None:
                return ReleaseAssessment(
                    decision=ReleaseDecision.READY_FOR_SCIELO,
                    reasons=("human-review-override",),
                    human_override_id=human_override.override_id,
                )
            return ReleaseAssessment(
                decision=ReleaseDecision.NEEDS_REVIEW,
                reasons=tuple(sorted(set(review_reasons))),
            )
        return ReleaseAssessment(decision=ReleaseDecision.READY_FOR_SCIELO, reasons=())
