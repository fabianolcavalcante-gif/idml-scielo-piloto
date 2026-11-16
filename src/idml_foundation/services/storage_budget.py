"""Conservative local-filesystem quotas shared by API and worker transactions."""

import hashlib
import os
import shutil
from pathlib import Path
from typing import BinaryIO
from uuid import UUID

from sqlalchemy import event
from sqlalchemy.orm import Session, SessionTransaction

from idml_foundation.ingest.upload_admission import _lock
from idml_foundation.settings import Settings

_LOCKS = "idml_artifact_storage_locks"


class ArtifactStorageError(Exception):
    def __init__(self, code: str, *, status_code: int = 503, retryable: bool = True) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code
        self.retryable = retryable


def integrity_error() -> ArtifactStorageError:
    return ArtifactStorageError("artifact_storage_integrity", status_code=409, retryable=False)


@event.listens_for(Session, "after_transaction_end")
def _release_storage_locks(db: Session, transaction: SessionTransaction) -> None:
    if transaction.parent is None:
        locks = db.info.pop(_LOCKS, {})
        for file in locks.values():
            file.close()


def lock_storage(db: Session, settings: Settings) -> Path:
    """Hold the writer lock through commit/rollback, including nested savepoints."""
    owned: BinaryIO | None = None
    try:
        root = settings.artifact_root.resolve()
        root.mkdir(parents=True, exist_ok=True, mode=0o750)
        if not db.in_transaction():
            db.begin()
        locks = db.info.setdefault(_LOCKS, {})
        if str(root) not in locks:
            owned = (root / ".storage-budget.lock").open("a+b")
            if not _lock(owned):
                raise ArtifactStorageError("artifact_storage_busy")
            locks[str(root)] = owned
            owned = None
        return root
    except OSError as exc:
        raise ArtifactStorageError("artifact_storage_unavailable") from exc
    finally:
        if owned is not None:
            owned.close()


def tenant_directory(root: Path, organization_id: str) -> Path:
    try:
        if str(UUID(organization_id)) != organization_id:
            raise ValueError("noncanonical tenant")
    except ValueError as exc:
        raise integrity_error() from exc
    tenant = root / organization_id
    if tenant.is_symlink() or not tenant.resolve().is_relative_to(root):
        raise integrity_error()
    return tenant


def tenant_usage(tenant: Path, settings: Settings) -> tuple[int, int]:
    """Count physical files, including unregistered/orphan and partial uploads.

    Walk is bounded by the configured file budget plus the 256 hash directories.
    Unknown nested directories/symlinks fail closed rather than hiding usage.
    """
    size = count = entries = 0
    pending = [(tenant, 0)] if tenant.exists() else []
    try:
        while pending:
            directory, depth = pending.pop()
            with os.scandir(directory) as children:
                for child in children:
                    entries += 1
                    if entries > settings.artifact_tenant_max_files + 256:
                        raise ArtifactStorageError("artifact_quota_exceeded", status_code=409)
                    if child.is_symlink():
                        raise integrity_error()
                    if child.is_dir(follow_symlinks=False):
                        if (
                            depth != 0
                            or len(child.name) != 2
                            or any(c not in "0123456789abcdef" for c in child.name)
                        ):
                            raise integrity_error()
                        pending.append((Path(child.path), depth + 1))
                    elif child.is_file(follow_symlinks=False):
                        size += child.stat(follow_symlinks=False).st_size
                        count += 1
                    else:
                        raise integrity_error()
    except OSError as exc:
        raise ArtifactStorageError("artifact_storage_unavailable") from exc
    return size, count


def verify_existing_file(destination: Path, digest: str, size: int) -> None:
    if destination.is_symlink() or not destination.is_file():
        raise integrity_error()
    try:
        with destination.open("rb") as source:
            if os.fstat(source.fileno()).st_size != size:
                raise integrity_error()
            actual = hashlib.sha256()
            remaining = size
            while remaining:
                block = source.read(min(65536, remaining))
                if not block:
                    raise integrity_error()
                actual.update(block)
                remaining -= len(block)
            if source.read(1) or actual.hexdigest() != digest:
                raise integrity_error()
    except OSError as exc:
        raise ArtifactStorageError("artifact_storage_unavailable") from exc


def check_new_file_budget(root: Path, tenant: Path, size: int, settings: Settings) -> None:
    used, count = tenant_usage(tenant, settings)
    if (
        used + size > settings.artifact_tenant_quota_bytes
        or count >= settings.artifact_tenant_max_files
    ):
        raise ArtifactStorageError("artifact_quota_exceeded", status_code=409)
    try:
        # Logical-byte quota is distinct from the actual free-space safeguard.
        block_size = max(4096, os.statvfs(root).f_frsize) if hasattr(os, "statvfs") else 4096
        required = ((size + block_size - 1) // block_size) * block_size
        if shutil.disk_usage(root).free < settings.artifact_disk_reserve_bytes + required:
            raise ArtifactStorageError("artifact_disk_reserve")
    except OSError as exc:
        raise ArtifactStorageError("artifact_storage_unavailable") from exc
