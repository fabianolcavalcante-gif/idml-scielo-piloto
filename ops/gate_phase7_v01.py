"""Execute the content-free V-01 corpus provenance gate."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path, PurePosixPath

from idml_foundation.domain.corpus import (
    audit_catalog,
    audit_repository_exposure,
    load_manifest,
    verify_manifest,
)

DEPLOYED_SOURCE_ROOTS = (
    ".github",
    "benchmarks/agents",
    "benchmarks/qualification",
    "benchmarks/security",
    "config",
    "corpus",
    "deploy",
    "docs",
    "migrations",
    "openclaw",
    "ops",
    "profiles",
    "prompts",
    "schemas",
    "src",
    "tests",
)
DEPLOYED_SOURCE_FILES = (
    ".dockerignore",
    ".env.example",
    ".gitignore",
    "Dockerfile",
    "README.md",
    "alembic.ini",
    "pyproject.toml",
    "requirements-dev.lock",
    "requirements.lock",
)


def repository_files(repository_root: Path) -> tuple[tuple[str, ...], str]:
    git = shutil.which("git")
    if git is not None and (repository_root / ".git").is_dir():
        result = subprocess.run(  # noqa: S603 - absolute executable and fixed arguments
            [
                git,
                "-c",
                "core.fsmonitor=false",
                "-C",
                str(repository_root),
                "ls-files",
                "--cached",
                "--others",
                "--exclude-standard",
                "-z",
            ],
            check=True,
            capture_output=True,
        )
        return (
            tuple(item.decode("utf-8") for item in result.stdout.split(b"\0") if item),
            "git-index-and-untracked",
        )

    paths: set[str] = set()
    for relative_value in DEPLOYED_SOURCE_FILES:
        candidate = repository_root / relative_value
        if candidate.is_file() and not candidate.is_symlink():
            paths.add(relative_value)
    for relative_value in DEPLOYED_SOURCE_ROOTS:
        source_root = repository_root / relative_value
        if not source_root.is_dir() or source_root.is_symlink():
            continue
        for candidate in source_root.rglob("*"):
            if (
                candidate.is_file()
                and not candidate.is_symlink()
                and "__pycache__" not in candidate.parts
                and ".pytest_cache" not in candidate.parts
                and "private" not in candidate.relative_to(repository_root).parts
            ):
                paths.add(candidate.relative_to(repository_root).as_posix())
    return tuple(sorted(paths)), "deployed-source-allowlist"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=Path(__file__).parents[1])
    parser.add_argument("--manifest-dir", type=Path)
    parser.add_argument("--source-base", type=Path)
    parser.add_argument("--metadata-only", action="store_true")
    arguments = parser.parse_args()

    repository_root = arguments.repository_root.resolve(strict=True)
    manifest_dir = (arguments.manifest_dir or repository_root / "corpus/manifests").resolve(
        strict=True
    )
    manifests = tuple(load_manifest(path) for path in sorted(manifest_dir.glob("*.json")))
    catalog = audit_catalog(manifests)
    inventory, inventory_source = repository_files(repository_root)
    exposure = audit_repository_exposure(
        manifests,
        repository_root,
        inventory,
    )

    physical_results: list[dict[str, object]] = []
    physical_valid: bool | None = None
    if not arguments.metadata_only:
        if arguments.source_base is None:
            parser.error("--source-base is required unless --metadata-only is used")
        source_base = arguments.source_base.resolve(strict=True)
        physical_valid = True
        for manifest in manifests:
            source_root = source_base / Path(*PurePosixPath(manifest.source_root_hint).parts)
            verification = verify_manifest(manifest, source_root)
            physical_valid = physical_valid and verification.valid
            physical_results.append(
                {
                    "corpus_id": manifest.corpus_id,
                    "valid": verification.valid,
                    "artifacts": len(verification.artifacts),
                    "verified": sum(item.valid for item in verification.artifacts),
                    "failure_reasons": sorted(
                        {item.reason for item in verification.artifacts if item.reason is not None}
                    ),
                }
            )

    approved = catalog.valid and exposure.valid and physical_valid is not False
    report = {
        "version": "phase7-v01-gate-1.0",
        "family": "V-01",
        "approved": approved,
        "catalog": catalog.model_dump(mode="json"),
        "repository_exposure": exposure.model_dump(mode="json"),
        "repository_inventory_source": inventory_source,
        "physical_verification": {
            "status": "not-run"
            if physical_valid is None
            else "passed"
            if physical_valid
            else "failed",
            "corpora": physical_results,
            "artifacts": sum(int(item["artifacts"]) for item in physical_results),
            "verified": sum(int(item["verified"]) for item in physical_results),
        },
        "restricted_content_emitted": False,
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if approved else 2


if __name__ == "__main__":
    raise SystemExit(main())
