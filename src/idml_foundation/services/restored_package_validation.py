"""Fresh private validation of a restored head. Internal service; caller commits."""

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from idml_foundation.database import ensure_write_transaction
from idml_foundation.domain.canonical import CanonicalArticle
from idml_foundation.domain.common import content_digest
from idml_foundation.models import Artifact, CanonicalHeadEvent, DomainSnapshot
from idml_foundation.pipeline.jats_builder import JatsBuilder
from idml_foundation.pipeline.profile import JournalProfile
from idml_foundation.pipeline.validation import OfflineJatsValidator
from idml_foundation.release.package_builder import AssetPayload
from idml_foundation.restoration_models import RestoredPackageValidation
from idml_foundation.services.artifacts import read_artifact_bytes, store_generated_artifact
from idml_foundation.services.autocorrection_executor import _human_state
from idml_foundation.services.autocorrection_package import _package_assets
from idml_foundation.services.autocorrection_promotion import _no_human_work
from idml_foundation.services.canonical_heads import (
    _event,
    _verified,
    current_canonical_snapshot,
    lock_resource,
    restore_working_head,
)
from idml_foundation.services.package_validation import Executor
from idml_foundation.services.restored_package_builder import build_restored_package
from idml_foundation.services.xpm_execution import XpmExecutor
from idml_foundation.settings import Settings


def _input(
    db: Session,
    organization_id: str,
    digest: str,
    media_type: str,
    settings: Settings,
    artifact_id: str | None = None,
) -> tuple[Artifact, bytes]:
    query = select(Artifact).where(
        Artifact.organization_id == organization_id,
        Artifact.sha256 == digest,
        Artifact.media_type == media_type,
    )
    if artifact_id is not None:
        query = query.where(Artifact.id == artifact_id)
    artifact = db.scalar(query.execution_options(populate_existing=True))
    if (
        artifact is None
        or artifact.scanner_status != "clamav_clean"
        or artifact.storage_key != f"{organization_id}/{digest[:2]}/{digest}"
    ):
        raise ValueError("restored_input_unavailable")
    try:
        return artifact, read_artifact_bytes(artifact, settings)
    except (OSError, ValueError):
        raise ValueError("restored_input_integrity_failure") from None


def _inputs(
    db: Session,
    *,
    organization_id: str,
    resource_id: str,
    restore_event_id: str,
    expected_resource_version: int,
    pdf_artifact_id: str,
    pdf_sha256: str,
    profile: JournalProfile,
    settings: Settings,
) -> tuple[CanonicalArticle, bytes, tuple[AssetPayload, ...], dict[str, Any]]:
    resource = lock_resource(db, organization_id, resource_id)
    event = _event(db, organization_id, resource_id)
    snapshot = current_canonical_snapshot(
        db, organization_id=organization_id, resource_id=resource_id
    )
    if (
        event is None
        or event.id != restore_event_id
        or event.receipt["action"] != "restore"
        or resource.version != expected_resource_version
        or event.receipt["resource_version"] != expected_resource_version
        or snapshot is None
        or content_digest(snapshot.payload) != snapshot.content_sha256
        or snapshot.id != event.snapshot_id
    ):
        raise ValueError("restored_head_changed_or_invalid")
    _no_human_work(db, organization_id, resource_id)
    _, human_sha = _human_state(db, organization_id, resource_id)
    article = CanonicalArticle.model_validate(snapshot.payload)
    if article.journal_profile_id != profile.profile_id:
        raise ValueError("restored_profile_mismatch")
    source = db.scalar(
        select(Artifact)
        .where(
            Artifact.id == snapshot.source_artifact_id,
            Artifact.organization_id == organization_id,
        )
        .execution_options(populate_existing=True)
    )
    if source is None:
        raise ValueError("restored_source_unavailable")
    _, idml = _input(
        db,
        organization_id,
        source.sha256,
        "application/vnd.adobe.indesign-idml-package",
        settings,
        source.id,
    )
    pdf_record, pdf = _input(
        db, organization_id, pdf_sha256, "application/pdf", settings, pdf_artifact_id
    )
    size = len(idml) + len(pdf)
    if size > settings.upload_max_bytes:
        raise ValueError("restored_package_too_large")
    assets = []
    bindings = []
    xml = JatsBuilder(sps_version=profile.sps_version).build(article)
    for asset in _package_assets(article, xml):
        if (
            asset.state != "present"
            or not asset.sha256
            or asset.media_type not in {"image/jpeg", "image/png", "image/tiff"}
            or PurePosixPath(asset.logical_name).suffix.casefold()
            not in {".jpg", ".jpeg", ".png", ".tif", ".tiff"}
            or any(c in asset.logical_name for c in ("/", "\\", ":"))
        ):
            raise ValueError("restored_asset_unavailable")
        record, raw = _input(db, organization_id, asset.sha256, asset.media_type, settings)
        size += len(raw)
        if size > settings.upload_max_bytes:
            raise ValueError("restored_package_too_large")
        assets.append(
            AssetPayload(source_name=asset.logical_name, data=raw, media_type=asset.media_type)
        )
        bindings.append(dict(asset_id=asset.id, artifact_id=record.id, sha256=record.sha256))
    binding = dict(
        snapshot_id=snapshot.id,
        snapshot_sha256=snapshot.content_sha256,
        restore_event_id=event.id,
        restore_receipt_sha256=event.receipt_sha256,
        resource_version=resource.version,
        source_artifact_id=source.id,
        source_idml_sha256=source.sha256,
        pdf_artifact_id=pdf_record.id,
        pdf_sha256=pdf_sha256,
        assets=bindings,
        profile_sha256=content_digest(profile),
        human_state_sha256=human_sha,
    )
    return article, pdf, tuple(assets), binding


def read_restored_validation(
    db: Session,
    *,
    organization_id: str,
    record_id: str,
    settings: Settings,
) -> RestoredPackageValidation:
    """Read checked historical evidence; never asserts that it is still current."""
    record = db.scalar(
        select(RestoredPackageValidation)
        .where(
            RestoredPackageValidation.id == record_id,
            RestoredPackageValidation.organization_id == organization_id,
        )
        .execution_options(populate_existing=True)
    )
    if record is None:
        raise LookupError("restored_validation_not_found")
    receipt = record.receipt
    event = db.get(CanonicalHeadEvent, record.restore_event_id, populate_existing=True)
    snapshot = db.get(DomainSnapshot, record.snapshot_id, populate_existing=True)
    try:
        valid = (
            content_digest(receipt) == record.receipt_sha256
            and receipt["version"] == "restored-package-validation-1.0"
            and receipt["request_id"] == record.request_id
            and receipt["request_sha256"] == record.request_sha256
            and receipt["scope"]["organization_id"] == organization_id
            and receipt["scope"]["resource_id"] == record.resource_id
            and receipt["binding"]["restore_event_id"] == record.restore_event_id
            and receipt["binding"]["snapshot_id"] == record.snapshot_id
            and content_digest(record.reports) == receipt["reports_sha256"]
            and event is not None
            and _verified(event).receipt["action"] == "restore"
            and event.organization_id == organization_id
            and event.resource_id == record.resource_id
            and event.snapshot_id == record.snapshot_id
            and event.receipt_sha256 == receipt["binding"]["restore_receipt_sha256"]
            and snapshot is not None
            and snapshot.organization_id == organization_id
            and snapshot.resource_id == record.resource_id
            and content_digest(snapshot.payload) == snapshot.content_sha256
            and snapshot.content_sha256 == receipt["binding"]["snapshot_sha256"]
            and receipt["historical_evidence_only"] is True
            and receipt["approval_inherited"] is False
            and receipt["release_approved"] is False
            and receipt["active_snapshot_changed"] is False
        )
    except (KeyError, TypeError, ValueError):
        valid = False
    if not valid:
        raise ValueError("restored_validation_integrity_failure")
    for kind, identity, media_type in (
        ("xml", record.xml_artifact_id, "application/xml"),
        ("package", record.package_artifact_id, "application/zip"),
    ):
        artifact = db.get(Artifact, identity, populate_existing=True)
        digest = receipt["scope"][f"{kind}_sha256"]
        if (
            artifact is None
            or artifact.organization_id != organization_id
            or artifact.sha256 != digest
            or artifact.media_type != media_type
            or artifact.storage_key != f"{organization_id}/{digest[:2]}/{digest}"
            or artifact.scanner_status not in {"generated", "clamav_clean"}
            or receipt[f"{kind}_artifact_id"] != identity
        ):
            raise ValueError("restored_validation_artifact_invalid")
        try:
            read_artifact_bytes(artifact, settings)
        except (OSError, ValueError):
            raise ValueError("restored_validation_artifact_invalid") from None
    return record


def revalidate_restored_package(
    db: Session,
    *,
    organization_id: str,
    resource_id: str,
    restore_event_id: str,
    expected_resource_version: int,
    request_id: UUID,
    pdf_artifact_id: str,
    pdf_sha256: str,
    profile: JournalProfile,
    settings: Settings,
    validator: OfflineJatsValidator,
    executor: Executor | None = None,
    xpm_executor: XpmExecutor | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> RestoredPackageValidation:
    request_id = UUID(str(request_id))
    inputs: dict[str, Any] = dict(
        organization_id=organization_id,
        resource_id=resource_id,
        restore_event_id=restore_event_id,
        expected_resource_version=expected_resource_version,
        pdf_artifact_id=pdf_artifact_id,
        pdf_sha256=pdf_sha256,
        profile=profile,
        settings=settings,
    )
    request_sha = content_digest(
        dict(
            action="revalidate-restored-package",
            resource_id=resource_id,
            restore_event_id=restore_event_id,
            expected_resource_version=expected_resource_version,
            pdf_artifact_id=pdf_artifact_id,
            pdf_sha256=pdf_sha256,
            profile_sha256=content_digest(profile),
        )
    )

    def previous() -> RestoredPackageValidation | None:
        row = db.scalar(
            select(RestoredPackageValidation).where(
                RestoredPackageValidation.organization_id == organization_id,
                RestoredPackageValidation.request_id == str(request_id),
            )
        )
        if row is None:
            return None
        if row.request_sha256 != request_sha or row.resource_id != resource_id:
            raise ValueError("restored_validation_request_conflict")
        return read_restored_validation(
            db, organization_id=organization_id, record_id=row.id, settings=settings
        )

    ensure_write_transaction(db)
    try:
        with db.begin_nested():
            lock_resource(db, organization_id, resource_id)
            existing = previous()
            if existing is not None:
                return existing
            started = clock()
            if started.utcoffset() is None:
                raise ValueError("clock_timezone_required")
            article, pdf, assets, binding = _inputs(db, **inputs)
            result = build_restored_package(
                article=article,
                organization_id=organization_id,
                resource_id=resource_id,
                source_sha256=binding["source_idml_sha256"],
                pdf=pdf,
                assets=assets,
                profile=profile,
                settings=settings,
                validator=validator,
                executor=executor,
                xpm_executor=xpm_executor,
            )
            ended = clock()
            if ended.utcoffset() is None or ended < started:
                raise ValueError("restored_validation_clock_invalid")
            *_, after = _inputs(db, **inputs)
            if after != binding:
                raise ValueError("restored_validation_inputs_changed")
            xml = store_generated_artifact(
                db,
                organization_id=organization_id,
                settings=settings,
                original_name=f"restored-{restore_event_id}.xml",
                data=result.xml,
                media_type="application/xml",
            )
            package = store_generated_artifact(
                db,
                organization_id=organization_id,
                settings=settings,
                original_name=f"restored-{restore_event_id}.zip",
                data=result.package.archive,
                media_type="application/zip",
            )
            receipt = dict(
                version="restored-package-validation-1.0",
                request_id=str(request_id),
                request_sha256=request_sha,
                scope=result.scope,
                binding=binding,
                reports_sha256=content_digest(result.reports),
                xml_artifact_id=xml.id,
                package_artifact_id=package.id,
                state="revalidated-working-draft" if result.decision["eligible"] else "blocked",
                draft_admission=result.decision,
                started_at=started.isoformat(),
                checked_at=ended.isoformat(),
                historical_evidence_only=True,
                approval_inherited=False,
                release_approved=False,
                active_snapshot_changed=False,
            )
            record = RestoredPackageValidation(
                organization_id=organization_id,
                resource_id=resource_id,
                restore_event_id=restore_event_id,
                snapshot_id=binding["snapshot_id"],
                request_id=str(request_id),
                request_sha256=request_sha,
                xml_artifact_id=xml.id,
                package_artifact_id=package.id,
                receipt=receipt,
                receipt_sha256=content_digest(receipt),
                reports=result.reports,
            )
            db.add(record)
            db.flush()
            return read_restored_validation(
                db, organization_id=organization_id, record_id=record.id, settings=settings
            )
    except IntegrityError:
        existing = previous()
        if existing is None:
            raise
        return existing


def restore_and_revalidate_package(
    db: Session,
    *,
    organization_id: str,
    resource_id: str,
    target_snapshot_id: str,
    expected_snapshot_id: str,
    expected_resource_version: int,
    request_id: UUID,
    pdf_artifact_id: str,
    pdf_sha256: str,
    profile: JournalProfile,
    settings: Settings,
    validator: OfflineJatsValidator,
    executor: Executor | None = None,
    xpm_executor: XpmExecutor | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> RestoredPackageValidation:
    """Atomic draft restore + fresh evidence; invalid XML stays blocked, never released."""
    ensure_write_transaction(db)
    with db.begin_nested():
        event = restore_working_head(
            db,
            organization_id=organization_id,
            resource_id=resource_id,
            target_snapshot_id=target_snapshot_id,
            expected_snapshot_id=expected_snapshot_id,
            expected_resource_version=expected_resource_version,
            request_id=request_id,
        )
        return revalidate_restored_package(
            db,
            organization_id=organization_id,
            resource_id=resource_id,
            restore_event_id=event.id,
            expected_resource_version=event.receipt["resource_version"],
            request_id=request_id,
            pdf_artifact_id=pdf_artifact_id,
            pdf_sha256=pdf_sha256,
            profile=profile,
            settings=settings,
            validator=validator,
            executor=executor,
            xpm_executor=xpm_executor,
            clock=clock,
        )
