"""Synthetic HTTP/worker probe for a disposable PostgreSQL/Redis network only."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timedelta

from redis import Redis
from sqlalchemy import func, select

from idml_foundation.database import SessionLocal
from idml_foundation.models import Job, JobEffect, JobEvent, Membership, Organization, User, utcnow
from idml_foundation.security import issue_session
from idml_foundation.settings import Settings
from ops.benchmark_phase7_v12 import fixture
from ops.probe_phase7_v12_storage import probe as storage_probe

BASE = "http://127.0.0.1:8000"


def request(path, headers=None, data=None, content_type="application/json"):
    headers = dict(headers or {})
    if data is not None:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(BASE + path, data=data, headers=headers)  # noqa: S310 - fixed loopback
    with urllib.request.urlopen(req, timeout=15) as response:  # noqa: S310 - fixed loopback
        body = response.read()
        return json.loads(body) if "json" in response.headers.get("Content-Type", "") else body


def post(path, headers, data):
    return request(path, headers, json.dumps(data).encode())


def stop(process):
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def main():
    settings = Settings()
    if (
        settings.environment != "test"
        or settings.database_url != "postgresql+psycopg://v12lab:v12lab@pg:5432/v12lab"
        or settings.redis_url != "redis://redis:6379/0"
        or settings.feature_openclaw
        or settings.feature_ai_swarm
    ):
        raise ValueError("refusing non-laboratory configuration")
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=45,
    )
    with SessionLocal.begin() as db:
        org = Organization(slug="v12-lab", name="Synthetic capacity laboratory")
        user = User(email="v12@example.test", password_hash="disabled-lab-login")  # noqa: S106 - no password login
        db.add_all([org, user])
        db.flush()
        db.add(Membership(organization_id=org.id, user_id=user.id, role="operator"))
        token = issue_session(db, user, settings)
        headers = {"Authorization": f"Bearer {token.raw_token}", "X-Organization-ID": org.id}
    redis = Redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2)
    api = worker = None
    scenarios = []
    try:
        api = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "idml_foundation.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
                "--no-access-log",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(80):
            try:
                request("/health/ready")
                break
            except OSError:
                time.sleep(0.25)
        else:
            raise RuntimeError("lab API unavailable")
        source = fixture(16)
        boundary = "v12syntheticboundary"
        multipart = (
            f'--{boundary}\r\nContent-Disposition: form-data; name="upload"; '
            'filename="ESA_2024001_AOP.idml"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n"
        ).encode()
        multipart += source + f"\r\n--{boundary}--\r\n".encode()
        artifact = request(
            "/v1/artifacts/idml", headers, multipart, f"multipart/form-data; boundary={boundary}"
        )
        for mode in ("normal", "duplicate", "lost", "outage"):
            if mode == "outage":
                redis.shutdown(nosave=True)
            ids = []
            requests_ms = []
            for index in range(6):
                resource = post("/v1/resources", headers, {"title": "Synthetic capacity article"})
                payload = {
                    "kind": "idml.process",
                    "idempotency_key": f"v12-{mode}-{index:04d}",
                    "payload": {"resource_id": resource["id"], "idml_artifact_id": artifact["id"]},
                }
                started = time.perf_counter()
                job = post("/v1/jobs", headers, payload)
                requests_ms.append(round((time.perf_counter() - started) * 1000, 3))
                ids.append(job["id"])
                if index == 0 and post("/v1/jobs", headers, payload)["id"] != job["id"]:
                    raise AssertionError("idempotency failed")
            with SessionLocal.begin() as db:
                delayed = db.get(Job, ids[-1])
                delayed.available_at = utcnow() + timedelta(seconds=12)
            if mode == "duplicate":
                redis.lpush("idml:jobs", *(["missing-job", ids[-1]] * 20))
            elif mode == "lost":
                redis.delete("idml:jobs")  # disposable Redis, exact key only
            began = time.perf_counter()
            delayed_observed_waiting = False
            worker = subprocess.Popen(
                [sys.executable, "-m", "idml_foundation.worker"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            while time.perf_counter() - began < 75:
                results = [request(f"/v1/jobs/{job_id}", headers) for job_id in ids]
                if (
                    all(row["state"] == "succeeded" for row in results[:-1])
                    and results[-1]["state"] == "queued"
                    and datetime.fromisoformat(results[-1]["available_at"]) > utcnow()
                ):
                    delayed_observed_waiting = True
                if all(row["state"] == "succeeded" for row in results):
                    break
                if any(row["state"] == "failed_permanent" for row in results):
                    raise AssertionError("conversion failed")
                if worker.poll() is not None:
                    raise AssertionError("worker exited")
                time.sleep(0.25)
            else:
                raise TimeoutError("queue did not drain")
            elapsed = time.perf_counter() - began
            stop(worker)
            worker = None
            with SessionLocal() as db:
                rows = list(db.scalars(select(Job).where(Job.id.in_(ids))))
                effects = db.scalar(
                    select(func.count(JobEffect.id)).where(JobEffect.job_id.in_(ids))
                )
                events = db.scalar(select(func.count(JobEvent.id)).where(JobEvent.job_id.in_(ids)))
                valid = all(
                    row.attempt_count == 1
                    and row.started_at >= row.available_at
                    and row.result["validation"]["valid"]
                    for row in rows
                )
                digests = {row.result["xml_sha256"] for row in rows}
                timing = [
                    {
                        "queue_ms": round((r.started_at - r.created_at).total_seconds() * 1000, 3),
                        "execution_ms": round(
                            (r.finished_at - r.started_at).total_seconds() * 1000, 3
                        ),
                    }
                    for r in rows
                ]
            download = request(
                f"/v1/artifacts/{results[0]['result']['xml_artifact_id']}/download", headers
            )
            approved = (
                valid
                and delayed_observed_waiting
                and len(digests) == 1
                and effects == 6
                and events == 18
                and hashlib.sha256(download).hexdigest() in digests
            )
            scenarios.append(
                {
                    "mode": mode,
                    "approved": approved,
                    "jobs": 6,
                    "elapsed_seconds": round(elapsed, 3),
                    "samples": timing,
                    "enqueue_ms": requests_ms,
                    "effects": effects,
                    "events": events,
                    "xml_sha256": sorted(digests),
                    "delayed_job_respected": valid,
                    "delayed_observed_waiting": delayed_observed_waiting,
                }
            )
        storage = storage_probe(settings)
        report = {
            "version": "phase7-v12-real-queue-1.0",
            "approved": len(scenarios) == 4
            and all(r["approved"] for r in scenarios)
            and storage["approved"],
            "storage": storage,
            "scenarios": scenarios,
            "provider_calls": 0,
            "restricted_content_emitted": False,
            "production_capacity_qualified": False,
            "v12_complete": False,
            "release_ready": False,
        }
        print(json.dumps(report), flush=True)
        return 0 if report["approved"] else 2
    finally:
        stop(worker)
        stop(api)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(
            json.dumps(
                {
                    "approved": False,
                    "error": type(exc).__name__,
                    "restricted_content_emitted": False,
                    "release_ready": False,
                }
            ),
            flush=True,
        )
        raise SystemExit(2) from None
