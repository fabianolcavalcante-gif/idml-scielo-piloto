"""Promotion races in an isolated PostgreSQL database with synthetic validators."""

import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DatabaseError
from sqlalchemy.orm import sessionmaker

from idml_foundation.autocorrection_models import AutomationRevalidation
from idml_foundation.models import Organization, Resource
from idml_foundation.services.reviews import claim_review_item
from idml_foundation.settings import get_settings
from tests.autocorrection_helpers import persisted_data, source_data
from tests.test_autocorrection_package import with_package_inputs
from tests.test_autocorrection_promotion import head, promote
from tests.test_canonical_heads import review_item, reviewer

NAME = "idml_vh09_promotion_20261029_check"


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
        with TemporaryDirectory(prefix="idml-promotion-") as temporary:
            settings = get_settings().model_copy(
                update={
                    "artifact_root": Path(temporary),
                    "artifact_disk_reserve_bytes": 1,
                }
            )

            def seed(db):
                fixture = source_data()
                scope = fixture["context"].scope.model_copy(
                    update={"organization_id": uuid4(), "resource_id": uuid4()}
                )
                fixture["context"] = fixture["context"].model_copy(update={"scope": scope})
                fixture["intent"] = fixture["intent"].model_copy(
                    update={"scope": scope, "proposal_id": uuid4()}
                )
                fixture["grants"] = tuple(
                    grant.model_copy(update={"scope": scope, "authorization_id": uuid4()})
                    for grant in fixture["grants"]
                )
                with patch("tests.autocorrection_helpers.source_data", return_value=fixture):
                    data = persisted_data(db, settings)
                org = db.get(Organization, str(data["context"].scope.organization_id))
                org.slug = "promotion-" + str(uuid4())
                db.commit()
                return with_package_inputs(db, data)

            for same_request in (True, False):
                with sessions() as db:
                    data = seed(db)
                request = uuid4()
                barrier = Barrier(2)

                def execute(data=data, request=request, barrier=barrier, same_request=same_request):
                    with sessions() as db:
                        db.execute(text("SET LOCAL lock_timeout = '10s'"))
                        barrier.wait(timeout=10)
                        try:
                            result = promote(db, data, request if same_request else uuid4())
                            db.commit()
                            assert result["decision"]["eligible"]
                            return result["event_id"], result["applied_now"]
                        except ValueError as exc:
                            assert "stale_snapshot_or_revision" in str(exc)
                            db.rollback()
                            return "conflict", False

                with ThreadPoolExecutor(max_workers=2) as pool:
                    futures = [pool.submit(execute), pool.submit(execute)]
                    results = [f.result(timeout=30) for f in futures]
                assert sum(applied for _, applied in results) == 1
                if same_request:
                    assert len({identity for identity, _ in results}) == 1
                else:
                    assert sum(identity == "conflict" for identity, _ in results) == 1
                with sessions() as db:
                    assert head(db, data).id != data["snapshot"].id
                    assert (
                        db.scalar(
                            select(func.count())
                            .select_from(AutomationRevalidation)
                            .where(
                                AutomationRevalidation.resource_id
                                == str(data["context"].scope.resource_id)
                            )
                        )
                        == 1
                    )
            with sessions() as db:
                data = seed(db)
                resource = db.get(Resource, str(data["context"].scope.resource_id))
                item = review_item(db, resource, data["snapshot"])
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
                    promote(automatic, data)
                except DatabaseError as exc:
                    assert getattr(exc.orig, "sqlstate", None) == "55P03"
                    automatic.rollback()
                else:
                    raise AssertionError("human_lock_not_enforced")
                human.commit()
                try:
                    promote(automatic, data)
                except ValueError as exc:
                    assert "human_work_protected" in str(exc)
                    automatic.rollback()
                else:
                    raise AssertionError("human_claim_not_protected")
            with sessions() as db:
                data = seed(db)
                assert promote(db, data)["applied_now"]
                db.rollback()
                assert head(db, data).id == data["snapshot"].id
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
                    dict(
                        passed=True,
                        same_request_single_promotion=True,
                        different_requests_one_conflict=True,
                        human_claim_lock_timeout_verified=True,
                        human_claim_refused_after_commit=True,
                        outer_rollback=True,
                        sql_guards=guards,
                        active_database_changed=False,
                        synthetic_validation=True,
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
