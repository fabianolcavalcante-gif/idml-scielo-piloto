import copy
import hashlib
from pathlib import Path

from idml_foundation.domain.corpus import (
    AccessClass,
    CorpusManifest,
    CorpusSplit,
    audit_catalog,
    audit_repository_exposure,
    load_manifest,
)


def repository_manifests() -> tuple[CorpusManifest, ...]:
    root = Path(__file__).parents[1]
    return tuple(load_manifest(path) for path in sorted((root / "corpus/manifests").glob("*.json")))


def test_repository_catalog_is_unique_classified_and_reproducible() -> None:
    manifests = repository_manifests()
    first = audit_catalog(manifests)
    second = audit_catalog(reversed(manifests))
    assert first.valid is True
    assert first.manifests == 7
    assert first.artifacts == 33
    assert first.holdouts == 1
    assert first.catalog_sha256 == second.catalog_sha256


def test_catalog_rejects_duplicate_digest_across_splits() -> None:
    manifests = repository_manifests()
    source = manifests[0]
    changed = copy.deepcopy(manifests[1].model_dump(mode="json"))
    changed["artifacts"][0]["sha256"] = source.artifacts[0].sha256
    changed["split"] = CorpusSplit.HOMOLOGATION_HOLDOUT
    result = audit_catalog((source, CorpusManifest.model_validate(changed)))
    assert result.valid is False
    assert {issue.code for issue in result.issues} == {"artifact_reused_across_splits"}


def test_catalog_rejects_weaker_artifact_access() -> None:
    manifest_data = repository_manifests()[0].model_dump(mode="json")
    manifest_data["artifacts"][0]["access_class"] = AccessClass.PUBLIC
    result = audit_catalog((CorpusManifest.model_validate(manifest_data),))
    assert result.valid is False
    assert result.issues[0].code == "artifact_access_weaker_than_corpus"


def test_repository_audit_detects_restricted_bytes_and_holdout_token(tmp_path: Path) -> None:
    manifests = repository_manifests()
    holdout = next(item for item in manifests if item.split == CorpusSplit.HOMOLOGATION_HOLDOUT)
    artifact_path = tmp_path / "tracked.bin"
    artifact_path.write_bytes(b"restricted fixture")
    manifest_data = holdout.model_dump(mode="json")
    manifest_data["artifacts"][0]["sha256"] = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    synthetic = CorpusManifest.model_validate(manifest_data)
    prompt_path = tmp_path / "prompts" / "leak.txt"
    prompt_path.parent.mkdir()
    prompt_path.write_text(holdout.corpus_id, encoding="utf-8")

    result = audit_repository_exposure(
        (synthetic,),
        tmp_path,
        ("tracked.bin", "prompts/leak.txt"),
    )

    assert result.valid is False
    assert {issue.code for issue in result.issues} == {
        "restricted_artifact_versioned",
        "holdout_token_in_execution_material",
    }


def test_repository_audit_accepts_metadata_outside_execution_material(tmp_path: Path) -> None:
    manifests = repository_manifests()
    holdout = next(item for item in manifests if item.split == CorpusSplit.HOMOLOGATION_HOLDOUT)
    metadata_path = tmp_path / "docs" / "catalog.md"
    metadata_path.parent.mkdir()
    metadata_path.write_text(holdout.corpus_id, encoding="utf-8")
    result = audit_repository_exposure(manifests, tmp_path, ("docs/catalog.md",))
    assert result.valid is True


def test_repository_audit_scans_nested_benchmark_root(tmp_path: Path) -> None:
    manifests = repository_manifests()
    holdout = next(item for item in manifests if item.split == CorpusSplit.HOMOLOGATION_HOLDOUT)
    benchmark_path = tmp_path / "benchmarks" / "agents" / "case.json"
    benchmark_path.parent.mkdir(parents=True)
    benchmark_path.write_text(holdout.artifacts[0].sha256, encoding="utf-8")
    result = audit_repository_exposure(
        manifests,
        tmp_path,
        ("benchmarks/agents/case.json",),
    )
    assert result.valid is False
    assert result.issues[0].code == "holdout_token_in_execution_material"


def test_manifest_rejects_unsafe_source_root() -> None:
    manifest_data = repository_manifests()[0].model_dump(mode="json")
    manifest_data["source_root_hint"] = "../private"
    try:
        CorpusManifest.model_validate(manifest_data)
    except ValueError as exc:
        assert "source_root_hint" in str(exc)
    else:
        raise AssertionError("unsafe source root was accepted")
