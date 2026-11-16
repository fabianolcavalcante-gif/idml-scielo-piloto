import hashlib
import logging
import signal
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from redis import Redis
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from idml_foundation.ai.autocorrection_contracts import PROFILE_SHA256
from idml_foundation.database import SessionLocal, session_scope
from idml_foundation.domain.canonical import CanonicalArticle
from idml_foundation.domain.common import content_digest
from idml_foundation.logging_config import configure_logging
from idml_foundation.models import Artifact, DomainSnapshot, Job, Resource, utcnow
from idml_foundation.pipeline.autocorrection_evidence import qualify_pipeline_result
from idml_foundation.pipeline.jats_builder import JatsBuilder
from idml_foundation.pipeline.profile import load_profile
from idml_foundation.pipeline.validation import OfflineJatsValidator
from idml_foundation.release.package_builder import AssetPayload, PackageBuilder
from idml_foundation.services.artifacts import read_artifact_bytes, store_generated_artifact
from idml_foundation.services.audit import record_audit
from idml_foundation.services.autocorrection_preflight import run_edit_preflight
from idml_foundation.services.canonical_heads import lock_resource
from idml_foundation.services.enrichment import select_enrichment
from idml_foundation.services.jobs import record_effect_once, schedule_retry, transition_job
from idml_foundation.services.package_validation import assess_package
from idml_foundation.services.scoped_validator_transport import ScopedValidatorExecutor
from idml_foundation.services.snapshots import load_snapshot, store_snapshot
from idml_foundation.services.storage_budget import ArtifactStorageError
from idml_foundation.services.validator_transport import LocalValidatorExecutor
from idml_foundation.services.web_edit_cycle import evaluate_revision
from idml_foundation.services.web_operator_edit import authorize_revision
from idml_foundation.services.web_restore import restore_from_web
from idml_foundation.services.xpm_socket import XpmSocketExecutor
from idml_foundation.settings import Settings, get_settings

logger = logging.getLogger(__name__)


@dataclass
class Shutdown:
    requested: bool = False


class PermanentJobError(ValueError):
    pass


class UnsupportedJobError(PermanentJobError):
    pass


def _payload_id(payload: dict[str, Any], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value:
        raise PermanentJobError(f"invalid {name}")
    return value


def _tenant_resource(db: Session, job: Job) -> Resource:
    resource = db.scalar(
        select(Resource).where(
            Resource.id == _payload_id(job.payload, "resource_id"),
            Resource.organization_id == job.organization_id,
        )
    )
    if resource is None:
        raise PermanentJobError("resource not found in organization")
    return resource


def _tenant_artifact(db: Session, job: Job, name: str) -> Artifact:
    artifact = db.scalar(
        select(Artifact).where(
            Artifact.id == _payload_id(job.payload, name),
            Artifact.organization_id == job.organization_id,
        )
    )
    if artifact is None:
        raise PermanentJobError(f"{name} not found in organization")
    return artifact


def _process_idml_job(db: Session, job: Job, settings: Settings) -> dict[str, Any]:
    resource = _tenant_resource(db, job)
    source = _tenant_artifact(db, job, "idml_artifact_id")
    if source.media_type != "application/vnd.adobe.indesign-idml-package":
        raise PermanentJobError("idml_artifact_id is not an IDML artifact")
    data = read_artifact_bytes(source, settings)
    profile = load_profile(settings.journal_profile_path)
    enrichment = select_enrichment(
        settings,
        organization_id=job.organization_id,
        resource_id=resource.id,
        source_sha256=source.sha256,
        profile_id=profile.profile_id,
    )
    result = enrichment.pipeline(settings).run(data, logical_name=source.original_name)
    canonical = result.canonical
    evidence: dict[str, Any] = {"status": "profile_not_qualified"}
    if content_digest(profile) == PROFILE_SHA256:
        fields = qualify_pipeline_result(result, idml=data, profile=profile, settings=settings)
        # A replay after an upgrade must still return its original immutable snapshot.
        lock_resource(db, job.organization_id, resource.id)
        legacy = db.scalar(
            select(DomainSnapshot.id).where(
                DomainSnapshot.organization_id == job.organization_id,
                DomainSnapshot.resource_id == resource.id,
                DomainSnapshot.source_artifact_id == source.id,
                DomainSnapshot.model_kind == "canonical",
                DomainSnapshot.content_sha256 == content_digest(canonical),
            )
        )
        if legacy is not None and fields.article != canonical:
            evidence = {"status": "historical_snapshot_unprepared"}
        else:
            canonical = fields.article
            evidence = {
                "status": "prepared",
                "catalog_sha256": content_digest(fields.catalog),
                "snapshot_sha256": fields.catalog.canonical_sha256,
                "source_sha256": fields.catalog.source_idml_sha256,
                "xml_sha256": hashlib.sha256(result.xml).hexdigest(),
                "source_scanned": source.scanner_status == "clamav_clean",
                "bindings": len(fields.catalog.bindings),
                "refused": len(fields.refused),
            }
    if enrichment.catalogs:
        current = select_enrichment(
            settings,
            organization_id=job.organization_id,
            resource_id=resource.id,
            source_sha256=source.sha256,
            profile_id=profile.profile_id,
        )
        if current.provenance != enrichment.provenance:
            raise ValueError("enrichment_bundle_changed_during_conversion")
    raw_snapshot, raw_created = store_snapshot(
        db,
        organization_id=job.organization_id,
        resource_id=resource.id,
        document=result.raw,
        revision=1,
        source_artifact_id=source.id,
    )
    canonical_snapshot, canonical_created = store_snapshot(
        db,
        organization_id=job.organization_id,
        resource_id=resource.id,
        document=canonical,
        revision=1,
        source_artifact_id=source.id,
    )
    package_stem = profile.package_stem(result.canonical.article_id)
    xml_artifact = store_generated_artifact(
        db,
        organization_id=job.organization_id,
        original_name=f"{package_stem}.xml",
        data=result.xml,
        media_type="application/xml",
        settings=settings,
    )
    return {
        "resource_id": resource.id,
        "source_artifact_id": source.id,
        "raw_snapshot_id": raw_snapshot.id,
        "canonical_snapshot_id": canonical_snapshot.id,
        "xml_artifact_id": xml_artifact.id,
        "xml_sha256": xml_artifact.sha256,
        "validation": result.validation.model_dump(mode="json"),
        "review_reasons": list(result.canonical.review_reasons),
        "enrichment": enrichment.provenance,
        "field_evidence": evidence,
        "deduplication": {
            "raw_snapshot_reused": not raw_created,
            "canonical_snapshot_reused": not canonical_created,
        },
    }


def _build_package_job(db: Session, job: Job, settings: Settings) -> dict[str, Any]:
    resource = _tenant_resource(db, job)
    snapshot = db.scalar(
        select(DomainSnapshot).where(
            DomainSnapshot.id == _payload_id(job.payload, "canonical_snapshot_id"),
            DomainSnapshot.organization_id == job.organization_id,
            DomainSnapshot.resource_id == resource.id,
            DomainSnapshot.model_kind == "canonical",
        )
    )
    if snapshot is None:
        raise PermanentJobError("canonical snapshot not found in organization")
    document = load_snapshot(snapshot)
    if not isinstance(document, CanonicalArticle):
        raise PermanentJobError("snapshot is not canonical")
    source = _tenant_artifact(db, job, "idml_artifact_id")
    pdf = _tenant_artifact(db, job, "pdf_artifact_id")
    if snapshot.source_artifact_id != source.id:
        raise PermanentJobError("snapshot does not belong to the selected source artifact")
    if source.media_type != "application/vnd.adobe.indesign-idml-package":
        raise PermanentJobError("idml_artifact_id is not an IDML artifact")
    if pdf.media_type != "application/pdf":
        raise PermanentJobError("pdf_artifact_id is not a PDF artifact")
    asset_ids = job.payload.get("asset_artifact_ids", [])
    if not isinstance(asset_ids, list) or any(not isinstance(item, str) for item in asset_ids):
        raise PermanentJobError("asset_artifact_ids is invalid")
    assets: list[AssetPayload] = []
    supplied: dict[str, Artifact] = {}
    for artifact_id in asset_ids:
        artifact = db.scalar(
            select(Artifact).where(
                Artifact.id == artifact_id,
                Artifact.organization_id == job.organization_id,
            )
        )
        if artifact is None:
            raise PermanentJobError("asset artifact not found in organization")
        supplied[artifact.original_name] = artifact
        assets.append(
            AssetPayload(
                source_name=artifact.original_name,
                data=read_artifact_bytes(artifact, settings),
                media_type=artifact.media_type,
            )
        )
    profile = load_profile(settings.journal_profile_path)
    if document.journal_profile_id != profile.profile_id:
        raise PermanentJobError("snapshot journal profile differs from configured profile")
    xml = JatsBuilder(sps_version=profile.sps_version).build(document)
    package_stem = profile.package_stem(document.article_id)
    builder = PackageBuilder()
    files, links = builder.scielo_files_with_bindings(
        package_stem=package_stem,
        xml=xml,
        pdf=read_artifact_bytes(pdf, settings),
        assets=tuple(assets),
    )
    resolved_xml = next(item for item in files if item.role.value == "xml")
    resolved_asset_names = {item.name for item in files if item.role.value == "asset"}
    vendor = Path(__file__).resolve().parents[2] / "vendor" / "jats" / "1.3"
    validation = OfflineJatsValidator(vendor).validate(
        resolved_xml.data,
        asset_names=resolved_asset_names,
    )
    if not validation.valid:
        raise PermanentJobError("canonical snapshot does not produce valid XML")
    package = builder.build(
        article_id=document.article_id,
        profile_id=profile.profile_id,
        source_idml_sha256=source.sha256,
        files=files,
        validator_versions={"offline": validation.validator_profile},
    )
    packaged = {f.name: f.sha256 for f in package.manifest.files}
    figures = []
    referenced_names = {href for href, _, _ in links}
    for href, original, filename in links:
        uploaded = supplied[original]
        if packaged[filename] != uploaded.sha256:
            raise PermanentJobError("packaged figure differs from supplied artifact")
        matches = [a for a in document.assets if a.logical_name == href]
        if len(matches) == 1 and matches[0].sha256 and matches[0].sha256 != uploaded.sha256:
            raise PermanentJobError("supplied figure conflicts with canonical hash")
        verified = (
            len(matches) == 1
            and matches[0].state == "present"
            and matches[0].sha256 == uploaded.sha256
            and uploaded.scanner_status == "clamav_clean"
        )
        figures.append(
            dict(
                xml_href=href,
                package_name=filename,
                artifact_id=uploaded.id,
                sha256=uploaded.sha256,
                source_name=original,
                name_match="exact" if href == original else "figure_number",
                canonical_asset_ids=[a.id for a in matches],
                canonical_origin_verified=verified,
            )
        )
    package_artifact = store_generated_artifact(
        db,
        organization_id=job.organization_id,
        original_name=f"{package_stem}.zip",
        data=package.archive,
        media_type="application/zip",
        settings=settings,
    )
    scope = {
        "organization_id": job.organization_id,
        "resource_id": resource.id,
        "source_idml_sha256": source.sha256,
        "journal_profile_id": profile.profile_id,
        "xml_sha256": hashlib.sha256(resolved_xml.data).hexdigest(),
        "package_sha256": package.package_sha256,
    }
    executor = None
    if settings.validator_socket:
        executor = (
            ScopedValidatorExecutor(
                settings.validator_socket,
                scope=scope,
            )
            if settings.validator_scoped_authorities
            else LocalValidatorExecutor(settings.validator_socket)
        )
    formal_validation = assess_package(
        xml=resolved_xml.data,
        package=package.archive,
        executor=executor,
        registry_path=settings.validator_registry_path,
        expected_scope=scope,
        xpm_executor=XpmSocketExecutor(settings.xpm_socket) if settings.xpm_socket else None,
    )
    return {
        "resource_id": resource.id,
        "snapshot_id": snapshot.id,
        "package_artifact_id": package_artifact.id,
        "package_sha256": package.package_sha256,
        "candidate_set_sha256": package.manifest.candidate_set_sha256,
        "figure_bindings": {
            "version": "package-figure-bindings-1.0",
            "snapshot_sha256": snapshot.content_sha256,
            "source_sha256": source.sha256,
            "package_sha256": package.package_sha256,
            "figures": figures,
            "canonical_asset_count": len(document.assets),
            "unreferenced_asset_ids": [
                a.id for a in document.assets if a.logical_name not in referenced_names
            ],
        },
        "formal_validation": formal_validation,
        "manifest": package.manifest.model_dump(mode="json"),
        "validation": validation.model_dump(mode="json"),
    }


def process_job(
    job_id: str,
    factory: sessionmaker[Session] = SessionLocal,
    *,
    settings: Settings | None = None,
) -> None:
    correlation_id = str(uuid4())
    runtime_settings = settings or get_settings()
    with session_scope(factory) as db:
        job = db.scalar(
            select(Job).where(Job.id == job_id, Job.available_at <= utcnow()).with_for_update()
        )
        if job is None or job.state != "queued":
            return
        transition_job(
            db,
            job,
            to_state="running",
            correlation_id=correlation_id,
            actor_type="worker",
        )
        try:
            # Keep domain writes atomic while preserving the job's failure timeline.
            # A parser/package failure rolls back snapshots and artifacts created by
            # that attempt before the outer transaction records its terminal state.
            with db.begin_nested():
                if job.kind == "foundation.noop":
                    created = record_effect_once(db, job, "foundation.noop.completed")
                    job.result = {"effect_created": created}
                elif job.kind == "idml.process":
                    job.result = _process_idml_job(db, job, runtime_settings)
                    record_effect_once(db, job, "idml.process.completed")
                elif job.kind == "autocorrection.evaluate":
                    job.result = evaluate_revision(db, job, runtime_settings)
                    record_effect_once(db, job, "autocorrection.evaluate.completed")
                elif job.kind == "autocorrection.authorize":
                    job.result = authorize_revision(db, job, runtime_settings)
                    record_effect_once(db, job, "autocorrection.authorize.completed")
                elif job.kind == "autocorrection.restore":
                    job.result = restore_from_web(db, job, runtime_settings)
                    record_effect_once(db, job, "autocorrection.restore.completed")
                elif job.kind == "autocorrection.preflight":
                    job.result = run_edit_preflight(db, job, runtime_settings)
                    record_effect_once(db, job, "autocorrection.preflight.completed")
                elif job.kind == "scielo.package":
                    job.result = _build_package_job(db, job, runtime_settings)
                    record_effect_once(db, job, "scielo.package.completed")
                else:
                    raise UnsupportedJobError("unsupported job kind")
            transition_job(
                db,
                job,
                to_state="succeeded",
                correlation_id=correlation_id,
                actor_type="worker",
            )
            record_audit(
                db,
                action="job.complete",
                resource_type="job",
                resource_id=job.id,
                organization_id=job.organization_id,
                correlation_id=correlation_id,
                outcome="succeeded",
                details={"kind": job.kind},
            )
        except UnsupportedJobError:
            transition_job(
                db,
                job,
                to_state="failed_permanent",
                correlation_id=correlation_id,
                actor_type="worker",
                error_code="unsupported_job",
            )
            record_audit(
                db,
                action="job.fail",
                resource_type="job",
                resource_id=job.id,
                organization_id=job.organization_id,
                correlation_id=correlation_id,
                outcome="failed_permanent",
                details={"kind": job.kind, "error_code": "unsupported_job"},
            )
        except ArtifactStorageError as exc:
            transition_job(
                db,
                job,
                to_state="failed_retryable" if exc.retryable else "failed_permanent",
                correlation_id=correlation_id,
                actor_type="worker",
                error_code=exc.code,
            )
            if exc.retryable:
                schedule_retry(db, job, correlation_id=correlation_id, delay_seconds=30)
            record_audit(
                db,
                action="job.retry_scheduled" if exc.retryable else "job.fail",
                resource_type="job",
                resource_id=job.id,
                organization_id=job.organization_id,
                correlation_id=correlation_id,
                outcome=job.state,
                details={"kind": job.kind, "error_code": exc.code},
            )
        except (FileNotFoundError, PermanentJobError, ValueError):
            transition_job(
                db,
                job,
                to_state="failed_permanent",
                correlation_id=correlation_id,
                actor_type="worker",
                error_code="invalid_job_input",
            )
            record_audit(
                db,
                action="job.fail",
                resource_type="job",
                resource_id=job.id,
                organization_id=job.organization_id,
                correlation_id=correlation_id,
                outcome="failed_permanent",
                details={"kind": job.kind, "error_code": "invalid_job_input"},
            )
        except Exception:
            logger.exception("job execution failed", extra={"job_id": job.id})
            transition_job(
                db,
                job,
                to_state="failed_retryable",
                correlation_id=correlation_id,
                actor_type="worker",
                error_code="transient_failure",
            )
            schedule_retry(db, job, correlation_id=correlation_id, delay_seconds=30)
            record_audit(
                db,
                action="job.retry_scheduled",
                resource_type="job",
                resource_id=job.id,
                organization_id=job.organization_id,
                correlation_id=correlation_id,
                outcome=job.state,
                details={"kind": job.kind, "error_code": job.error_code},
            )


def find_queued_job(factory: sessionmaker[Session] = SessionLocal) -> str | None:
    """Recover durable queued work when a Redis wake-up is lost."""
    with session_scope(factory) as db:
        return db.scalar(
            select(Job.id)
            .where(Job.state == "queued", Job.available_at <= utcnow())
            .order_by(Job.available_at, Job.created_at)
            .limit(1)
        )


def run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    redis = Redis.from_url(
        settings.redis_url, decode_responses=True, socket_connect_timeout=2, socket_timeout=5
    )
    shutdown = Shutdown()

    def request_shutdown(signum: int, frame: object) -> None:
        del signum, frame
        shutdown.requested = True

    signal.signal(signal.SIGTERM, request_shutdown)
    signal.signal(signal.SIGINT, request_shutdown)
    logger.info("worker started", extra={"event": "worker.started"})
    while not shutdown.requested:
        redis_failed = False
        job_id = find_queued_job()
        try:
            if job_id is not None:
                # Drain a hint without blocking durable work behind a Redis timeout.
                redis.rpop("idml:jobs")
            else:
                redis.brpop(["idml:jobs"], timeout=2)
        except Exception:
            logger.exception("worker loop failure", extra={"event": "worker.loop_failure"})
            redis_failed = True
        if job_id is None:
            # Redis is only a wake-up hint. Always use the durable due-time/order,
            # including after stale, duplicate, or out-of-order notifications.
            job_id = find_queued_job()
        if job_id is not None:
            process_job(job_id)
        elif redis_failed:
            time.sleep(2)
    logger.info("worker stopped", extra={"event": "worker.stopped"})


def main() -> None:
    run()


if __name__ == "__main__":
    main()
