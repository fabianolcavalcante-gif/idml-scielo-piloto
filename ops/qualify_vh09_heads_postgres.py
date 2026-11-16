"""Isolated native working-head migration and human/restore race qualification."""

import json
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DatabaseError
from sqlalchemy.orm import sessionmaker

from idml_foundation.models import CanonicalHeadEvent
from idml_foundation.services.canonical_heads import restore_working_head
from idml_foundation.services.reviews import claim_review_item
from idml_foundation.settings import get_settings
from tests.test_canonical_heads import head, restore_args, review_item, reviewer, seeded

NAME = "idml_vh09_heads_20261021_check"


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
        for same_request in (True, False):
            with sessions() as db:
                resource, first, second = seeded(db)
                args = restore_args(resource, first, second)
            barrier = Barrier(2)

            def execute(barrier=barrier, args=args, same_request=same_request):
                with sessions() as db:
                    db.execute(text("SET LOCAL lock_timeout = '10s'"))
                    barrier.wait(timeout=10)
                    try:
                        row = restore_working_head(
                            db, **(args if same_request else args | {"request_id": uuid4()})
                        )
                        db.commit()
                        return row.id
                    except RuntimeError as exc:
                        assert "version_conflict" in str(exc)
                        db.rollback()
                        return "conflict"

            with ThreadPoolExecutor(max_workers=2) as pool:
                pending = [pool.submit(execute), pool.submit(execute)]
                results = [f.result(timeout=30) for f in pending]
            if same_request:
                assert len(set(results)) == 1
            else:
                assert results.count("conflict") == 1
            with sessions() as db:
                assert head(db, resource).id == first.id
                assert (
                    db.scalar(
                        select(func.count())
                        .select_from(CanonicalHeadEvent)
                        .where(CanonicalHeadEvent.resource_id == resource.id)
                    )
                    == 3
                )
        with sessions() as db:
            resource, first, second = seeded(db)
            item = review_item(db, resource, second)
            user = reviewer(db)
            db.commit()
            args = restore_args(resource, first, second)
        # A human claim holds the same resource lock used by restoration/promotion.
        with sessions() as human, sessions() as automatic:
            assert (
                claim_review_item(
                    human,
                    organization_id=resource.organization_id,
                    item_id=item.id,
                    user_id=user.id,
                    expected_version=1,
                )
                is not None
            )
            automatic.execute(text("SET LOCAL lock_timeout = '500ms'"))
            try:
                restore_working_head(automatic, **args)
            except DatabaseError as exc:
                assert getattr(exc.orig, "sqlstate", None) == "55P03"
                automatic.rollback()
            else:
                raise AssertionError("human_resource_lock_not_enforced")
            human.commit()
            try:
                restore_working_head(automatic, **args)
            except ValueError as exc:
                assert "human_claim_protected" in str(exc)
                automatic.rollback()
            else:
                raise AssertionError("human_claim_not_protected")
        with sessions() as db:
            resource, first, second = seeded(db)
            restore_working_head(db, **restore_args(resource, first, second))
            db.rollback()
            assert head(db, resource).id == second.id
            revision = db.scalar(text("SELECT version_num FROM alembic_version"))
            assert revision == "c0e1f2031425"
        guards = 0
        with engine.connect() as connection:
            for sql in (
                "UPDATE canonical_head_events SET sequence=99",
                "DELETE FROM canonical_head_events",
            ):
                try:
                    connection.execute(text(sql))
                except DatabaseError as exc:
                    assert "autocorrection_history_is_append_only" in str(exc.orig)
                    guards += 1
                finally:
                    connection.rollback()
        assert guards == 2
        print(
            json.dumps(
                {
                    "passed": True,
                    "migration": revision,
                    "concurrent_sessions": 2,
                    "same_request_single_restore": True,
                    "different_requests_one_conflict": True,
                    "human_claim_lock_timeout_verified": True,
                    "human_claim_refused_after_commit": True,
                    "outer_rollback": True,
                    "sql_guards": guards,
                    "active_database_changed": False,
                    "promotion_implemented": False,
                    "release_approved": False,
                }
            )
        )
    finally:
        if engine is not None:
            engine.dispose()
        if created:
            with admin.connect() as connection:
                connection.exec_driver_sql(f'DROP DATABASE "{NAME}"')
        admin.dispose()
        get_settings.cache_clear()


if __name__ == "__main__":
    main()
