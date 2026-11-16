"""Durable scheduling regressions; mocked Redis is not a capacity qualification."""

import signal
from datetime import timedelta
from types import SimpleNamespace

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import func, select

from idml_foundation import worker
from idml_foundation.models import Job, JobEffect, JobEvent, Organization, utcnow
from idml_foundation.routers.jobs import _wake_worker
from idml_foundation.services.jobs import create_job


def enqueue(db, count=1):
    org = Organization(slug="v12-queue", name="Synthetic queue")
    db.add(org)
    db.flush()
    ids = []
    for index in range(count):
        job, _ = create_job(
            db,
            organization_id=org.id,
            kind="foundation.noop",
            idempotency_key=f"v12-queue-{index:04d}",
            payload={},
            correlation_id="v12-queue",
            actor_id="synthetic",
        )
        ids.append(job.id)
    db.commit()
    return ids


def test_direct_notification_cannot_bypass_due_time(db, session_factory):
    job_id = enqueue(db)[0]
    job = db.get(Job, job_id)
    job.available_at = utcnow() + timedelta(minutes=10)
    db.commit()
    worker.process_job(job_id, session_factory)
    db.expire_all()
    assert job.state == "queued"
    assert job.attempt_count == 0
    assert db.scalar(select(func.count(JobEvent.id))) == 1
    assert worker.find_queued_job(session_factory) is None
    job.available_at = utcnow() - timedelta(seconds=1)
    db.commit()
    worker.process_job(job_id, session_factory)
    db.expire_all()
    assert job.state == "succeeded"


@pytest.mark.parametrize("redis_mode", ["lost", "duplicate", "unavailable"])
def test_backlog_drains_without_blocking_or_duplicate_effects(
    db, session_factory, settings, monkeypatch, redis_mode
):
    ids = enqueue(db, 20)
    callbacks = {}
    processed = []

    def pop(_queue):
        if redis_mode == "unavailable":
            raise RedisConnectionError("synthetic outage")
        return ids[-1] if redis_mode == "duplicate" else None

    def blocking_pop(*_args, **_kwargs):
        pytest.fail("durable backlog must not wait on Redis")

    original_process = worker.process_job

    def process(job_id):
        original_process(job_id, session_factory, settings=settings)
        processed.append(job_id)
        if len(processed) == len(ids):
            callbacks[signal.SIGTERM](signal.SIGTERM, None)

    monkeypatch.setattr(worker.signal, "signal", lambda key, value: callbacks.update({key: value}))
    monkeypatch.setattr(worker, "get_settings", lambda: settings)
    monkeypatch.setattr(worker, "find_queued_job", lambda: find_job(session_factory))
    monkeypatch.setattr(worker, "process_job", process)
    redis = SimpleNamespace(rpop=pop, brpop=blocking_pop)
    monkeypatch.setattr(worker.Redis, "from_url", lambda *_args, **_kwargs: redis)
    worker.run()
    assert processed == ids
    db.expire_all()
    assert db.scalar(select(func.count(JobEffect.id))) == 20
    assert all(
        job.state == "succeeded" and job.attempt_count == 1 for job in db.scalars(select(Job))
    )


find_job = worker.find_queued_job


@pytest.mark.parametrize("wake_mode", ["empty", "stale", "outage"])
def test_idle_worker_rechecks_durable_queue_after_wakeup(
    db, session_factory, settings, monkeypatch, wake_mode
):
    job_id = enqueue(db)[0]
    job = db.get(Job, job_id)
    job.available_at = utcnow() + timedelta(hours=1)
    db.commit()
    callbacks = {}
    processed = []
    original_process = worker.process_job

    def wake(*_args, **_kwargs):
        job.available_at = utcnow() - timedelta(seconds=1)
        db.commit()
        if wake_mode == "outage":
            raise RedisConnectionError("synthetic outage")
        return ("idml:jobs", "nonexistent-job") if wake_mode == "stale" else None

    def process(selected):
        original_process(selected, session_factory, settings=settings)
        processed.append(selected)
        callbacks[signal.SIGTERM](signal.SIGTERM, None)

    monkeypatch.setattr(worker.signal, "signal", lambda key, value: callbacks.update({key: value}))
    monkeypatch.setattr(worker, "get_settings", lambda: settings)
    monkeypatch.setattr(worker, "find_queued_job", lambda: find_job(session_factory))
    monkeypatch.setattr(worker, "process_job", process)
    monkeypatch.setattr(
        worker.Redis, "from_url", lambda *_args, **_kwargs: SimpleNamespace(brpop=wake)
    )
    worker.run()
    assert processed == [job_id]
    db.expire_all()
    assert job.state == "succeeded"


def test_api_wakeup_has_bounded_network_timeouts(db, settings, monkeypatch):
    job_id = enqueue(db)[0]
    captured = {}

    def connect(_url, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(lpush=lambda *_args: 1)

    monkeypatch.setattr("idml_foundation.routers.jobs.Redis.from_url", connect)
    _wake_worker(db, settings, db.get(Job, job_id), "v12-timeouts")
    assert captured == {"socket_connect_timeout": 2, "socket_timeout": 2}
