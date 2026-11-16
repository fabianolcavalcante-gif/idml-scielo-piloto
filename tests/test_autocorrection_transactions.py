from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from threading import Barrier

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.exc import DatabaseError
from sqlalchemy.orm import sessionmaker

from idml_foundation.autocorrection_models import AutomationAttempt
from idml_foundation.database import Base
from idml_foundation.services.autocorrection_executor import stage_autocorrection
from idml_foundation.settings import get_settings
from tests.autocorrection_helpers import persisted_data, stage_kwargs


def test_two_workers_commit_one_identical_attempt(tmp_path, settings):
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'concurrent.sqlite'}", connect_args={"timeout": 15}
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, autoflush=False, expire_on_commit=False)
    try:
        with sessions() as db:
            data = persisted_data(db, settings)
        barrier = Barrier(2)

        def execute():
            with sessions() as db:
                barrier.wait(timeout=10)
                attempt = stage_autocorrection(db, **stage_kwargs(data))
                db.commit()
                return attempt.id

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(execute) for _ in range(2)]
            results = [future.result(timeout=30) for future in futures]
        assert results[0] == results[1]
        with sessions() as db:
            assert db.scalar(select(func.count()).select_from(AutomationAttempt)) == 1
    finally:
        engine.dispose()


def test_migration_upgrade_rollback_and_database_history_guards(tmp_path, monkeypatch, settings):
    url = f"sqlite+pysqlite:///{tmp_path / 'migration.sqlite'}"
    monkeypatch.setenv("IDML_DATABASE_URL", url)
    monkeypatch.setenv("IDML_ENVIRONMENT", "test")
    get_settings.cache_clear()
    config = Config("alembic.ini")
    engine = create_engine(url)
    try:
        command.upgrade(config, "head")
        assert "automation_attempts" in inspect(engine).get_table_names()
        with sessionmaker(engine, autoflush=False, expire_on_commit=False)() as db:
            data = persisted_data(db, settings)
            attempt = stage_autocorrection(db, **stage_kwargs(data))
            db.commit()
            attempt_id = attempt.id
        with engine.connect() as connection:
            for sql in (
                "UPDATE automation_attempts SET xml_content = 'changed' WHERE id = ?",
                "DELETE FROM automation_attempts WHERE id = ?",
            ):
                with pytest.raises(DatabaseError, match="autocorrection_history_is_append_only"):
                    connection.exec_driver_sql(sql, (attempt_id,))
                connection.rollback()
            assert (
                connection.exec_driver_sql("SELECT count(*) FROM automation_attempts").scalar() == 1
            )
        command.downgrade(config, "f7b8c9d0e1f2")
        assert "automation_attempts" not in inspect(engine).get_table_names()
        assert "domain_snapshots" in inspect(engine).get_table_names()
        command.upgrade(config, "head")
        assert "automation_attempts" in inspect(engine).get_table_names()
    finally:
        engine.dispose()
        get_settings.cache_clear()


def test_postgresql_ddl_contains_append_only_triggers(monkeypatch):
    # SQL compilation only; not proof of a native PostgreSQL concurrency run.
    monkeypatch.setenv("IDML_DATABASE_URL", "postgresql+psycopg://fixture@localhost/fixture")
    get_settings.cache_clear()
    output = StringIO()
    try:
        command.upgrade(Config("alembic.ini", output_buffer=output), "f7b8c9d0e1f2:head", sql=True)
    finally:
        get_settings.cache_clear()
    ddl = output.getvalue()
    assert "uq_auto_intent" in ddl
    for name in (
        "automation_grants",
        "automation_grant_revocations",
        "automation_attempts",
        "automation_discards",
    ):
        assert f"CREATE TRIGGER immutable_{name} BEFORE UPDATE OR DELETE ON {name}" in ddl
    assert "prevent_autocorrection_history_change" in ddl
