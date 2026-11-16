import hashlib
import json
from collections.abc import Iterable
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import cast

from pydantic import Field, field_validator

from idml_foundation.domain.common import SHA256_PATTERN, StrictModel, content_digest


class AccessClass(StrEnum):
    RESTRICTED = "restricted"
    INTERNAL = "internal"
    PUBLIC = "public"


class CorpusSplit(StrEnum):
    DEVELOPMENT = "development"
    CONTRAST = "contrast"
    HOMOLOGATION_HOLDOUT = "homologation_holdout"


class CorpusArtifact(StrictModel):
    logical_path: str
    role: str = Field(min_length=1, max_length=80)
    media_type: str
    sha256: str = Field(pattern=SHA256_PATTERN)
    size_bytes: int = Field(ge=0)
    access_class: AccessClass

    @field_validator("logical_path")
    @classmethod
    def path_is_relative_and_portable(cls, value: str) -> str:
        path = PurePosixPath(value)
        if "\\" in value or path.is_absolute() or ".." in path.parts or not path.parts:
            raise ValueError("logical_path must be a safe relative POSIX path")
        return value


class RetentionPolicy(StrictModel):
    retain_until: str | None = None
    review_interval_days: int = Field(ge=1)
    deletion_requires_approval: bool = True


class CorpusPolicy(StrictModel):
    purpose: str
    license_status: str
    confidentiality: AccessClass
    contains_personal_data: bool
    redistribution_allowed: bool
    anonymization: str
    retention: RetentionPolicy


class ExpectedStructure(StrictModel):
    pages: int | None = Field(default=None, ge=0)
    stories: int | None = Field(default=None, ge=0)
    text_frames: int | None = Field(default=None, ge=0)
    body_sections: int | None = Field(default=None, ge=0)
    body_paragraphs: int | None = Field(default=None, ge=0)
    contributors: int | None = Field(default=None, ge=0)
    affiliations: int | None = Field(default=None, ge=0)
    figures: int | None = Field(default=None, ge=0)
    tables: int | None = Field(default=None, ge=0)
    inline_formulas: int | None = Field(default=None, ge=0)
    display_formulas: int | None = Field(default=None, ge=0)
    references: int | None = Field(default=None, ge=0)
    notes: int | None = Field(default=None, ge=0)


class CorpusManifest(StrictModel):
    manifest_version: str
    corpus_id: str
    journal: str
    template: str
    split: CorpusSplit
    source_root_hint: str
    policy: CorpusPolicy
    artifacts: tuple[CorpusArtifact, ...]
    expected: ExpectedStructure

    @field_validator("source_root_hint")
    @classmethod
    def source_root_is_relative_and_portable(cls, value: str) -> str:
        path = PurePosixPath(value)
        if "\\" in value or path.is_absolute() or ".." in path.parts or not path.parts:
            raise ValueError("source_root_hint must be a safe relative POSIX path")
        return value


class ArtifactVerification(StrictModel):
    logical_path: str
    valid: bool
    reason: str | None = None


class CorpusVerification(StrictModel):
    corpus_id: str
    valid: bool
    artifacts: tuple[ArtifactVerification, ...]


class CorpusAuditIssue(StrictModel):
    code: str
    corpus_id: str | None = None
    logical_path: str | None = None


class CorpusCatalogAudit(StrictModel):
    valid: bool
    catalog_sha256: str
    manifests: int
    artifacts: int
    holdouts: int
    issues: tuple[CorpusAuditIssue, ...]


class RepositoryExposureAudit(StrictModel):
    valid: bool
    tracked_files: int
    files_hashed: int
    text_files_scanned: int
    issues: tuple[CorpusAuditIssue, ...]


def load_manifest(path: Path) -> CorpusManifest:
    return CorpusManifest.model_validate_json(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_manifest(manifest: CorpusManifest, root: Path) -> CorpusVerification:
    resolved_root = root.resolve(strict=True)
    results: list[ArtifactVerification] = []
    for descriptor in manifest.artifacts:
        candidate = (resolved_root / Path(*PurePosixPath(descriptor.logical_path).parts)).resolve()
        if not candidate.is_relative_to(resolved_root):
            results.append(
                ArtifactVerification(
                    logical_path=descriptor.logical_path,
                    valid=False,
                    reason="outside_root",
                )
            )
            continue
        if candidate.is_symlink() or not candidate.is_file():
            results.append(
                ArtifactVerification(
                    logical_path=descriptor.logical_path,
                    valid=False,
                    reason="missing_or_symlink",
                )
            )
            continue
        if candidate.stat().st_size != descriptor.size_bytes:
            results.append(
                ArtifactVerification(
                    logical_path=descriptor.logical_path,
                    valid=False,
                    reason="size_mismatch",
                )
            )
            continue
        if _sha256(candidate) != descriptor.sha256:
            results.append(
                ArtifactVerification(
                    logical_path=descriptor.logical_path,
                    valid=False,
                    reason="sha256_mismatch",
                )
            )
            continue
        results.append(ArtifactVerification(logical_path=descriptor.logical_path, valid=True))
    return CorpusVerification(
        corpus_id=manifest.corpus_id,
        valid=all(item.valid for item in results),
        artifacts=tuple(results),
    )


def catalog_digest(manifests: Iterable[CorpusManifest]) -> str:
    ordered = sorted(manifests, key=lambda item: item.corpus_id)
    return content_digest({"manifests": [item.model_dump(mode="json") for item in ordered]})


def audit_catalog(manifests: Iterable[CorpusManifest]) -> CorpusCatalogAudit:
    ordered = sorted(manifests, key=lambda item: item.corpus_id)
    issues: list[CorpusAuditIssue] = []
    corpus_ids: set[str] = set()
    digest_owners: dict[str, tuple[str, CorpusSplit, str]] = {}
    access_rank = {
        AccessClass.PUBLIC: 0,
        AccessClass.INTERNAL: 1,
        AccessClass.RESTRICTED: 2,
    }

    if not ordered:
        issues.append(CorpusAuditIssue(code="empty_catalog"))

    for manifest in ordered:
        if manifest.corpus_id in corpus_ids:
            issues.append(
                CorpusAuditIssue(code="duplicate_corpus_id", corpus_id=manifest.corpus_id)
            )
        corpus_ids.add(manifest.corpus_id)
        logical_paths: set[str] = set()
        if (
            manifest.policy.confidentiality == AccessClass.RESTRICTED
            and manifest.policy.redistribution_allowed
        ):
            issues.append(
                CorpusAuditIssue(
                    code="restricted_redistribution_allowed",
                    corpus_id=manifest.corpus_id,
                )
            )
        if (
            manifest.policy.confidentiality == AccessClass.RESTRICTED
            and not manifest.policy.retention.deletion_requires_approval
        ):
            issues.append(
                CorpusAuditIssue(
                    code="restricted_deletion_without_approval",
                    corpus_id=manifest.corpus_id,
                )
            )
        for artifact in manifest.artifacts:
            if artifact.logical_path in logical_paths:
                issues.append(
                    CorpusAuditIssue(
                        code="duplicate_logical_path",
                        corpus_id=manifest.corpus_id,
                        logical_path=artifact.logical_path,
                    )
                )
            logical_paths.add(artifact.logical_path)
            if access_rank[artifact.access_class] < access_rank[manifest.policy.confidentiality]:
                issues.append(
                    CorpusAuditIssue(
                        code="artifact_access_weaker_than_corpus",
                        corpus_id=manifest.corpus_id,
                        logical_path=artifact.logical_path,
                    )
                )
            owner = digest_owners.get(artifact.sha256)
            if owner is not None:
                owner_corpus, owner_split, _ = owner
                code = (
                    "artifact_reused_across_splits"
                    if owner_split != manifest.split
                    else "artifact_reused_across_corpora"
                )
                issues.append(
                    CorpusAuditIssue(
                        code=code,
                        corpus_id=f"{owner_corpus}|{manifest.corpus_id}",
                        logical_path=artifact.logical_path,
                    )
                )
            else:
                digest_owners[artifact.sha256] = (
                    manifest.corpus_id,
                    manifest.split,
                    artifact.logical_path,
                )

    return CorpusCatalogAudit(
        valid=not issues,
        catalog_sha256=catalog_digest(ordered),
        manifests=len(ordered),
        artifacts=sum(len(item.artifacts) for item in ordered),
        holdouts=sum(item.split == CorpusSplit.HOMOLOGATION_HOLDOUT for item in ordered),
        issues=tuple(issues),
    )


def audit_repository_exposure(
    manifests: Iterable[CorpusManifest],
    repository_root: Path,
    tracked_paths: Iterable[str],
    *,
    forbidden_holdout_roots: tuple[str, ...] = (
        "prompts",
        "tests",
        "benchmarks/agents",
        "logs",
    ),
) -> RepositoryExposureAudit:
    ordered = tuple(manifests)
    resolved_root = repository_root.resolve(strict=True)
    restricted_hashes = {
        artifact.sha256: (manifest.corpus_id, artifact.logical_path)
        for manifest in ordered
        for artifact in manifest.artifacts
        if artifact.access_class == AccessClass.RESTRICTED
    }
    holdout_tokens = {
        token.casefold(): manifest.corpus_id
        for manifest in ordered
        if manifest.split == CorpusSplit.HOMOLOGATION_HOLDOUT
        for token in (
            manifest.corpus_id,
            *(artifact.sha256 for artifact in manifest.artifacts),
            *(PurePosixPath(artifact.logical_path).name for artifact in manifest.artifacts),
        )
    }
    issues: list[CorpusAuditIssue] = []
    normalized_paths = tuple(sorted(set(tracked_paths)))
    files_hashed = 0
    text_files_scanned = 0

    for relative_value in normalized_paths:
        relative_path = PurePosixPath(relative_value)
        if (
            "\\" in relative_value
            or relative_path.is_absolute()
            or ".." in relative_path.parts
            or not relative_path.parts
        ):
            issues.append(CorpusAuditIssue(code="unsafe_tracked_path", logical_path=relative_value))
            continue
        candidate = (resolved_root / Path(*relative_path.parts)).resolve()
        if not candidate.is_relative_to(resolved_root) or candidate.is_symlink():
            issues.append(
                CorpusAuditIssue(code="tracked_path_escape_or_symlink", logical_path=relative_value)
            )
            continue
        if not candidate.is_file():
            continue
        files_hashed += 1
        candidate_digest = _sha256(candidate)
        if candidate_digest in restricted_hashes:
            corpus_id, logical_path = restricted_hashes[candidate_digest]
            issues.append(
                CorpusAuditIssue(
                    code="restricted_artifact_versioned",
                    corpus_id=corpus_id,
                    logical_path=logical_path,
                )
            )
        normalized = relative_path.as_posix()
        if not any(
            normalized == root or normalized.startswith(f"{root}/")
            for root in forbidden_holdout_roots
        ):
            continue
        try:
            content = candidate.read_text(encoding="utf-8").casefold()
        except UnicodeDecodeError:
            continue
        text_files_scanned += 1
        for token, corpus_id in holdout_tokens.items():
            if token in content:
                issues.append(
                    CorpusAuditIssue(
                        code="holdout_token_in_execution_material",
                        corpus_id=corpus_id,
                        logical_path=relative_value,
                    )
                )
                break

    return RepositoryExposureAudit(
        valid=not issues,
        tracked_files=len(normalized_paths),
        files_hashed=files_hashed,
        text_files_scanned=text_files_scanned,
        issues=tuple(issues),
    )


def manifest_json_schema() -> dict[str, object]:
    normalized = json.loads(json.dumps(CorpusManifest.model_json_schema(), sort_keys=True))
    return cast(dict[str, object], normalized)
