from uuid import uuid4

import pytest
from fastapi import HTTPException

from idml_foundation.models import Artifact, Job
from idml_foundation.rbac import Role, TenantContext
from idml_foundation.routers.edit_evaluations import input_workspace
from idml_foundation.services.snapshots import store_snapshot
from tests.test_canonical_heads import draft, reviewer, seeded


def file(db, org, media, name):
    row = Artifact(
        organization_id=org,
        media_type=media,
        original_name=name,
        scanner_status="clamav_clean",
        sha256=uuid4().hex * 2,
        storage_key=uuid4().hex,
        size_bytes=100,
    )
    db.add(row)
    db.flush()
    return row.id


def test_named_inputs_bind_exact_revision_and_hide_unrelated_files(db):
    article, _, baseline = seeded(db)
    org = article.organization_id
    source = file(db, org, "application/vnd.adobe.indesign-idml-package", "texto.idml")
    pdf = file(db, org, "application/pdf", "prova.pdf")
    extra = file(db, org, "application/pdf", "prova.pdf")
    args = dict(organization_id=org, resource_id=article.id, source_artifact_id=source)
    first, _ = store_snapshot(
        db, **args, document=draft("With source"), revision=3, parent_snapshot_id=baseline.id
    )
    second, _ = store_snapshot(
        db, **args, document=draft("Current"), revision=4, parent_snapshot_id=first.id
    )
    db.add(
        Job(
            organization_id=org,
            kind="scielo.package",
            state="succeeded",
            idempotency_key=uuid4().hex,
            payload=dict(
                resource_id=article.id,
                canonical_snapshot_id=first.id,
                idml_artifact_id=source,
                pdf_artifact_id=pdf,
            ),
            result=dict(package_artifact_id="download"),
        )
    )
    db.flush()
    user = reviewer(db)
    read = TenantContext(user, org, Role.REVIEWER)
    op = TenantContext(user, org, Role.OPERATOR)
    history = input_workspace(article.id, db, read, first.id)
    assert not history["can_start"] and history["package_artifact"] == "download"
    assert history["pdf"] == pdf and {f["id"] for f in history["files"]} == {source, pdf}
    current = input_workspace(article.id, db, op)
    assert current["selected"] == second.id and current["pdf"] is None
    assert current["can_start"] and {f["id"] for f in current["files"]} == {source, pdf, extra}
    db.get(Artifact, extra).scanner_status = "malware_detected"
    db.flush()
    assert extra not in {f["id"] for f in input_workspace(article.id, db, op)["files"]}


def test_named_input_workspace_rejects_foreign_revision_and_article(db):
    a, _, _ = seeded(db)
    b, foreign, _ = seeded(db)
    context = TenantContext(reviewer(db), a.organization_id, Role.OPERATOR)
    for article, revision in [(a.id, foreign.id), (b.id, None)]:
        with pytest.raises(HTTPException) as rejected:
            input_workspace(article, db, context, revision)
        assert rejected.value.status_code == 404
