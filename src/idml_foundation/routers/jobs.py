import logging
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, status
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.orm import Session

from idml_foundation.dependencies import (
    Configuration,
    CorrelationId,
    Database,
    require_permission,
)
from idml_foundation.models import Job, JobEvent
from idml_foundation.rbac import Permission, TenantContext
from idml_foundation.schemas import JobControlRequest, JobCreate, JobEventRead, JobRead
from idml_foundation.services.audit import record_audit
from idml_foundation.services.jobs import (
    IdempotencyConflictError,
    create_job,
    schedule_retry,
    transition_job,
)
from idml_foundation.services.validation_diagnosis import describe_validation

router = APIRouter(prefix="/v1/jobs", tags=["jobs"])
logger = logging.getLogger(__name__)


def _wake_worker(db: Session, settings: Configuration, job: Job, correlation_id: str) -> None:
    # The database remains the durable queue. Commit before the best-effort
    # notification so a fast worker can always observe the queued row.
    job_id = job.id
    organization_id = job.organization_id
    db.commit()
    db.refresh(job)
    try:
        Redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2).lpush(
            "idml:jobs", job_id
        )
    except RedisError:
        logger.warning(
            "job persisted; Redis wake-up failed",
            extra={
                "event": "job.redis_wakeup_failed",
                "job_id": job_id,
                "organization_id": organization_id,
                "correlation_id": correlation_id,
            },
        )


@router.get("", response_model=list[JobRead])
def list_jobs(
    db: Database,
    context: Annotated[TenantContext, require_permission(Permission.JOB_READ)],
) -> list[Job]:
    return list(
        db.scalars(
            select(Job)
            .where(Job.organization_id == context.organization_id)
            .order_by(Job.created_at.desc())
            .limit(200)
        )
    )


@router.post("", response_model=JobRead, status_code=status.HTTP_202_ACCEPTED)
def enqueue_job(
    payload: JobCreate,
    db: Database,
    settings: Configuration,
    correlation_id: CorrelationId,
    context: Annotated[TenantContext, require_permission(Permission.JOB_CREATE)],
) -> Job:
    try:
        job, created = create_job(
            db,
            organization_id=context.organization_id,
            kind=payload.kind,
            idempotency_key=payload.idempotency_key,
            payload=payload.payload,
            correlation_id=correlation_id,
            actor_id=context.user.id,
        )
    except IdempotencyConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if created:
        record_audit(
            db,
            action="job.create",
            resource_type="job",
            resource_id=job.id,
            organization_id=context.organization_id,
            actor_user_id=context.user.id,
            correlation_id=correlation_id,
            outcome="queued",
            details={"kind": job.kind, "idempotency_key": job.idempotency_key},
        )
        _wake_worker(db, settings, job, correlation_id)
    return job


@router.get("/{job_id}", response_model=JobRead)
def get_job(
    job_id: str,
    db: Database,
    context: Annotated[TenantContext, require_permission(Permission.JOB_READ)],
) -> Job:
    job = db.scalar(
        select(Job).where(Job.id == job_id, Job.organization_id == context.organization_id)
    )
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
    return job


@router.get("/{job_id}/validation-diagnosis")
def get_validation_diagnosis(
    job_id: str,
    db: Database,
    context: Annotated[TenantContext, require_permission(Permission.JOB_READ)],
) -> dict[str, Any]:
    job = get_job(job_id, db, context)
    return describe_validation(job.result)


@router.get("/{job_id}/events", response_model=list[JobEventRead])
def get_job_events(
    job_id: str,
    db: Database,
    context: Annotated[TenantContext, require_permission(Permission.JOB_READ)],
) -> list[JobEvent]:
    job = db.scalar(
        select(Job.id).where(
            Job.id == job_id,
            Job.organization_id == context.organization_id,
        )
    )
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
    return list(
        db.scalars(
            select(JobEvent)
            .where(
                JobEvent.job_id == job_id,
                JobEvent.organization_id == context.organization_id,
            )
            .order_by(JobEvent.sequence)
        )
    )


@router.post("/{job_id}/cancel", response_model=JobRead)
def cancel_job(
    job_id: str,
    payload: JobControlRequest,
    db: Database,
    correlation_id: CorrelationId,
    context: Annotated[TenantContext, require_permission(Permission.JOB_CREATE)],
) -> Job:
    job = db.scalar(
        select(Job).where(
            Job.id == job_id,
            Job.organization_id == context.organization_id,
        )
    )
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
    try:
        transition_job(
            db,
            job,
            to_state="cancelled",
            correlation_id=correlation_id,
            actor_type="user",
            actor_id=context.user.id,
            expected_version=payload.expected_version,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    record_audit(
        db,
        action="job.cancel",
        resource_type="job",
        resource_id=job.id,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        correlation_id=correlation_id,
        outcome="cancelled",
    )
    return job


@router.post("/{job_id}/retry", response_model=JobRead)
def retry_job(
    job_id: str,
    payload: JobControlRequest,
    db: Database,
    settings: Configuration,
    correlation_id: CorrelationId,
    context: Annotated[TenantContext, require_permission(Permission.JOB_CREATE)],
) -> Job:
    job = db.scalar(
        select(Job).where(
            Job.id == job_id,
            Job.organization_id == context.organization_id,
        )
    )
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
    if job.version != payload.expected_version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="job version conflict")
    try:
        schedule_retry(db, job, correlation_id=correlation_id, delay_seconds=0)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    record_audit(
        db,
        action="job.retry",
        resource_type="job",
        resource_id=job.id,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        correlation_id=correlation_id,
        outcome=job.state,
        details={"attempt_count": job.attempt_count},
    )
    if job.state == "queued":
        _wake_worker(db, settings, job, correlation_id)
    return job
