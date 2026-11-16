import copy
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, select, text, update
from sqlalchemy.exc import DatabaseError
from sqlalchemy.orm import sessionmaker

from idml_foundation.database import Base
from idml_foundation.domain.canonical import CanonicalArticle
from idml_foundation.domain.common import content_digest
from idml_foundation.models import (
    CanonicalHeadEvent,
    DomainSnapshot,
    Organization,
    Resource,
    ReviewDecision,
    ReviewItem,
    User,
)
from idml_foundation.pipeline.profile import load_profile
from idml_foundation.pipeline.validation import OfflineJatsValidator
from idml_foundation.schemas import ReviewDecisionCreate
from idml_foundation.services.canonical_heads import (
    current_canonical_snapshot,
    restore_working_head,
)
from idml_foundation.services.reviews import apply_review_decision, claim_review_item
from idml_foundation.services.snapshots import store_snapshot
from idml_foundation.settings import get_settings
from tests.domain_helpers import canonical_article


def draft(label):
    payload = canonical_article().model_dump(mode="json")
    payload["front"]["titles"][0]["text"]["value"] = label
    return CanonicalArticle.model_validate(payload)


def seeded(db):
    org = Organization(slug=f"head-{uuid4()}", name="Synthetic")
    db.add(org)
    db.flush()
    resource = Resource(organization_id=org.id, title="Synthetic")
    db.add(resource)
    db.flush()
    first, _ = store_snapshot(
        db, organization_id=org.id, resource_id=resource.id, document=draft("First"), revision=1
    )
    second, _ = store_snapshot(
        db,
        organization_id=org.id,
        resource_id=resource.id,
        document=draft("Second"),
        revision=2,
        parent_snapshot_id=first.id,
    )
    db.commit()
    return resource, first, second


def restore_args(resource, first, second):
    return dict(
        organization_id=resource.organization_id,
        resource_id=resource.id,
        target_snapshot_id=first.id,
        expected_snapshot_id=second.id,
        expected_resource_version=resource.version,
        request_id=uuid4(),
    )


def head(db, resource):
    return current_canonical_snapshot(
        db, organization_id=resource.organization_id, resource_id=resource.id
    )


def review_item(db, resource, snapshot):
    item = ReviewItem(
        organization_id=resource.organization_id,
        resource_id=resource.id,
        base_snapshot_id=snapshot.id,
        category="semantic",
        rule_code="TITLE",
        field_path="/front/titles/0/text/value",
        message="Check title",
    )
    db.add(item)
    db.flush()
    return item


def reviewer(db):
    user = User(email=f"{uuid4()}@example.test", password_hash="not-a-login-hash")
    db.add(user)
    db.flush()
    return user


def decision(db, resource, item, user, title="Human revision"):
    return apply_review_decision(
        db,
        organization_id=resource.organization_id,
        item_id=item.id,
        user_id=user.id,
        payload=ReviewDecisionCreate(
            expected_version=item.version,
            action="apply_patch",
            patch=({"op": "replace", "path": item.field_path, "value": title},),
            justification="Synthetic explicit human correction",
        ),
        profile=load_profile(),
        validator=OfflineJatsValidator(Path("vendor/jats/1.3")),
    )


def test_restore_moves_head_not_maximum_revision_and_preserves_snapshots(db):
    resource, first, second = seeded(db)
    before = [copy.deepcopy(first.payload), copy.deepcopy(second.payload)]
    args = restore_args(resource, first, second)
    row = restore_working_head(db, **args)
    assert head(db, resource).id == first.id
    assert row.sequence == 3 and row.receipt["action"] == "restore"
    assert row.receipt["requires_revalidation"] and not row.receipt["release_approved"]
    assert resource.version == args["expected_resource_version"] + 1
    assert db.scalar(select(func.count()).select_from(DomainSnapshot)) == 2
    assert [first.payload, second.payload] == before
    assert db.scalar(select(func.max(DomainSnapshot.revision))) == 2


def test_idempotent_restore_replay_never_reapplies_after_new_work(db):
    resource, first, second = seeded(db)
    args = restore_args(resource, first, second)
    row = restore_working_head(db, **args)
    third, _ = store_snapshot(
        db,
        organization_id=resource.organization_id,
        resource_id=resource.id,
        document=draft("Third"),
        revision=3,
        parent_snapshot_id=first.id,
    )
    assert restore_working_head(db, **args).id == row.id
    assert head(db, resource).id == third.id
    with pytest.raises(ValueError, match="request_conflict"):
        restore_working_head(db, **(args | {"target_snapshot_id": second.id}))


@pytest.mark.parametrize(
    "field",
    [
        "organization_id",
        "resource_id",
        "target_snapshot_id",
        "expected_snapshot_id",
        "expected_resource_version",
    ],
)
def test_invalid_or_stale_scope_fails_without_head_change(db, field):
    resource, first, second = seeded(db)
    args = restore_args(resource, first, second)
    args[field] = 100 if field == "expected_resource_version" else str(uuid4())
    with pytest.raises((ValueError, LookupError, RuntimeError)):
        restore_working_head(db, **args)
    assert head(db, resource).id == second.id
    assert db.scalar(select(func.count()).select_from(CanonicalHeadEvent)) == 2


def test_outer_rollback_discards_head_and_version_change(db):
    resource, first, second = seeded(db)
    args = restore_args(resource, first, second)
    restore_working_head(db, **args)
    db.rollback()
    assert head(db, resource).id == second.id
    assert resource.version == args["expected_resource_version"]
    assert db.scalar(select(func.count()).select_from(CanonicalHeadEvent)) == 2


def test_restore_rebases_open_review_and_human_writer_uses_restored_head(db):
    resource, first, second = seeded(db)
    item = review_item(db, resource, second)
    user = reviewer(db)
    restore_working_head(db, **restore_args(resource, first, second))
    db.refresh(item)
    assert item.base_snapshot_id == first.id and item.version == 2
    _, human, build = decision(db, resource, item, user)
    current = head(db, resource)
    assert current.revision == 3 and current.parent_snapshot_id == first.id
    assert human.base_snapshot_id == first.id and build.snapshot_id == current.id
    assert current.payload["front"]["titles"][0]["text"]["value"] == "Human revision"


@pytest.mark.parametrize("human_state", ["claimed", "decision"])
def test_restore_cannot_override_claim_or_human_decision(db, human_state):
    resource, first, second = seeded(db)
    item = review_item(db, resource, second)
    user = reviewer(db)
    if human_state == "claimed":
        claim_review_item(
            db,
            organization_id=resource.organization_id,
            item_id=item.id,
            user_id=user.id,
            expected_version=item.version,
        )
    else:
        _, _, _ = decision(db, resource, item, user)
    current = head(db, resource)
    args = restore_args(resource, first, current)
    with pytest.raises(ValueError, match=r"human_.*protected"):
        restore_working_head(db, **args)
    assert head(db, resource).id == current.id


def test_human_validation_exception_rolls_back_snapshot_head_item_and_decision(db, monkeypatch):
    resource, _, second = seeded(db)
    item = review_item(db, resource, second)
    user = reviewer(db)
    db.commit()
    version = resource.version

    def fail(*args, **kwargs):
        raise RuntimeError("synthetic interruption")

    monkeypatch.setattr(OfflineJatsValidator, "validate", fail)
    with pytest.raises(RuntimeError, match="interruption"):
        decision(db, resource, item, user)
    assert head(db, resource).id == second.id and resource.version == version
    assert item.version == 1 and item.state == "open"
    assert db.scalar(select(func.count()).select_from(ReviewDecision)) == 0
    assert db.scalar(select(func.count()).select_from(DomainSnapshot)) == 2


def test_old_parent_rejected_even_when_revision_is_higher(db):
    resource, first, second = seeded(db)
    with pytest.raises(RuntimeError, match=r"parent.*stale"):
        store_snapshot(
            db,
            organization_id=resource.organization_id,
            resource_id=resource.id,
            document=draft("Stale work"),
            revision=3,
            parent_snapshot_id=first.id,
        )
    assert head(db, resource).id == second.id


def test_duplicate_snapshot_does_not_implicitly_restore(db):
    resource, first, second = seeded(db)
    row, created = store_snapshot(
        db,
        organization_id=resource.organization_id,
        resource_id=resource.id,
        document=draft("First"),
        revision=3,
    )
    assert not created and row.id == first.id and head(db, resource).id == second.id


def test_unregistered_branch_is_not_head_and_cannot_be_restore_target(db):
    resource, first, second = seeded(db)
    branch = DomainSnapshot(
        organization_id=resource.organization_id,
        resource_id=resource.id,
        model_kind="canonical",
        schema_version=first.schema_version,
        revision=100,
        content_sha256=content_digest(draft("Branch")),
        payload=draft("Branch").model_dump(mode="json"),
    )
    db.add(branch)
    db.flush()
    assert head(db, resource).id == second.id
    with pytest.raises(ValueError, match="target_invalid"):
        restore_working_head(
            db, **(restore_args(resource, first, second) | {"target_snapshot_id": branch.id})
        )


@pytest.mark.parametrize("tamper", ["payload", "receipt", "orm_delete", "orm_update"])
def test_tampering_and_history_mutation_refused(db, tamper):
    resource, first, second = seeded(db)
    if tamper == "payload":
        db.execute(
            update(DomainSnapshot)
            .where(DomainSnapshot.id == first.id)
            .values(payload=draft("Changed").model_dump(mode="json"))
        )
        with pytest.raises(ValueError, match="target_invalid"):
            restore_working_head(db, **restore_args(resource, first, second))
    else:
        row = db.scalar(select(CanonicalHeadEvent).order_by(CanonicalHeadEvent.sequence.desc()))
        if tamper == "receipt":
            db.execute(
                update(CanonicalHeadEvent)
                .where(CanonicalHeadEvent.id == row.id)
                .values(receipt_sha256="f" * 64)
            )
            with pytest.raises(ValueError, match="integrity_failure"):
                head(db, resource)
        else:
            if tamper == "orm_delete":
                db.delete(row)
            else:
                row.sequence = 100
            with pytest.raises(ValueError, match="append_only"):
                db.flush()


def test_legacy_fallback_and_first_transition_preserve_old_head(db):
    org = Organization(slug="legacy-head", name="Legacy")
    db.add(org)
    db.flush()
    resource = Resource(organization_id=org.id, title="Legacy")
    db.add(resource)
    db.flush()
    old = DomainSnapshot(
        organization_id=org.id,
        resource_id=resource.id,
        model_kind="canonical",
        schema_version=canonical_article().schema_version,
        revision=1,
        content_sha256=content_digest(draft("First")),
        payload=draft("First").model_dump(mode="json"),
    )
    db.add(old)
    db.flush()
    assert head(db, resource).id == old.id
    assert db.scalar(select(func.count()).select_from(CanonicalHeadEvent)) == 0
    new, _ = store_snapshot(
        db,
        organization_id=org.id,
        resource_id=resource.id,
        document=draft("Second"),
        revision=2,
        parent_snapshot_id=old.id,
    )
    restore_working_head(db, **restore_args(resource, old, new))
    assert head(db, resource).id == old.id


@pytest.mark.parametrize("same_request", [True, False])
def test_two_sessions_restore_once(tmp_path, same_request):
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'heads.sqlite'}", connect_args={"timeout": 20}
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, autoflush=False, expire_on_commit=False)
    try:
        with sessions() as db:
            resource, first, second = seeded(db)
            args = restore_args(resource, first, second)
        barrier = Barrier(2)

        def execute():
            with sessions() as db:
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
            results = [f.result(timeout=30) for f in [pool.submit(execute), pool.submit(execute)]]
        assert (len(set(results)) == 1) if same_request else (results.count("conflict") == 1)
        with sessions() as db:
            assert db.scalar(select(func.count()).select_from(CanonicalHeadEvent)) == 3
            assert head(db, resource).id == first.id
    finally:
        engine.dispose()


def test_migration_guards_and_rollback_no_backfill(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{tmp_path / 'migrated.sqlite'}"
    monkeypatch.setenv("IDML_DATABASE_URL", url)
    monkeypatch.setenv("IDML_ENVIRONMENT", "test")
    get_settings.cache_clear()
    engine = create_engine(url)
    try:
        command.upgrade(Config("alembic.ini"), "head")
        with sessionmaker(engine, expire_on_commit=False)() as db:
            resource, first, second = seeded(db)
            restore_working_head(db, **restore_args(resource, first, second))
            db.rollback()
            assert head(db, resource).id == second.id
        with engine.connect() as connection:
            for sql in (
                "UPDATE canonical_head_events SET sequence=99",
                "DELETE FROM canonical_head_events",
            ):
                with pytest.raises(DatabaseError, match="append_only"):
                    connection.execute(text(sql))
                connection.rollback()
    finally:
        engine.dispose()
        get_settings.cache_clear()
