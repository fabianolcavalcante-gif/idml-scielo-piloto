import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from idml_foundation.domain.corpus import (
    AccessClass,
    CorpusArtifact,
    CorpusManifest,
    CorpusSplit,
    load_manifest,
    verify_manifest,
)
from idml_foundation.domain.metrics import (
    QualityDecision,
    QualityMetrics,
    evaluate_quality,
    normalize_text,
    set_score,
    text_fidelity,
)


def test_repository_corpus_manifests_are_valid_and_holdout_is_separate() -> None:
    root = Path(__file__).parents[1]
    manifests = [load_manifest(path) for path in sorted((root / "corpus/manifests").glob("*.json"))]
    assert len(manifests) == 7
    assert sum(item.split == CorpusSplit.HOMOLOGATION_HOLDOUT for item in manifests) == 1
    assert all(not item.policy.redistribution_allowed for item in manifests)
    esa = next(item for item in manifests if item.corpus_id == "esa-e20240086")
    assert esa.expected.contributors == 3
    assert esa.expected.figures == 5
    assert esa.expected.references == 52
    assert len(esa.artifacts) == 11
    corrective = next(item for item in manifests if item.corpus_id == "esa-e20240135")
    assert corrective.expected.figures == 7
    assert corrective.expected.inline_formulas == 32
    assert corrective.expected.display_formulas == 11
    assert len(corrective.artifacts) == 12


def test_manifest_verification_checks_size_and_digest(tmp_path: Path) -> None:
    content = b"controlled corpus fixture"
    fixture = tmp_path / "sample.idml"
    fixture.write_bytes(content)
    artifact = CorpusArtifact(
        logical_path="sample.idml",
        role="source_idml",
        media_type="application/zip",
        sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
        access_class=AccessClass.RESTRICTED,
    )
    template = json.loads(
        (Path(__file__).parents[1] / "corpus/manifests/esa-e20240086.json").read_text()
    )
    template["corpus_id"] = "fixture"
    template["artifacts"] = [artifact.model_dump(mode="json")]
    manifest = CorpusManifest.model_validate(template)
    assert verify_manifest(manifest, tmp_path).valid is True

    fixture.write_bytes(b"changed")
    result = verify_manifest(manifest, tmp_path)
    assert result.valid is False
    assert result.artifacts[0].reason == "size_mismatch"


def test_manifest_rejects_unsafe_paths() -> None:
    with pytest.raises(ValidationError, match="safe relative"):
        CorpusArtifact(
            logical_path="../private.idml",
            role="source",
            media_type="application/zip",
            sha256="a" * 64,
            size_bytes=1,
            access_class=AccessClass.RESTRICTED,
        )


def perfect_metrics(**overrides: float) -> QualityMetrics:
    values = {
        "text_fidelity": 1.0,
        "metadata_accuracy": 1.0,
        "author_accuracy": 1.0,
        "affiliation_accuracy": 1.0,
        "reference_accuracy": 1.0,
        "figure_accuracy": 1.0,
        "table_accuracy": 1.0,
        "cross_reference_accuracy": 1.0,
    }
    values.update(overrides)
    return QualityMetrics(**values)


def test_quality_metrics_and_decisions_are_deterministic() -> None:
    assert normalize_text("inter-\n nacional") == "internacional"
    assert text_fidelity("same text", "same   text") == 1.0
    score = set_score({"a", "b"}, {"b", "c"})
    assert score.precision == score.recall == score.f1 == 0.5

    assert evaluate_quality(perfect_metrics()).decision == QualityDecision.PASS
    assert (
        evaluate_quality(perfect_metrics(reference_accuracy=0.9)).decision
        == QualityDecision.NEEDS_REVIEW
    )
    assert evaluate_quality(perfect_metrics(text_fidelity=0.5)).decision == QualityDecision.FAILED
    assert (
        evaluate_quality(perfect_metrics(), blocking_errors=("unrepresentable",)).decision
        == QualityDecision.FAILED
    )
