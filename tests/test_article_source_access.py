from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from idml_foundation.models import AuditEvent, Membership, Organization
from idml_foundation.rbac import Role
from idml_foundation.services import article_source_access as access
from idml_foundation.services.canonical_heads import current_canonical_snapshot
from idml_foundation.source_access_models import ArticleSourceDecision
from tests.test_phase5_review_ui import _headers, _token, _user
from tests.test_worker_xpm_integration import configured, queued


def seed(db, factory, settings):
    job, source = queued(db, factory, configured(settings))
    org = db.get(Organization, job.organization_id)
    user = _user(db, org, "source-admin-" + uuid4().hex + "@example.test", Role.ORG_ADMIN)
    db.commit()
    request = dict(
        organization_id=org.id,
        resource_id=job.payload["resource_id"],
        actor_id=user.id,
        request_id=str(uuid4()),
        expected_sequence=0,
        action="grant",
        days=7,
        correlation_id="source-test",
    )
    scope = dict(
        organization_id=org.id,
        resource_id=job.payload["resource_id"],
        source_idml_sha256=source.sha256,
        journal_profile_id=access.PROFILE,
        xml_sha256="a" * 64,
        package_sha256="b" * 64,
    )
    return org, user, source, request, scope


@pytest.fixture
def data(db, session_factory, settings):
    return seed(db, session_factory, settings)


def test_grant_revoke_and_replay_do_not_reauthorize(db, data):
    _, _, _, request, scope = data
    first = access.decide(db, **request)
    assert access.resolve(db, scope)["decision_id"] == first.id
    revoked = access.decide(
        db, **(request | dict(request_id=str(uuid4()), action="revoke", expected_sequence=1))
    )
    assert revoked.sequence == 2
    assert access.decide(db, **request).id == first.id
    with pytest.raises(ValueError, match="inactive"):
        access.resolve(db, scope)
    assert db.scalar(select(func.count()).select_from(ArticleSourceDecision)) == 2
    assert (
        db.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action.like("article.sources.%"))
        )
        == 2
    )
    renewed = access.decide(db, **(request | dict(request_id=str(uuid4()), expected_sequence=2)))
    assert access.resolve(db, scope)["decision_id"] == renewed.id


@pytest.mark.parametrize(
    "field", ["organization_id", "resource_id", "source_idml_sha256", "journal_profile_id"]
)
def test_consent_never_crosses_scope(db, data, field):
    *_, request, scope = data
    access.decide(db, **request)
    scope[field] = (
        str(uuid4())
        if field in {"organization_id", "resource_id"}
        else "f" * 64
        if field.endswith("sha256")
        else "unqualified"
    )
    with pytest.raises(ValueError):
        access.resolve(db, scope)


@pytest.mark.parametrize(
    "change",
    [
        "expired",
        "user_disabled",
        "org_disabled",
        "role",
        "membership",
        "source",
        "corrupt_snapshot",
    ],
)
def test_lapsed_or_changed_authority_is_refused(db, data, monkeypatch, change):
    org, user, source, request, scope = data
    access.decide(db, **request)
    if change == "expired":

        class Future(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime.now(UTC) + timedelta(days=8)

        monkeypatch.setattr(access, "datetime", Future)
    elif change == "user_disabled":
        user.is_active = False
    elif change == "org_disabled":
        org.is_active = False
    elif change in {"role", "membership"}:
        member = db.scalar(select(Membership).where(Membership.user_id == user.id))
        if change == "role":
            member.role = "operator"
        else:
            member.is_active = False
    elif change == "source":
        source.sha256 = "c" * 64
    else:
        from sqlalchemy import update

        from idml_foundation.models import DomainSnapshot

        snapshot = current_canonical_snapshot(
            db, organization_id=org.id, resource_id=request["resource_id"]
        )
        db.execute(
            update(DomainSnapshot)
            .where(DomainSnapshot.id == snapshot.id)
            .values(content_sha256="c" * 64)
        )
    db.flush()
    with pytest.raises(ValueError):
        access.resolve(db, scope)


def test_conflicts_rollback_and_immutable_record(db, data):
    *_, request, scope = data
    first = access.decide(db, **request)
    db.commit()
    for change in [dict(days=8), dict(request_id=str(uuid4()))]:
        with pytest.raises(ValueError, match="conflict"):
            access.decide(db, **(request | change))
    access.decide(
        db, **(request | dict(request_id=str(uuid4()), expected_sequence=1, action="revoke"))
    )
    db.rollback()
    assert access.resolve(db, scope)["decision_id"] == first.id
    first.receipt = first.receipt | {"status": "revoked"}
    with pytest.raises(ValueError, match="append_only"):
        db.flush()
    db.rollback()


@pytest.mark.parametrize("role", list(Role))
def test_http_permission_and_tenant_isolation(client, db, settings, data, role):
    org, _, _, request, scope = data
    user = _user(db, org, "role-" + uuid4().hex + "@example.test", role)
    token = _token(db, user, settings)
    db.commit()
    headers = _headers(token, org)
    path = f"/v1/resources/{scope['resource_id']}/public-sources"
    before = client.get(path, headers=headers)
    assert before.status_code == 200
    payload = dict(request_id=request["request_id"], action="grant", days=7, expected_sequence=0)
    response = client.post(path, headers=headers, json=payload)
    assert response.status_code == (200 if role == Role.ORG_ADMIN else 403)
    if role == Role.ORG_ADMIN:
        assert client.get(path, headers=headers).json()["status"] == "active"
        assert (
            client.post(
                path, headers=headers, json=payload | {"source_idml_sha256": "a" * 64}
            ).status_code
            == 422
        )
    assert client.get(f"/v1/resources/{uuid4()}/public-sources", headers=headers).status_code == 404
    assert client.get(path).status_code == 401


def test_unprocessed_article_cannot_grant_and_ui_contains_no_manual_ids(client, db, settings, data):
    from idml_foundation.models import Resource

    org, user, *_ = data
    article = Resource(organization_id=org.id, title="Unprocessed")
    db.add(article)
    db.flush()
    token = _token(db, user, settings)
    db.commit()
    path = f"/v1/resources/{article.id}/public-sources"
    response = client.post(
        path,
        headers=_headers(token, org),
        json=dict(request_id=str(uuid4()), expected_sequence=0, action="grant", days=7),
    )
    assert response.status_code == 409
    html = client.get("/app").text
    assert "source-article" in html and "/app/assets/sources.js" in html
    assert client.get("/app/assets/sources.js").status_code == 200
