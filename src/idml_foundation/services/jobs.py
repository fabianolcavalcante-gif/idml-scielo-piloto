from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from idml_foundation.models import Job, JobEffect, JobEvent, utcnow

TERMINAL_STATES = {"succeeded", "failed_permanent", "cancelled", "quarantined"}
RETRYABLE_STATES = {"failed_retryable"}
TRANSITIONS: dict[str, frozenset[str]] = {
    "queued": frozenset({"running", "cancelled", "quarantined"}),
    "running": frozenset({"succeeded", "failed_retryable", "failed_permanent", "cancelled"}),
    "failed_retryable": frozenset({"queued", "failed_permanent", "cancelled"}),
    "succeeded": frozenset(),
    "failed_permanent": frozenset(),
    "cancelled": frozenset(),
    "quarantined": frozenset(),
}


class IdempotencyConflictError(ValueError):
    pass


def create_job(
    db: Session,
    *,
    organization_id: str,
    kind: str,
    idempotency_key: str,
    payload: dict[str, Any],
    correlation_id: str,
    actor_id: str,
) -> tuple[Job, bool]:
    existing = db.scalar(
        select(Job).where(
            Job.organization_id == organization_id,
            Job.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        if existing.kind != kind or existing.payload != payload:
            raise IdempotencyConflictError(
                "idempotency key is already bound to a different request"
            )
        return existing, False
    job = Job(
        organization_id=organization_id,
        kind=kind,
        idempotency_key=idempotency_key,
        payload=payload,
    )
    db.add(job)
    db.flush()
    db.add(
        JobEvent(
            job_id=job.id,
            organization_id=organization_id,
            sequence=1,
            from_state=None,
            to_state="queued",
            actor_type="user",
            actor_id=actor_id,
            correlation_id=correlation_id,
        )
    )
    db.flush()
    return job, True


def transition_job(
    db: Session,
    job: Job,
    *,
    to_state: str,
    correlation_id: str,
    actor_type: str,
    actor_id: str | None = None,
    expected_version: int | None = None,
    error_code: str | None = None,
) -> Job:
    if expected_version is not None and job.version != expected_version:
        raise ValueError("job version conflict")
    if to_state not in TRANSITIONS.get(job.state, frozenset()):
        raise ValueError(f"invalid job transition: {job.state} -> {to_state}")
    previous = job.state
    job.state = to_state
    job.version += 1
    job.error_code = error_code
    if to_state == "running":
        job.started_at = utcnow()
        job.attempt_count += 1
    if to_state in TERMINAL_STATES:
        job.finished_at = utcnow()
    if to_state == "cancelled":
        job.cancelled_at = job.finished_at
    sequence = db.scalar(
        select(func.coalesce(func.max(JobEvent.sequence), 0)).where(JobEvent.job_id == job.id)
    )
    db.add(
        JobEvent(
            job_id=job.id,
            organization_id=job.organization_id,
            sequence=int(sequence or 0) + 1,
            from_state=previous,
            to_state=to_state,
            actor_type=actor_type,
            actor_id=actor_id,
            correlation_id=correlation_id,
            details={"error_code": error_code} if error_code else {},
        )
    )
    db.flush()
    return job


def schedule_retry(db: Session, job: Job, *, correlation_id: str, delay_seconds: int) -> Job:
    if job.state != "failed_retryable":
        raise ValueError("only retryable jobs can be scheduled")
    if job.attempt_count >= job.max_attempts:
        return transition_job(
            db,
            job,
            to_state="failed_permanent",
            correlation_id=correlation_id,
            actor_type="system",
            error_code="max_attempts_exceeded",
        )
    job.available_at = utcnow() + timedelta(seconds=delay_seconds)
    return transition_job(
        db,
        job,
        to_state="queued",
        correlation_id=correlation_id,
        actor_type="system",
    )


def record_effect_once(db: Session, job: Job, effect_key: str) -> bool:
    existing = db.scalar(
        select(JobEffect).where(JobEffect.job_id == job.id, JobEffect.effect_key == effect_key)
    )
    if existing is not None:
        return False
    try:
        with db.begin_nested():
            db.add(
                JobEffect(
                    job_id=job.id,
                    organization_id=job.organization_id,
                    effect_key=effect_key,
                )
            )
            db.flush()
    except IntegrityError:
        return False
    return True
