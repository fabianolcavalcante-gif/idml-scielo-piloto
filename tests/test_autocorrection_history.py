import copy
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, select, update
from sqlalchemy.exc import DatabaseError
from sqlalchemy.orm import sessionmaker

from idml_foundation.autocorrection_models import AutomationRevalidation
from idml_foundation.database import Base
from idml_foundation.models import Artifact, DomainSnapshot
from idml_foundation.services.autocorrection_executor import discard_candidate
from idml_foundation.services.autocorrection_history import read_revalidation, revalidate_and_store
from idml_foundation.settings import get_settings
from tests.autocorrection_helpers import persisted_data
from tests.test_autocorrection_package import PassingOffline, with_package_inputs
from tests.test_autocorrection_package import data as data
from tests.test_package_formal_validation import completed
from tests.test_xpm_execution import execution


def save(db, data, request_id, **overrides):
    return revalidate_and_store(
        db,
        **(
            {
                "organization_id": str(data["context"].scope.organization_id),
                "attempt_id": data["attempt"].id,
                "request_id": request_id,
                "intent": data["intent"],
                "context": data["context"],
                "pdf_artifact_id": data["pdf"].id,
                "pdf_sha256": data["pdf"].sha256,
                "profile": data["profile"],
                "settings": data["settings"],
                "validator": PassingOffline(),
                "executor": completed,
                "clock": lambda: data["now"],
            }
            | overrides
        ),
    )


def test_persisted_revalidation_is_historical_private_idempotent_and_not_a_release(db, data):
    request_id = uuid4()
    row = save(db, data, request_id)
    db.commit()
    assert not row.receipt["promotion_authorized"] and not row.receipt["release_approved"]
    assert row.receipt["historical_evidence_only"]
    assert row.receipt["state"] == "validation-unavailable"
    seen = []
    assert save(db, data, request_id, executor=lambda *a: seen.append(a)).id == row.id
    assert not seen
    assert db.scalar(select(func.count()).select_from(AutomationRevalidation)) == 1
    assert db.scalar(select(func.count()).select_from(DomainSnapshot)) == 1
    assert db.get(Artifact, row.package_artifact_id).original_name.startswith("evaluation-")
    assert (
        read_revalidation(
            db, organization_id=row.organization_id, record_id=row.id, settings=data["settings"]
        ).receipt
        == row.receipt
    )


def test_new_request_revalidates_and_reuses_identical_bytes(db, data):
    first = save(db, data, uuid4())
    db.commit()
    seen = []

    def execute(payload, spec):
        seen.append(spec.name)
        return completed(payload, spec)

    second = save(db, data, uuid4(), executor=execute)
    assert second.id != first.id and seen == ["packtools", "spsvalidator"]
    assert second.xml_artifact_id == first.xml_artifact_id
    assert second.package_artifact_id == first.package_artifact_id


def test_xpm_is_bound_to_rebuilt_package_and_persisted_without_promoting(db, data):
    calls = []

    def execute(payload, scope):
        calls.append(scope.copy())
        return execution(payload, scope, errors=1, queries=False)

    request = uuid4()
    row = save(db, data, request, xpm_executor=execute)
    db.commit()
    assert len(calls) == 1
    assert calls[0]["organization_id"] == row.organization_id
    assert calls[0]["resource_id"] == row.resource_id
    assert calls[0]["xml_sha256"] == row.receipt["xml_sha256"]
    assert calls[0]["package_sha256"] == row.receipt["package_sha256"]
    assert calls[0]["source_idml_sha256"] == data["context"].scope.source_idml_sha256
    assert row.reports["formal"]["xpm"]["counts"]["errors"] == 1
    assert row.receipt["state"] == "blocked"
    assert not row.receipt["promotion_authorized"]
    assert save(db, data, request, xpm_executor=execute).id == row.id
    assert len(calls) == 1  # Historical replay is not a new execution.
    save(db, data, uuid4(), xpm_executor=execute)
    assert len(calls) == 2


def test_bad_offline_result_never_dispatches_xpm(db, data):
    class BrokenOffline:
        def validate(self, *args, **kwargs):
            raise ValueError("private-validator-error")

    def forbidden(*args):
        pytest.fail("offline failure dispatched XPM")

    row = save(db, data, uuid4(), validator=BrokenOffline(), xpm_executor=forbidden)
    assert "offline-validation-unavailable" in row.receipt["reasons"]
    assert row.reports["formal"]["xpm"]["status"] == "unavailable"


def test_discarded_attempt_can_be_audited_but_not_revalidated_as_new(db, data):
    request_id = uuid4()
    row = save(db, data, request_id)
    discard_candidate(
        db, organization_id=row.organization_id, attempt_id=data["attempt"].id, now=data["now"]
    )
    db.commit()
    assert save(db, data, request_id).id == row.id
    with pytest.raises(ValueError, match="candidate_unavailable"):
        save(db, data, uuid4())


@pytest.mark.parametrize("field", ["pdf_sha256", "pdf_artifact_id", "attempt_id"])
def test_request_key_cannot_be_rebound(db, data, field):
    request_id = uuid4()
    save(db, data, request_id)
    with pytest.raises(ValueError, match="request_conflict"):
        save(
            db, data, request_id, **{field: "e" * 64 if field.endswith("sha256") else str(uuid4())}
        )


def test_cross_tenant_write_and_read_refused(db, data):
    row = save(db, data, uuid4())
    with pytest.raises(PermissionError):
        save(db, data, uuid4(), organization_id=str(uuid4()))
    with pytest.raises(LookupError):
        read_revalidation(
            db, organization_id=str(uuid4()), record_id=row.id, settings=data["settings"]
        )


def test_outer_rollback_removes_rows_not_source_and_retry_recovers_cas_orphans(db, data):
    count = db.scalar(select(func.count()).select_from(Artifact))
    request_id = uuid4()
    first = save(db, data, request_id)
    digest = first.receipt["package_sha256"]
    db.rollback()
    assert db.scalar(select(func.count()).select_from(AutomationRevalidation)) == 0
    assert db.scalar(select(func.count()).select_from(Artifact)) == count
    recovered = save(db, data, request_id)
    assert recovered.receipt["package_sha256"] == digest


@pytest.mark.parametrize("fault", ["second_write", "history_flush"])
def test_interruption_does_not_leave_partial_persisted_result(db, data, monkeypatch, fault):
    import idml_foundation.services.autocorrection_history as module

    count = db.scalar(select(func.count()).select_from(Artifact))
    original = module.store_generated_artifact
    calls = 0

    def interrupt(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2 and fault == "second_write":
            raise RuntimeError("synthetic interruption")
        return original(*args, **kwargs)

    monkeypatch.setattr(module, "store_generated_artifact", interrupt)
    if fault == "history_flush":
        from sqlalchemy import event

        def fail(*args):
            raise RuntimeError("synthetic interruption")

        event.listen(AutomationRevalidation, "before_insert", fail)
    try:
        with pytest.raises(RuntimeError, match="synthetic interruption"):
            save(db, data, uuid4())
    finally:
        if fault == "history_flush":
            event.remove(AutomationRevalidation, "before_insert", fail)
    assert db.scalar(select(func.count()).select_from(AutomationRevalidation)) == 0
    assert db.scalar(select(func.count()).select_from(Artifact)) == count


@pytest.mark.parametrize("fault", ["receipt", "reports", "artifact_bytes", "artifact_tenant"])
def test_history_and_artifact_tampering_fail_closed(db, data, fault):
    row = save(db, data, uuid4())
    db.commit()
    if fault in {"receipt", "reports"}:
        payload = copy.deepcopy(getattr(row, fault))
        payload["invented"] = True
        db.execute(
            update(AutomationRevalidation)
            .where(AutomationRevalidation.id == row.id)
            .values(**{fault: payload})
        )
    else:
        artifact = db.get(Artifact, row.package_artifact_id)
        if fault == "artifact_bytes":
            (data["settings"].artifact_root / artifact.storage_key).write_bytes(b"tampered")
        else:
            # Raw update simulates corruption; unit DB is not the migrated trigger DB.
            db.execute(
                update(Artifact)
                .where(Artifact.id == artifact.id)
                .values(storage_key=f"{uuid4()}/wrong")
            )
    with pytest.raises(ValueError, match="automation_revalidation_"):
        read_revalidation(
            db, organization_id=row.organization_id, record_id=row.id, settings=data["settings"]
        )


def test_native_or_sqlite_database_migration_guards(tmp_path, monkeypatch, settings):
    url = f"sqlite+pysqlite:///{tmp_path / 'history.sqlite'}"
    monkeypatch.setenv("IDML_DATABASE_URL", url)
    monkeypatch.setenv("IDML_ENVIRONMENT", "test")
    get_settings.cache_clear()
    engine = create_engine(url)
    try:
        command.upgrade(Config("alembic.ini"), "head")
        with sessionmaker(engine, expire_on_commit=False)() as db:
            test_data = with_package_inputs(db, persisted_data(db, settings))
            row = save(db, test_data, uuid4())
            db.commit()
            record_id = row.id
        with engine.connect() as connection:
            for action in (
                "UPDATE automation_revalidations SET request_sha256='changed' WHERE id=:id",
                "DELETE FROM automation_revalidations WHERE id=:id",
            ):
                from sqlalchemy import text

                with pytest.raises(DatabaseError, match="autocorrection_history_is_append_only"):
                    connection.execute(text(action), {"id": record_id})
                connection.rollback()
    finally:
        engine.dispose()
        get_settings.cache_clear()


def test_two_sessions_persist_one_request(tmp_path, settings):
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'race.sqlite'}", connect_args={"timeout": 20}
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, autoflush=False, expire_on_commit=False)
    try:
        with sessions() as db:
            test_data = with_package_inputs(db, persisted_data(db, settings))
        barrier = Barrier(2)
        request_id = uuid4()

        def execute():
            with sessions() as db:
                barrier.wait(timeout=10)
                row = save(db, test_data, request_id)
                db.commit()
                return row.id

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(execute) for _ in range(2)]
            assert futures[0].result(timeout=30) == futures[1].result(timeout=30)
    finally:
        engine.dispose()
