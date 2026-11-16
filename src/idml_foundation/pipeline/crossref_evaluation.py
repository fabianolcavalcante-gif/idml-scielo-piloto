from __future__ import annotations

from collections import Counter
from typing import Literal, cast

from lxml import etree
from pydantic import Field

from idml_foundation.domain.common import StrictModel


class TargetDelta(StrictModel):
    reference_ordinal: int = Field(ge=1)
    occurrences: int = Field(ge=1)


class CrossReferenceEvaluation(StrictModel):
    expected: int = Field(ge=0)
    actual: int = Field(ge=0)
    matched_targets: int = Field(ge=0)
    precision: float = Field(ge=0, le=1)
    recall: float = Field(ge=0, le=1)
    f1: float = Field(ge=0, le=1)
    expected_unique_targets: int = Field(ge=0)
    actual_unique_targets: int = Field(ge=0)
    expected_target_deficits: tuple[TargetDelta, ...] = ()
    actual_target_surpluses: tuple[TargetDelta, ...] = ()
    decision: Literal["pass", "needs_review", "source_qualified"]


def _target_sequence(root: etree._Element) -> tuple[int, ...]:
    references = cast(list[etree._Element], root.xpath("//back//ref[@id]"))
    reference_order = {
        str(reference.get("id")): ordinal for ordinal, reference in enumerate(references, start=1)
    }
    sequence: list[int] = []
    xrefs = cast(list[etree._Element], root.xpath("//body//xref[@ref-type='bibr']"))
    for xref in xrefs:
        targets = str(xref.get("rid", "")).split()
        if len(targets) != 1 or targets[0] not in reference_order:
            raise ValueError("bibliographic xref must have exactly one known reference target")
        sequence.append(reference_order[targets[0]])
    return tuple(sequence)


def _deltas(counter: Counter[int]) -> tuple[TargetDelta, ...]:
    return tuple(
        TargetDelta(reference_ordinal=ordinal, occurrences=count)
        for ordinal, count in sorted(counter.items())
    )


def evaluate_cross_references(
    expected_root: etree._Element,
    actual_root: etree._Element,
) -> CrossReferenceEvaluation:
    expected = _target_sequence(expected_root)
    actual = _target_sequence(actual_root)
    expected_counts = Counter(expected)
    actual_counts = Counter(actual)
    matched = sum((expected_counts & actual_counts).values())
    precision = matched / len(actual) if actual else float(not expected)
    recall = matched / len(expected) if expected else float(not actual)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return CrossReferenceEvaluation(
        expected=len(expected),
        actual=len(actual),
        matched_targets=matched,
        precision=precision,
        recall=recall,
        f1=f1,
        expected_unique_targets=len(expected_counts),
        actual_unique_targets=len(actual_counts),
        expected_target_deficits=_deltas(expected_counts - actual_counts),
        actual_target_surpluses=_deltas(actual_counts - expected_counts),
        decision="pass" if precision == recall == 1.0 else "needs_review",
    )
