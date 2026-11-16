import re
import unicodedata
from difflib import SequenceMatcher
from enum import StrEnum

from pydantic import Field

from idml_foundation.domain.common import StrictModel


class QualityDecision(StrEnum):
    PASS = "pass"  # noqa: S105 - quality state, not a credential
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"


class SetScore(StrictModel):
    expected: int = Field(ge=0)
    actual: int = Field(ge=0)
    matched: int = Field(ge=0)
    precision: float = Field(ge=0, le=1)
    recall: float = Field(ge=0, le=1)
    f1: float = Field(ge=0, le=1)


class QualityMetrics(StrictModel):
    text_fidelity: float = Field(ge=0, le=1)
    metadata_accuracy: float = Field(ge=0, le=1)
    author_accuracy: float = Field(ge=0, le=1)
    affiliation_accuracy: float = Field(ge=0, le=1)
    reference_accuracy: float = Field(ge=0, le=1)
    figure_accuracy: float = Field(ge=0, le=1)
    table_accuracy: float = Field(ge=0, le=1)
    cross_reference_accuracy: float = Field(ge=0, le=1)


class QualityThresholds(StrictModel):
    text_fidelity_target: float = Field(default=0.995, ge=0, le=1)
    text_fidelity_hard_floor: float = Field(default=0.98, ge=0, le=1)
    metadata_accuracy: float = Field(default=0.98, ge=0, le=1)
    author_accuracy: float = Field(default=1.0, ge=0, le=1)
    affiliation_accuracy: float = Field(default=1.0, ge=0, le=1)
    reference_accuracy: float = Field(default=0.98, ge=0, le=1)
    figure_accuracy: float = Field(default=1.0, ge=0, le=1)
    table_accuracy: float = Field(default=1.0, ge=0, le=1)
    cross_reference_accuracy: float = Field(default=1.0, ge=0, le=1)


class QualityEvaluation(StrictModel):
    decision: QualityDecision
    reasons: tuple[str, ...]
    metrics: QualityMetrics
    thresholds: QualityThresholds


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value)
    normalized = re.sub(r"-\s*\r?\n\s*(?=\w)", "", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def text_fidelity(expected: str, actual: str) -> float:
    left = normalize_text(expected)
    right = normalize_text(actual)
    if not left and not right:
        return 1.0
    return SequenceMatcher(None, left, right, autojunk=False).ratio()


def set_score(expected: set[str], actual: set[str]) -> SetScore:
    matched = len(expected & actual)
    precision = matched / len(actual) if actual else float(not expected)
    recall = matched / len(expected) if expected else float(not actual)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return SetScore(
        expected=len(expected),
        actual=len(actual),
        matched=matched,
        precision=precision,
        recall=recall,
        f1=f1,
    )


def evaluate_quality(
    metrics: QualityMetrics,
    *,
    blocking_errors: tuple[str, ...] = (),
    ambiguity_count: int = 0,
    thresholds: QualityThresholds | None = None,
) -> QualityEvaluation:
    policy = thresholds or QualityThresholds()
    if blocking_errors:
        return QualityEvaluation(
            decision=QualityDecision.FAILED,
            reasons=tuple(f"blocking:{item}" for item in blocking_errors),
            metrics=metrics,
            thresholds=policy,
        )
    if metrics.text_fidelity < policy.text_fidelity_hard_floor:
        return QualityEvaluation(
            decision=QualityDecision.FAILED,
            reasons=("text_fidelity_below_hard_floor",),
            metrics=metrics,
            thresholds=policy,
        )

    comparisons = {
        "text_fidelity": (metrics.text_fidelity, policy.text_fidelity_target),
        "metadata_accuracy": (metrics.metadata_accuracy, policy.metadata_accuracy),
        "author_accuracy": (metrics.author_accuracy, policy.author_accuracy),
        "affiliation_accuracy": (metrics.affiliation_accuracy, policy.affiliation_accuracy),
        "reference_accuracy": (metrics.reference_accuracy, policy.reference_accuracy),
        "figure_accuracy": (metrics.figure_accuracy, policy.figure_accuracy),
        "table_accuracy": (metrics.table_accuracy, policy.table_accuracy),
        "cross_reference_accuracy": (
            metrics.cross_reference_accuracy,
            policy.cross_reference_accuracy,
        ),
    }
    reasons = tuple(name for name, (score, minimum) in comparisons.items() if score < minimum)
    if ambiguity_count:
        reasons += ("unresolved_ambiguity",)
    return QualityEvaluation(
        decision=QualityDecision.NEEDS_REVIEW if reasons else QualityDecision.PASS,
        reasons=reasons,
        metrics=metrics,
        thresholds=policy,
    )
