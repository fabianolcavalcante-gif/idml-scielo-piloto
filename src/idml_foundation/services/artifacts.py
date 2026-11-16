import hashlib
import os
import tempfile
from pathlib import Path, PurePath

from sqlalchemy import select
from sqlalchemy.orm import Session

from idml_foundation.ingest.safe_zip import ArchiveInspection, inspect_idml
from idml_foundation.ingest.scanner import ContentScanner
from idml_foundation.models import Artifact
from idml_foundation.services.storage_budget import (
    ArtifactStorageError,
    check_new_file_budget,
    integrity_error,
    lock_storage,
    tenant_directory,
    verify_existing_file,
)
from idml_foundation.settings import Settings

_ASSET_SIGNATURES = (
    (b"%PDF-", "application/pdf"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
)


class UnsafeContentError(ValueError):
    pass


def _store_bytes(
    db: Session,
    *,
    organization_id: str,
    original_name: str,
    data: bytes,
    media_type: str,
    settings: Settings,
    scanner: ContentScanner | None,
    scanner_status: str | None = None,
) -> Artifact:
    if scanner is not None:
        scan = scanner.scan(data)
        if not scan.clean:
            raise UnsafeContentError("content scanner rejected upload")
        resolved_scanner_status = scan.status
    elif scanner_status is not None:
        resolved_scanner_status = scanner_status
    else:
        raise ValueError("scanner status is required for generated artifacts")
    digest = hashlib.sha256(data).hexdigest()
    root = lock_storage(db, settings)
    tenant = tenant_directory(root, organization_id)
    storage_key = f"{organization_id}/{digest[:2]}/{digest}"
    destination = root / storage_key
    if destination.parent.is_symlink() or not destination.resolve().is_relative_to(tenant):
        raise integrity_error()
    existing = db.scalar(
        select(Artifact)
        .where(
            Artifact.organization_id == organization_id,
            Artifact.sha256 == digest,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if existing is not None:
        if existing.storage_key != storage_key or existing.size_bytes != len(data):
            raise integrity_error()
        verify_existing_file(destination, digest, len(data))
        if existing.scanner_status == "malware_detected":
            raise UnsafeContentError("content quarantined")
        if resolved_scanner_status == "clamav_clean" and existing.scanner_status != "generated":
            existing.scanner_status = resolved_scanner_status
            db.flush()
        return existing
    # A rollback may leave an immutable orphan. Reuse only verified content;
    # retained files remain part of the tenant's physical quota.
    if destination.exists() or destination.is_symlink():
        verify_existing_file(destination, digest, len(data))
    else:
        check_new_file_budget(root, tenant, len(data), settings)
        try:
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
            descriptor, temporary_name = tempfile.mkstemp(prefix=".upload-", dir=destination.parent)
            temporary = Path(temporary_name)
            try:
                with os.fdopen(descriptor, "wb") as output:
                    output.write(data)
                    output.flush()
                    os.fsync(output.fileno())
                temporary.chmod(0o640)
                os.replace(temporary, destination)
            finally:
                temporary.unlink(missing_ok=True)
        except OSError as exc:
            raise ArtifactStorageError("artifact_storage_unavailable") from exc
    basename = PurePath(original_name).name
    safe_name = "".join(
        character
        for character in basename
        if character.isprintable() and character not in {'"', "\\", "/"}
    )[:255]
    artifact = Artifact(
        organization_id=organization_id,
        sha256=digest,
        size_bytes=len(data),
        media_type=media_type,
        original_name=safe_name or "artifact",
        storage_key=storage_key,
        scanner_status=resolved_scanner_status,
    )
    db.add(artifact)
    db.flush()
    return artifact


def store_supporting_artifact(
    db: Session,
    *,
    organization_id: str,
    original_name: str,
    data: bytes,
    settings: Settings,
    scanner: ContentScanner,
) -> Artifact:
    media_type = next(
        (candidate for signature, candidate in _ASSET_SIGNATURES if data.startswith(signature)),
        None,
    )
    if media_type is None:
        raise ValueError("unsupported asset format")
    return _store_bytes(
        db,
        organization_id=organization_id,
        original_name=original_name,
        data=data,
        media_type=media_type,
        settings=settings,
        scanner=scanner,
    )


def store_idml_artifact(
    db: Session,
    *,
    organization_id: str,
    original_name: str,
    data: bytes,
    settings: Settings,
    scanner: ContentScanner,
) -> tuple[Artifact, ArchiveInspection]:
    inspection = inspect_idml(data, settings)
    artifact = _store_bytes(
        db,
        organization_id=organization_id,
        original_name=original_name,
        data=data,
        media_type="application/vnd.adobe.indesign-idml-package",
        settings=settings,
        scanner=scanner,
    )
    return artifact, inspection


def store_generated_artifact(
    db: Session,
    *,
    organization_id: str,
    original_name: str,
    data: bytes,
    media_type: str,
    settings: Settings,
) -> Artifact:
    if media_type not in {"application/xml", "application/zip"}:
        raise ValueError("unsupported generated artifact format")
    if not data or len(data) > settings.upload_max_bytes:
        raise ValueError("generated artifact size is invalid")
    return _store_bytes(
        db,
        organization_id=organization_id,
        original_name=original_name,
        data=data,
        media_type=media_type,
        settings=settings,
        scanner=None,
        scanner_status="generated",
    )


def read_artifact_bytes(artifact: Artifact, settings: Settings) -> bytes:
    if artifact.scanner_status == "malware_detected":
        raise UnsafeContentError("content quarantined")
    if (
        artifact.storage_key
        != f"{artifact.organization_id}/{artifact.sha256[:2]}/{artifact.sha256}"
    ):
        raise ValueError("artifact storage key integrity failure")
    root = settings.artifact_root.resolve()
    path = (root / artifact.storage_key).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise FileNotFoundError("artifact content not found")
    if not 0 < artifact.size_bytes <= settings.upload_max_bytes:
        raise ValueError("artifact size exceeds read limit")
    # Check the opened file, then bound the read even if it grows concurrently.
    with path.open("rb") as source:
        if os.fstat(source.fileno()).st_size != artifact.size_bytes:
            raise ValueError("artifact size integrity failure")
        content = source.read(artifact.size_bytes + 1)
    if len(content) != artifact.size_bytes:
        raise ValueError("artifact size integrity failure")
    if hashlib.sha256(content).hexdigest() != artifact.sha256:
        raise ValueError("artifact integrity failure")
    return content
