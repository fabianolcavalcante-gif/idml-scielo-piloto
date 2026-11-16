import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from idml_foundation.models import JobEffect, JobEvent, Organization
from idml_foundation.services.jobs import (
    IdempotencyConflictError,
    create_job,
    record_effect_once,
    schedule_retry,
    transition_job,
)


def test_idempotent_job_creation_and_effects(db: Session) -> None:
    org = Organization(slug="jobs", name="Jobs")
    db.add(org)
    db.flush()
    first, created = create_job(
        db,
        organization_id=org.id,
        kind="foundation.noop",
        idempotency_key="same-request-0001",
        payload={"value": 1},
        correlation_id="job-correlation-1",
        actor_id="test-user",
    )
    second, created_again = create_job(
        db,
        organization_id=org.id,
        kind="foundation.noop",
        idempotency_key="same-request-0001",
        payload={"value": 1},
        correlation_id="job-correlation-2",
        actor_id="test-user",
    )
    assert created is True
    assert created_again is False
    assert first.id == second.id
    with pytest.raises(IdempotencyConflictError, match="different request"):
        create_job(
            db,
            organization_id=org.id,
            kind="foundation.noop",
            idempotency_key="same-request-0001",
            payload={"value": 2},
            correlation_id="job-correlation-3",
            actor_id="test-user",
        )
    assert record_effect_once(db, first, "write-once") is True
    assert record_effect_once(db, first, "write-once") is False
    assert db.scalar(select(func.count(JobEffect.id))) == 1


def test_retry_state_machine_preserves_timeline(db: Session) -> None:
    org = Organization(slug="retry", name="Retry")
    db.add(org)
    db.flush()
    job, _ = create_job(
        db,
        organization_id=org.id,
        kind="foundation.noop",
        idempotency_key="retry-request-0001",
        payload={},
        correlation_id="corr-create",
        actor_id="test-user",
    )
    transition_job(
        db,
        job,
        to_state="running",
        correlation_id="corr-run",
        actor_type="worker",
        expected_version=1,
    )
    transition_job(
        db,
        job,
        to_state="failed_retryable",
        correlation_id="corr-fail",
        actor_type="worker",
        error_code="temporary",
    )
    schedule_retry(db, job, correlation_id="corr-retry", delay_seconds=1)
    assert job.state == "queued"
    assert job.attempt_count == 1
    events = list(db.scalars(select(JobEvent).order_by(JobEvent.sequence)))
    assert [event.to_state for event in events] == [
        "queued",
        "running",
        "failed_retryable",
        "queued",
    ]
    assert [event.sequence for event in events] == [1, 2, 3, 4]
