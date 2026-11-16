import hashlib
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, status
from fastapi.responses import JSONResponse
from sqlalchemy import select

from idml_foundation.dependencies import (
    Configuration,
    CorrelationId,
    Database,
    Scanner,
    require_permission,
)
from idml_foundation.ingest.http_upload import UPLOAD_OPENAPI, bounded_upload
from idml_foundation.ingest.scanner import ScannerUnavailableError
from idml_foundation.ingest.upload_admission import upload_admission
from idml_foundation.models import Artifact
from idml_foundation.rbac import Permission, TenantContext
from idml_foundation.schemas import ArtifactRead
from idml_foundation.services.artifacts import (
    UnsafeContentError,
    read_artifact_bytes,
    store_idml_artifact,
    store_supporting_artifact,
)
from idml_foundation.services.audit import record_audit

router = APIRouter(prefix="/v1/artifacts", tags=["artifacts"])


def rejected_upload(
    db: Database, context: TenantContext, correlation_id: str, data: bytes
) -> Response:
    digest = hashlib.sha256(data).hexdigest()
    existing = db.scalar(
        select(Artifact)
        .where(Artifact.organization_id == context.organization_id, Artifact.sha256 == digest)
        .with_for_update()
    )
    if existing is not None:
        existing.scanner_status = "malware_detected"
    record_audit(
        db,
        action="artifact.scan",
        resource_type="artifact",
        resource_id=existing.id if existing else None,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        correlation_id=correlation_id,
        outcome="malware_detected",
        details={"sha256": digest},
    )
    return JSONResponse({"detail": "Arquivo recusado pelo antivírus."}, status_code=422)


@router.post(
    "/idml",
    response_model=ArtifactRead,
    status_code=status.HTTP_201_CREATED,
    openapi_extra=UPLOAD_OPENAPI,
)
def upload_idml(
    db: Database,
    settings: Configuration,
    scanner: Scanner,
    correlation_id: CorrelationId,
    context: Annotated[TenantContext, require_permission(Permission.ARTIFACT_UPLOAD)],
    upload: Annotated[UploadFile, Depends(bounded_upload)],
) -> object:
    data = upload.file.read(settings.upload_max_bytes + 1)
    if len(data) > settings.upload_max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="too large"
        )
    try:
        artifact, _inspection = store_idml_artifact(
            db,
            organization_id=context.organization_id,
            original_name=upload.filename or "upload.idml",
            data=data,
            settings=settings,
            scanner=scanner,
        )
    except UnsafeContentError:
        return rejected_upload(db, context, correlation_id, data)
    record_audit(
        db,
        action="artifact.upload",
        resource_type="artifact",
        resource_id=artifact.id,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        correlation_id=correlation_id,
        outcome="success",
        details={
            "sha256": artifact.sha256,
            "media_type": artifact.media_type,
            "scanner_status": artifact.scanner_status,
        },
    )
    return artifact


@router.post(
    "/assets",
    response_model=ArtifactRead,
    status_code=status.HTTP_201_CREATED,
    openapi_extra=UPLOAD_OPENAPI,
)
def upload_asset(
    db: Database,
    settings: Configuration,
    scanner: Scanner,
    correlation_id: CorrelationId,
    context: Annotated[TenantContext, require_permission(Permission.ARTIFACT_UPLOAD)],
    upload: Annotated[UploadFile, Depends(bounded_upload)],
) -> Artifact | Response:
    data = upload.file.read(settings.upload_max_bytes + 1)
    if len(data) > settings.upload_max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="too large"
        )
    try:
        artifact = store_supporting_artifact(
            db,
            organization_id=context.organization_id,
            original_name=upload.filename or "asset",
            data=data,
            settings=settings,
            scanner=scanner,
        )
    except UnsafeContentError:
        return rejected_upload(db, context, correlation_id, data)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    record_audit(
        db,
        action="artifact.upload",
        resource_type="artifact",
        resource_id=artifact.id,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        correlation_id=correlation_id,
        outcome="success",
        details={
            "sha256": artifact.sha256,
            "media_type": artifact.media_type,
            "scanner_status": artifact.scanner_status,
        },
    )
    return artifact


@router.post("/{artifact_id}/rescan", response_model=ArtifactRead)
def rescan_artifact(
    artifact_id: str,
    db: Database,
    settings: Configuration,
    scanner: Scanner,
    correlation_id: CorrelationId,
    context: Annotated[TenantContext, require_permission(Permission.ARTIFACT_UPLOAD)],
) -> Artifact | Response:
    with upload_admission(settings):
        artifact = db.scalar(
            select(Artifact)
            .where(Artifact.id == artifact_id, Artifact.organization_id == context.organization_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if artifact is None:
            raise HTTPException(404, "arquivo não encontrado")
        if artifact.scanner_status in {"generated", "malware_detected"}:
            raise HTTPException(409, "arquivo indisponível para nova varredura")
        previous = artifact.scanner_status
        code = 200
        try:
            data = read_artifact_bytes(artifact, settings)
            scan = scanner.scan(data)
            if not scan.clean:
                artifact.scanner_status, code = "malware_detected", 422
            elif scan.status != "clamav_clean":
                raise ScannerUnavailableError("scanner unavailable")
            else:
                artifact.scanner_status = "clamav_clean"
        except ScannerUnavailableError:
            artifact.scanner_status, code = "scan_unavailable", 503
        except (ValueError, OSError):
            artifact.scanner_status, code = "integrity_failure", 409
        record_audit(
            db,
            action="artifact.rescan",
            resource_type="artifact",
            resource_id=artifact.id,
            organization_id=context.organization_id,
            actor_user_id=context.user.id,
            correlation_id=correlation_id,
            outcome=artifact.scanner_status,
            details={"previous": previous, "sha256": artifact.sha256},
        )
        if code != 200:
            return JSONResponse(
                {"detail": "Não foi possível confirmar este arquivo como limpo."}, status_code=code
            )
        return artifact


@router.get("", response_model=list[ArtifactRead])
def list_artifacts(
    db: Database,
    context: Annotated[TenantContext, require_permission(Permission.RESOURCE_READ)],
) -> list[Artifact]:
    return list(
        db.scalars(
            select(Artifact)
            .where(Artifact.organization_id == context.organization_id)
            .order_by(Artifact.created_at.desc())
            .limit(200)
        )
    )


@router.get("/{artifact_id}/download")
def download_artifact(
    artifact_id: str,
    db: Database,
    settings: Configuration,
    correlation_id: CorrelationId,
    context: Annotated[TenantContext, require_permission(Permission.RESOURCE_READ)],
) -> Response:
    artifact = db.scalar(
        select(Artifact).where(
            Artifact.id == artifact_id,
            Artifact.organization_id == context.organization_id,
        )
    )
    if artifact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="artifact not found")
    try:
        content = read_artifact_bytes(artifact, settings)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="artifact not found"
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="artifact integrity failure",
        ) from exc
    record_audit(
        db,
        action="artifact.download",
        resource_type="artifact",
        resource_id=artifact.id,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        correlation_id=correlation_id,
        outcome="success",
        details={"sha256": artifact.sha256},
    )
    return Response(
        content=content,
        media_type=artifact.media_type,
        headers={"Content-Disposition": f'attachment; filename="{artifact.original_name}"'},
    )
