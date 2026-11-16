"""Restore/validation races and additive migration in a disposable PostgreSQL DB."""

import json
import os
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

from idml_foundation.models import Resource
from idml_foundation.restoration_models import RestoredPackageValidation
from idml_foundation.services.canonical_heads import restore_working_head
from idml_foundation.services.reviews import claim_review_item
from idml_foundation.settings import get_settings
from tests.test_canonical_heads import review_item, reviewer
from tests.test_restored_package_validation import head, prepare, restore, revalidate

NAME = "idml_vh09_restored_20261029_check"


def main():
    url = make_url(os.environ["IDML_DATABASE_URL"])
    if url.get_backend_name() != "postgresql" or url.database == NAME:
        raise RuntimeError("expected_active_postgresql_connection")
    admin = create_engine(url, isolation_level="AUTOCOMMIT")
    engine = None
    created = False
    try:
        with admin.connect() as connection:
            if connection.scalar(text("SELECT 1 FROM pg_database WHERE datname=:n"), {"n": NAME}):
                raise RuntimeError("existing_qualification_database_refused")
            connection.exec_driver_sql(f'CREATE DATABASE "{NAME}"')
            created = True
        test_url = url.set(database=NAME)
        os.environ["IDML_DATABASE_URL"] = test_url.render_as_string(hide_password=False)
        get_settings.cache_clear()
        command.upgrade(Config("alembic.ini"), "c0e1f2031425")
        engine = create_engine(test_url)
        sessions = sessionmaker(engine, autoflush=False, expire_on_commit=False)
        with TemporaryDirectory(prefix="idml-restored-") as folder:
            settings = get_settings().model_copy(
                update={
                    "artifact_root": Path(folder),
                    "artifact_disk_reserve_bytes": 1,
                }
            )
            with sessions() as db:
                data = prepare(db, settings)
            command.upgrade(Config("alembic.ini"), "head")
            with sessions() as db:
                assert head(db, data).id == data["later"].id
                assert db.scalar(select(func.count()).select_from(RestoredPackageValidation)) == 0

            def move_back():
                with sessions() as db:
                    resource = db.get(Resource, data["target"].resource_id)
                    restore_working_head(
                        db,
                        organization_id=resource.organization_id,
                        resource_id=resource.id,
                        target_snapshot_id=data["later"].id,
                        expected_snapshot_id=data["target"].id,
                        expected_resource_version=resource.version,
                        request_id=uuid4(),
                    )
                    db.commit()
                    data["restore_args"]["expected_resource_version"] = resource.version

            for same_request in (True, False):
                request = uuid4()
                barrier = Barrier(2)

                def execute(request=request, barrier=barrier, same_request=same_request):
                    with sessions() as db:
                        db.execute(text("SET LOCAL lock_timeout = '15s'"))
                        barrier.wait(timeout=10)
                        try:
                            record = restore(db, data, request if same_request else uuid4())
                            db.commit()
                            return record.id
                        except RuntimeError as exc:
                            assert "canonical_head_version_conflict" in str(exc)
                            db.rollback()
                            return "conflict"

                with ThreadPoolExecutor(max_workers=2) as pool:
                    futures = [pool.submit(execute), pool.submit(execute)]
                    ids = [future.result(timeout=40) for future in futures]
                if same_request:
                    assert ids[0] == ids[1] and "conflict" not in ids
                else:
                    assert ids.count("conflict") == 1
                with sessions() as db:
                    assert head(db, data).id == data["target"].id
                    assert db.scalar(
                        select(func.count()).select_from(RestoredPackageValidation)
                    ) == (1 if same_request else 2)
                move_back()
            with sessions() as db:
                restore(db, data)
                db.rollback()
                assert head(db, data).id == data["later"].id
                assert db.scalar(select(func.count()).select_from(RestoredPackageValidation)) == 2
                record = restore(db, data)
                db.commit()
                resource = db.get(Resource, record.resource_id)
                item = review_item(db, resource, data["target"])
                user = reviewer(db)
                db.commit()
            with sessions() as human, sessions() as automatic:
                claim_review_item(
                    human,
                    organization_id=resource.organization_id,
                    item_id=item.id,
                    user_id=user.id,
                    expected_version=1,
                )
                automatic.execute(text("SET LOCAL lock_timeout = '500ms'"))
                try:
                    revalidate(automatic, data, record)
                except DatabaseError as exc:
                    assert getattr(exc.orig, "sqlstate", None) == "55P03"
                    automatic.rollback()
                else:
                    raise AssertionError("human_lock_not_enforced")
                human.commit()
                try:
                    revalidate(automatic, data, record)
                except ValueError as exc:
                    assert "human_work_protected" in str(exc)
                    automatic.rollback()
                else:
                    raise AssertionError("human_claim_not_protected")
            guards = 0
            with engine.connect() as connection:
                for sql in (
                    "UPDATE restored_package_validations SET request_sha256='changed'",
                    "DELETE FROM restored_package_validations",
                ):
                    try:
                        connection.execute(text(sql))
                    except DatabaseError as exc:
                        assert "autocorrection_history_is_append_only" in str(exc.orig)
                        guards += 1
                    finally:
                        connection.rollback()
            assert guards == 2
            command.downgrade(Config("alembic.ini"), "c0e1f2031425")
            command.upgrade(Config("alembic.ini"), "head")
            with sessions() as db:
                assert head(db, data).id == data["target"].id
                assert db.scalar(text("SELECT version_num FROM alembic_version")) == "d1f203142536"
            print(
                json.dumps(
                    dict(
                        passed=True,
                        additive_migration_no_backfill=True,
                        downgrade_upgrade_preserves_heads=True,
                        same_request_one_restore_and_record=True,
                        distinct_requests_one_conflict=True,
                        outer_rollback=True,
                        human_claim_lock_and_refusal=True,
                        sql_guards=guards,
                        synthetic_validators=True,
                        active_database_changed=False,
                        release_approved=False,
                    )
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
