"""Restoration transaction fixtures are synthetic; they do not approve real XML."""

import copy
from datetime import timedelta
from io import BytesIO
from uuid import uuid4
from zipfile import ZipFile

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, select, text, update
from sqlalchemy.exc import DatabaseError
from sqlalchemy.orm import sessionmaker

from idml_foundation.domain.canonical import CanonicalArticle
from idml_foundation.models import (
    Artifact,
    CanonicalHeadEvent,
    DomainSnapshot,
    Resource,
    ReviewItem,
)
from idml_foundation.restoration_models import RestoredPackageValidation
from idml_foundation.services.artifacts import read_artifact_bytes
from idml_foundation.services.canonical_heads import restore_working_head
from idml_foundation.services.restored_package_validation import (
    read_restored_validation,
    restore_and_revalidate_package,
    revalidate_restored_package,
)
from idml_foundation.services.snapshots import store_snapshot
from idml_foundation.settings import get_settings
from tests.autocorrection_helpers import persisted_data
from tests.test_autocorrection_package import with_package_inputs
from tests.test_autocorrection_promotion import arguments, head, promote
from tests.test_package_formal_validation import completed
from tests.test_xpm_execution import execution


def prepare(db, settings):
    data = with_package_inputs(db, persisted_data(db, settings))
    promote(db, data)
    db.commit()
    target = head(db, data)
    article = CanonicalArticle.model_validate(target.payload)
    raw = article.model_dump(mode="json")
    raw["front"]["titles"][0]["text"]["value"] = "Later synthetic draft"
    later, _ = store_snapshot(
        db,
        organization_id=target.organization_id,
        resource_id=target.resource_id,
        document=CanonicalArticle.model_validate(raw),
        revision=target.revision + 1,
        source_artifact_id=target.source_artifact_id,
        parent_snapshot_id=target.id,
    )
    db.commit()
    data.update(target=target, later=later)
    data["restore_args"] = dict(
        organization_id=target.organization_id,
        resource_id=target.resource_id,
        target_snapshot_id=target.id,
        expected_snapshot_id=later.id,
        expected_resource_version=db.get(Resource, target.resource_id).version,
    )
    return data


@pytest.fixture
def data(db, settings):
    return prepare(db, settings)


def dependencies(data):
    args = arguments(data)
    return {
        key: args[key]
        for key in (
            "pdf_artifact_id",
            "pdf_sha256",
            "profile",
            "settings",
            "validator",
            "executor",
            "xpm_executor",
            "clock",
        )
    }


def restore(db, data, request=None, **overrides):
    return restore_and_revalidate_package(
        db,
        request_id=request or uuid4(),
        **(data["restore_args"] | dependencies(data) | overrides),
    )


def revalidate(db, data, row, **overrides):
    return revalidate_restored_package(
        db,
        **(
            dict(
                organization_id=row.organization_id,
                resource_id=row.resource_id,
                restore_event_id=row.restore_event_id,
                expected_resource_version=row.receipt["binding"]["resource_version"],
                request_id=uuid4(),
            )
            | dependencies(data)
            | overrides
        ),
    )


def test_restore_rebuilds_exact_target_with_new_reports_and_no_inherited_approval(db, data):
    seen = []

    def execute(payload, spec):
        seen.append((spec.name, payload))
        return completed(payload, spec)

    row = restore(db, data, executor=execute)
    db.commit()
    assert [name for name, _ in seen] == ["packtools", "spsvalidator"]
    assert head(db, data).id == data["target"].id
    assert row.snapshot_id == data["target"].id and row.snapshot_id != data["later"].id
    assert row.receipt["state"] == "revalidated-working-draft"
    assert row.receipt["historical_evidence_only"]
    assert not row.receipt["approval_inherited"] and not row.receipt["release_approved"]
    xml = read_artifact_bytes(db.get(Artifact, row.xml_artifact_id), data["settings"])
    package = read_artifact_bytes(db.get(Artifact, row.package_artifact_id), data["settings"])
    assert seen == [("packtools", xml), ("spsvalidator", package)]
    assert b"Later synthetic draft" not in xml
    with ZipFile(BytesIO(package)) as archive:
        assert next(archive.read(n) for n in archive.namelist() if n.endswith(".xml")) == xml
        assert next(archive.read(n) for n in archive.namelist() if n.endswith(".pdf")).startswith(
            b"%PDF-"
        )
    assert db.scalar(select(func.count()).select_from(DomainSnapshot)) == 3
    event = db.get(CanonicalHeadEvent, row.restore_event_id)
    assert event.receipt["requires_revalidation"] and not event.receipt["release_approved"]


def test_request_replay_after_later_transition_is_history_without_work_or_head_change(db, data):
    request = uuid4()
    row = restore(db, data, request)
    db.commit()
    restore_working_head(
        db,
        organization_id=row.organization_id,
        resource_id=row.resource_id,
        target_snapshot_id=data["later"].id,
        expected_snapshot_id=data["target"].id,
        expected_resource_version=db.get(Resource, row.resource_id).version,
        request_id=uuid4(),
    )
    db.commit()
    calls = []
    assert restore(db, data, request, executor=lambda *a: calls.append(a)).id == row.id
    assert not calls and head(db, data).id == data["later"].id
    with pytest.raises(ValueError, match="head_changed"):
        revalidate(db, data, row)


def test_new_request_revalidates_identical_restored_bytes_without_new_head(db, data):
    first = restore(db, data)
    db.commit()
    version = db.get(Resource, first.resource_id).version
    calls = []

    def execute(payload, spec):
        calls.append(spec.name)
        return completed(payload, spec)

    second = revalidate(db, data, first, executor=execute)
    assert second.id != first.id and second.request_id != first.request_id
    assert second.xml_artifact_id == first.xml_artifact_id
    assert second.package_artifact_id == first.package_artifact_id
    assert calls == ["packtools", "spsvalidator"]
    assert db.get(Resource, first.resource_id).version == version


@pytest.mark.parametrize(
    "change", ["offline", "offline_exception", "offline_wrong_hash", "modern", "xpm", "xpm_error"]
)
def test_failed_or_missing_validation_is_saved_blocked_without_approval(db, data, change):
    calls = []
    args = {}
    if change == "offline":
        args["validator"] = data["validator"]  # Real DTD: minimal fixture is invalid.
    elif change.startswith("offline_"):

        class Broken:
            def validate(self, xml, **kwargs):
                if change == "offline_exception":
                    raise RuntimeError("synthetic-secret-must-not-leak")
                return (
                    dependencies(data)["validator"]
                    .validate(xml, **kwargs)
                    .model_copy(update={"xml_sha256": "0" * 64})
                )

        args["validator"] = Broken()
    elif change == "modern":
        args["executor"] = None
    elif change == "xpm":
        args["xpm_executor"] = None
    else:
        args["xpm_executor"] = lambda p, s: execution(p, s, errors=1)
    if change.startswith("offline"):
        args["executor"] = lambda *a: calls.append(a)
        args["xpm_executor"] = lambda *a: calls.append(a)
    row = restore(db, data, **args)
    assert row.receipt["state"] == "blocked" and not calls
    assert not row.receipt["draft_admission"]["eligible"]
    assert "synthetic-secret" not in str(row.reports)
    assert head(db, data).id == data["target"].id


def test_warnings_remain_pending(db, data):
    row = restore(db, data, xpm_executor=lambda p, s: execution(p, s, warnings=1))
    assert row.receipt["draft_admission"]["pending_review"] == ["xpm-warnings-review"]
    assert not row.receipt["draft_admission"]["warnings_accepted"]


def test_outer_rollback_reverts_head_and_evidence_then_retry_succeeds(db, data):
    request = uuid4()
    row = restore(db, data, request)
    identity = row.id
    db.rollback()
    assert head(db, data).id == data["later"].id
    assert db.scalar(select(func.count()).select_from(RestoredPackageValidation)) == 0
    assert restore(db, data, request).id != identity


@pytest.mark.parametrize(
    "change",
    [
        "pdf_hash",
        "pdf_tenant",
        "profile",
        "clock_naive",
        "clock_reverse",
        "source_bytes",
        "asset_bytes",
        "pdf_bytes",
        "limit",
    ],
)
def test_invalid_inputs_fail_atomically_without_leaving_restore(db, data, change):
    args = {}
    if change == "pdf_hash":
        args["pdf_sha256"] = "0" * 64
    elif change == "pdf_tenant":
        args["pdf_artifact_id"] = str(uuid4())
    elif change == "profile":
        args["profile"] = data["profile"].model_copy(update={"profile_id": "wrong"})
    elif change == "clock_naive":
        args["clock"] = lambda: data["now"].replace(tzinfo=None)
    elif change == "clock_reverse":
        ticks = iter([data["now"], data["now"] - timedelta(seconds=1)])
        args["clock"] = lambda: next(ticks)
    elif change == "limit":
        args["settings"] = dependencies(data)["settings"].model_copy(
            update={"upload_max_bytes": 10}
        )
    else:
        if change == "source_bytes":
            artifact = db.get(Artifact, data["target"].source_artifact_id)
        elif change == "pdf_bytes":
            artifact = data["pdf"]
        else:
            artifact = db.scalar(select(Artifact).where(Artifact.media_type == "image/jpeg"))
        path = data["settings"].artifact_root / artifact.storage_key
        path.write_bytes(path.read_bytes() + b"tampered")
    with pytest.raises((ValueError, RuntimeError)):
        restore(db, data, **args)
    assert head(db, data).id == data["later"].id
    assert db.scalar(select(func.count()).select_from(RestoredPackageValidation)) == 0


@pytest.mark.parametrize("change", ["source", "asset", "pdf", "head", "human"])
def test_state_changed_during_external_validation_cannot_persist_evidence(db, data, change):
    called = False

    def execute(payload, spec):
        nonlocal called
        if not called:
            called = True
            if change == "head":
                db.get(Resource, data["target"].resource_id).version += 1
                db.flush()
            elif change == "human":
                db.add(
                    ReviewItem(
                        organization_id=data["target"].organization_id,
                        resource_id=data["target"].resource_id,
                        base_snapshot_id=data["target"].id,
                        state="claimed",
                        field_path="/front/title",
                        category="semantic",
                        rule_code="human",
                        message="Check",
                    )
                )
                db.flush()
            else:
                artifact = (
                    data["pdf"]
                    if change == "pdf"
                    else db.get(Artifact, data["target"].source_artifact_id)
                    if change == "source"
                    else db.scalar(select(Artifact).where(Artifact.media_type == "image/jpeg"))
                )
                path = data["settings"].artifact_root / artifact.storage_key
                path.write_bytes(path.read_bytes() + b"changed")
        return completed(payload, spec)

    with pytest.raises(ValueError):
        restore(db, data, executor=execute)
    assert head(db, data).id == data["later"].id
    assert db.scalar(select(func.count()).select_from(RestoredPackageValidation)) == 0


def test_scope_request_conflict_and_human_claim_are_protected(db, data):
    with pytest.raises(LookupError):
        restore(db, data, organization_id=str(uuid4()))
    request = uuid4()
    row = restore(db, data, request)
    db.commit()
    with pytest.raises(ValueError, match="request_conflict"):
        restore(db, data, request, pdf_sha256="f" * 64)
    with pytest.raises(LookupError):
        read_restored_validation(
            db, organization_id=str(uuid4()), record_id=row.id, settings=data["settings"]
        )
    db.add(
        ReviewItem(
            organization_id=row.organization_id,
            resource_id=row.resource_id,
            base_snapshot_id=row.snapshot_id,
            state="claimed",
            category="semantic",
            rule_code="human",
            message="check",
            field_path="/front/title",
        )
    )
    db.flush()
    with pytest.raises(ValueError, match="human_work_protected"):
        revalidate(db, data, row)


@pytest.mark.parametrize("change", ["receipt", "reports", "xml", "package", "tenant_key"])
def test_private_history_detects_tampering(db, data, change):
    row = restore(db, data)
    db.commit()
    if change in {"receipt", "reports"}:
        payload = copy.deepcopy(getattr(row, change))
        payload["tamper"] = True
        db.execute(
            update(RestoredPackageValidation)
            .where(RestoredPackageValidation.id == row.id)
            .values(**{change: payload})
        )
    else:
        artifact = db.get(
            Artifact, row.package_artifact_id if change == "package" else row.xml_artifact_id
        )
        if change == "tenant_key":
            db.execute(
                update(Artifact)
                .where(Artifact.id == artifact.id)
                .values(storage_key=f"{uuid4()}/invalid")
            )
        else:
            path = data["settings"].artifact_root / artifact.storage_key
            path.write_bytes(path.read_bytes() + b"bad")
    with pytest.raises(ValueError, match="restored_validation_"):
        read_restored_validation(
            db, organization_id=row.organization_id, record_id=row.id, settings=data["settings"]
        )


def test_orm_history_is_immutable(db, data):
    row = restore(db, data)
    db.commit()
    row.request_sha256 = "f" * 64
    with pytest.raises(ValueError, match="append_only"):
        db.flush()


def test_restore_missing_figure_link_never_guesses_mapping(db, data):
    with pytest.raises(ValueError, match="exact_asset_mapping"):
        restore(db, data, target_snapshot_id=data["snapshot"].id)
    assert head(db, data).id == data["later"].id
    assert db.scalar(select(func.count()).select_from(RestoredPackageValidation)) == 0


def test_sqlite_migration_guards_and_rollback(tmp_path, settings, monkeypatch):
    url = f"sqlite+pysqlite:///{tmp_path / 'restore.sqlite'}"
    monkeypatch.setenv("IDML_DATABASE_URL", url)
    monkeypatch.setenv("IDML_ENVIRONMENT", "test")
    get_settings.cache_clear()
    engine = create_engine(url)
    try:
        command.upgrade(Config("alembic.ini"), "c0e1f2031425")
        with sessionmaker(engine, expire_on_commit=False)() as db:
            data = prepare(db, settings)
        command.upgrade(Config("alembic.ini"), "head")
        with sessionmaker(engine, expire_on_commit=False)() as db:
            assert head(db, data).id == data["later"].id
            assert db.scalar(select(func.count()).select_from(RestoredPackageValidation)) == 0
            restore(db, data)
            db.rollback()
            assert head(db, data).id == data["later"].id
            restore(db, data)
            db.commit()
        with engine.connect() as connection:
            for sql in [
                "UPDATE restored_package_validations SET request_sha256='bad'",
                "DELETE FROM restored_package_validations",
            ]:
                with pytest.raises(DatabaseError, match="append_only"):
                    connection.execute(text(sql))
                connection.rollback()
        command.downgrade(Config("alembic.ini"), "c0e1f2031425")
        command.upgrade(Config("alembic.ini"), "head")
    finally:
        engine.dispose()
        get_settings.cache_clear()
