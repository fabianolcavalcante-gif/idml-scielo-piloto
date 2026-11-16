"""Native isolated PostgreSQL migration/concurrency test; never alters active schema."""

import json
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DatabaseError
from sqlalchemy.orm import sessionmaker

from idml_foundation.autocorrection_models import AutomationRevalidation
from idml_foundation.settings import Settings, get_settings
from tests.autocorrection_helpers import persisted_data
from tests.test_autocorrection_history import save
from tests.test_autocorrection_package import with_package_inputs

NAME = "idml_vh09_20261020_check"


def main():
    url = make_url(os.environ["IDML_DATABASE_URL"])
    if url.get_backend_name() != "postgresql" or url.database == NAME:
        raise RuntimeError("expected_active_postgresql_connection")
    admin = create_engine(url, isolation_level="AUTOCOMMIT")
    created = False
    engine = None
    try:
        with admin.connect() as connection:
            if connection.scalar(text("SELECT 1 FROM pg_database WHERE datname=:n"), {"n": NAME}):
                raise RuntimeError("existing_qualification_database_refused")
            connection.exec_driver_sql(f'CREATE DATABASE "{NAME}"')
            created = True
        test_url = url.set(database=NAME)
        os.environ["IDML_DATABASE_URL"] = test_url.render_as_string(hide_password=False)
        get_settings.cache_clear()
        command.upgrade(Config("alembic.ini"), "head")
        engine = create_engine(test_url)
        sessions = sessionmaker(engine, autoflush=False, expire_on_commit=False)
        with tempfile.TemporaryDirectory(prefix="vh09-pg-") as directory:
            settings = Settings(
                environment="test",
                database_url=test_url.render_as_string(hide_password=False),
                artifact_root=Path(directory),
                artifact_disk_reserve_bytes=1,
                session_pepper="synthetic-qualification-only-32-bytes",
            )
            with sessions() as db:
                data = with_package_inputs(db, persisted_data(db, settings))
            barrier = Barrier(2)
            request = uuid4()

            def execute():
                with sessions() as db:
                    db.execute(text("SET LOCAL lock_timeout = '15s'"))
                    barrier.wait(timeout=10)
                    row = save(db, data, request)
                    db.commit()
                    return row.id

            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(execute) for _ in range(2)]
                ids = [future.result(timeout=40) for future in futures]
            assert ids[0] == ids[1]
            with sessions() as db:
                assert db.scalar(select(func.count()).select_from(AutomationRevalidation)) == 1
                revision = db.scalar(text("SELECT version_num FROM alembic_version"))
                triggers = db.scalar(
                    text(
                        "SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal "
                        "AND tgname LIKE 'immutable_automation_%'"
                    )
                )
                assert revision == "b9d0e1f20314" and triggers == 5
            guards = 0
            with engine.connect() as connection:
                for sql in (
                    "UPDATE automation_revalidations SET request_sha256='tampered' WHERE id=:id",
                    "DELETE FROM automation_revalidations WHERE id=:id",
                ):
                    try:
                        connection.execute(text(sql), {"id": ids[0]})
                    except DatabaseError:
                        guards += 1
                    finally:
                        connection.rollback()
            assert guards == 2
            # Outer rollback must not commit a nested revalidation/history transaction.
            with sessions() as db:
                save(db, data, uuid4())
                db.rollback()
                assert db.scalar(select(func.count()).select_from(AutomationRevalidation)) == 1
        print(
            json.dumps(
                {
                    "passed": True,
                    "migration": revision,
                    "immutable_triggers": triggers,
                    "concurrent_sessions": 2,
                    "persisted_requests": 1,
                    "sql_guards": guards,
                    "outer_rollback": True,
                    "active_database_changed": False,
                    "release_approved": False,
                }
            )
        )
    finally:
        if engine is not None:
            engine.dispose()
        if created:
            with admin.connect() as connection:
                # Exactly the new, isolated DB created by this invocation.
                connection.exec_driver_sql(f'DROP DATABASE "{NAME}"')
        admin.dispose()
        get_settings.cache_clear()


if __name__ == "__main__":
    main()
