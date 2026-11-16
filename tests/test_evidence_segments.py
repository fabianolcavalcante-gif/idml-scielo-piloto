import copy

import pytest

from idml_foundation.ai.evidence import (
    EVIDENCE_SEGMENT_MAX_CHARACTERS,
    EVIDENCE_TOTAL_MAX_CHARACTERS,
    evidence_reference,
    reassemble_evidence,
    segment_evidence,
)
from idml_foundation.ai.security import payload_digest


def test_segmented_evidence_is_lossless_bounded_and_content_free_when_referenced() -> None:
    text = "Áβ exact evidence\n" + ("reference content " * 70)
    evidence = segment_evidence(
        evidence_id="gold-reference-001",
        source_kind="canonical",
        locator="approved_xml:references:1",
        text=text,
    )

    assert reassemble_evidence(evidence) == text
    assert evidence["segment_count"] == len(evidence["segments"]) == 3
    assert all(
        0 < len(segment["text"]) <= EVIDENCE_SEGMENT_MAX_CHARACTERS
        for segment in evidence["segments"]
    )
    reference = evidence_reference(evidence)
    assert text not in str(reference)
    assert reference["aggregate_sha256"] == evidence["aggregate_sha256"]
    assert [item["position"] for item in reference["segments"]] == [0, 1, 2]


@pytest.mark.parametrize("mutation", ["text", "hash", "order", "aggregate", "size"])
def test_segmented_evidence_rejects_any_integrity_divergence(mutation: str) -> None:
    evidence = segment_evidence(
        evidence_id="gold-reference-001",
        source_kind="canonical",
        locator="approved_xml:references:1",
        text="e" * 700,
    )
    tampered = copy.deepcopy(evidence)
    if mutation == "text":
        tampered["segments"][0]["text"] = "x" + tampered["segments"][0]["text"][1:]
    elif mutation == "hash":
        tampered["segments"][0]["text_sha256"] = "0" * 64
    elif mutation == "order":
        tampered["segments"].reverse()
    elif mutation == "aggregate":
        tampered["aggregate_sha256"] = "0" * 64
    else:
        tampered["total_characters"] += 1

    with pytest.raises(ValueError):
        reassemble_evidence(tampered)


def test_segmented_evidence_rejects_total_overflow_without_truncating() -> None:
    with pytest.raises(ValueError, match="total character bound"):
        segment_evidence(
            evidence_id="gold-reference-001",
            source_kind="canonical",
            locator="approved_xml:references:1",
            text="x" * (EVIDENCE_TOTAL_MAX_CHARACTERS + 1),
        )


def test_legacy_evidence_remains_supported() -> None:
    excerpt = "Historical evidence"
    evidence = {
        "evidence_id": "legacy-001",
        "source_kind": "canonical",
        "locator": "approved_xml:metadata:1",
        "excerpt": excerpt,
        "excerpt_sha256": payload_digest(excerpt),
    }

    assert reassemble_evidence(evidence) == excerpt
    assert evidence_reference(evidence)["excerpt_sha256"] == payload_digest(excerpt)
