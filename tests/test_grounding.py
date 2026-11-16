import pytest

from idml_foundation.ai.grounding import assess_evidence_grounding


def test_grounding_accepts_only_safe_normalization() -> None:
    whitespace = assess_evidence_grounding(
        "Evidence   supported\nvalue",
        "Evidence supported value",
    )
    dehyphenated = assess_evidence_grounding(
        "international",
        "inter-\n national",
    )
    compatibility = assess_evidence_grounding("Article Ⅳ", "Article IV")

    assert whitespace.supported is True
    assert dehyphenated.supported is True
    assert compatibility.supported is True
    assert whitespace.reason == "normalized_exact"


@pytest.mark.parametrize(
    "proposed,evidence",
    [
        ("Supported value plus invention", "Supported value"),
        ("Different value", "Supported value"),
        ("supported value", "Supported value"),
        ("", "Supported value"),
        (["Supported value"], "Supported value"),
    ],
)
def test_grounding_rejects_content_not_exactly_supported(
    proposed: object,
    evidence: str,
) -> None:
    assert assess_evidence_grounding(proposed, evidence).supported is False


def test_grounding_rejects_unknown_policy() -> None:
    with pytest.raises(ValueError, match="unsupported evidence grounding policy"):
        assess_evidence_grounding("value", "value", policy="substring")  # type: ignore[arg-type]
