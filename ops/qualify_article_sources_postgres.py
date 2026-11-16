"""Disposable PostgreSQL qualification; never authorizes an active article."""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DatabaseError
from sqlalchemy.orm import sessionmaker

from idml_foundation.services.article_source_access import decide, resolve
from idml_foundation.settings import get_settings
from idml_foundation.source_access_models import ArticleSourceDecision
from tests.test_article_source_access import seed


def main():
    settings = get_settings()
    url = make_url(settings.database_url)
    name = "idml_sources_qualification_" + uuid4().hex[:12]
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    engine = None
    created = False
    try:
        with admin.connect() as c:
            c.exec_driver_sql(f'CREATE DATABASE "{name}"')
        created = True
        target = url.set(database=name)
        config = Config("alembic.ini")
        # env.py reads settings, so override the cached settings for this process only.
        original = settings.database_url
        settings.database_url = target.render_as_string(hide_password=False)
        command.upgrade(config, "head")
        engine = create_engine(target)
        sessions = sessionmaker(bind=engine, expire_on_commit=False)
        with TemporaryDirectory() as temp:
            lab = settings.model_copy(
                update=dict(artifact_root=Path(temp), artifact_disk_reserve_bytes=1)
            )
            with sessions() as db:
                _, _, _, request, scope = seed(db, sessions, lab)
            barrier = Barrier(2)

            def attempt(_):
                with sessions() as db:
                    barrier.wait(timeout=15)
                    try:
                        row = decide(db, **(request | {"request_id": str(uuid4())}))
                        db.commit()
                        return row.id
                    except ValueError:
                        db.rollback()
                        return None

            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(attempt, range(2)))
            assert sum(r is not None for r in results) == 1
            with sessions() as db:
                assert db.scalar(select(func.count()).select_from(ArticleSourceDecision)) == 1
                assert resolve(db, scope)["decision_id"] in results
                decide(
                    db,
                    **(
                        request
                        | dict(request_id=str(uuid4()), expected_sequence=1, action="revoke")
                    ),
                )
                db.rollback()
                assert resolve(db, scope)["decision_id"] in results
                decide(
                    db,
                    **(
                        request
                        | dict(request_id=str(uuid4()), expected_sequence=1, action="revoke")
                    ),
                )
                db.commit()
                try:
                    resolve(db, scope)
                except ValueError:
                    pass
                else:
                    raise AssertionError("revoked decision accepted")
            guards = 0
            for statement in [
                "UPDATE article_source_decisions SET sequence=99",
                "DELETE FROM article_source_decisions",
            ]:
                try:
                    with engine.begin() as connection:
                        connection.execute(text(statement))
                except DatabaseError:
                    guards += 1
            assert guards == 2
            with engine.connect() as connection:
                assert (
                    connection.scalar(text("select version_num from alembic_version"))
                    == "e2f314253647"
                )
            print(
                json.dumps(
                    dict(
                        passed=True,
                        concurrent_decisions_one_conflict=True,
                        outer_rollback=True,
                        revocation_enforced=True,
                        sql_guards=guards,
                        active_database_changed=False,
                        ai_invoked=False,
                    )
                )
            )
        settings.database_url = original
    finally:
        if engine is not None:
            engine.dispose()
        if created:
            with admin.connect() as c:
                c.exec_driver_sql(f'DROP DATABASE "{name}"')
        admin.dispose()
        get_settings.cache_clear()


if __name__ == "__main__":
    main()
