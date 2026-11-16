import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from idml_foundation.mfa import totp_at, verify_totp
from idml_foundation.models import (
    AuditEvent,
    DomainSnapshot,
    Membership,
    Organization,
    ReleaseApproval,
    Resource,
    User,
    utcnow,
)
from idml_foundation.rbac import Role
from idml_foundation.security import hash_password, issue_session
from idml_foundation.services.snapshots import store_snapshot
from idml_foundation.settings import Settings
from tests.domain_helpers import canonical_article

PASSWORD = "a sufficiently long phase five password"


def _user(
    db: Session,
    org: Organization,
    email: str,
    role: Role,
    *,
    mfa: bool = False,
) -> User:
    user = User(
        email=email,
        password_hash=hash_password(PASSWORD),
        mfa_enabled_at=utcnow() if mfa else None,
    )
    db.add(user)
    db.flush()
    db.add(Membership(user_id=user.id, organization_id=org.id, role=role.value))
    db.flush()
    return user


def _token(db: Session, user: User, settings: Settings, *, mfa: bool = False) -> str:
    return issue_session(db, user, settings, mfa_verified=mfa).raw_token


def _headers(token: str, org: Organization) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "X-Organization-ID": org.id,
    }


def test_mfa_setup_recovery_login_and_replay_protection(
    client: TestClient, db: Session, settings: Settings
) -> None:
    user = User(email="mfa@example.com", password_hash=hash_password(PASSWORD))
    db.add(user)
    db.commit()
    login = client.post("/v1/auth/login", json={"email": user.email, "password": PASSWORD})
    token = login.json()["access_token"]
    auth = {"Authorization": f"Bearer {token}"}

    setup = client.post("/v1/auth/mfa/setup", json={"password": PASSWORD}, headers=auth)
    assert setup.status_code == 200
    secret = setup.json()["secret"]
    counter = int(time.time()) // 30
    confirm = client.post(
        "/v1/auth/mfa/confirm",
        json={"code": totp_at(secret, counter)},
        headers=auth,
    )
    assert confirm.status_code == 200
    recovery_codes = confirm.json()["recovery_codes"]
    assert len(recovery_codes) == 10
    assert client.get("/v1/auth/me", headers=auth).status_code == 401

    missing = client.post("/v1/auth/login", json={"email": user.email, "password": PASSWORD})
    assert missing.status_code == 401
    assert missing.json()["detail"] == "MFA required"
    recovered = client.post(
        "/v1/auth/login",
        json={
            "email": user.email,
            "password": PASSWORD,
            "recovery_code": recovery_codes[0],
        },
    )
    assert recovered.status_code == 200
    assert recovered.json()["mfa_verified"] is True
    replayed_recovery = client.post(
        "/v1/auth/login",
        json={
            "email": user.email,
            "password": PASSWORD,
            "recovery_code": recovery_codes[0],
        },
    )
    assert replayed_recovery.status_code == 401

    fixed_secret = "JBSWY3DPEHPK3PXP"
    assert verify_totp(fixed_secret, totp_at(fixed_secret, 100), timestamp=3000) == 100
    assert (
        verify_totp(
            fixed_secret,
            totp_at(fixed_secret, 100),
            timestamp=3000,
            last_counter=100,
        )
        is None
    )


def test_gate_g5_review_patch_is_tenant_bound_versioned_and_auditable(
    client: TestClient, db: Session, settings: Settings
) -> None:
    org = Organization(slug="phase5", name="Phase 5")
    other_org = Organization(slug="phase5-other", name="Other")
    db.add_all([org, other_org])
    db.flush()
    operator = _user(db, org, "operator@example.test", Role.OPERATOR)
    reviewer = _user(db, org, "reviewer@example.test", Role.REVIEWER)
    manager = _user(db, org, "manager@example.test", Role.RELEASE_MANAGER)
    outsider = _user(db, other_org, "outsider@example.test", Role.REVIEWER)
    resource = Resource(organization_id=org.id, title="Review article")
    db.add(resource)
    db.flush()
    base, _ = store_snapshot(
        db,
        organization_id=org.id,
        resource_id=resource.id,
        document=canonical_article(),
        revision=1,
    )
    tokens = {
        "operator": _token(db, operator, settings),
        "reviewer": _token(db, reviewer, settings),
        "manager": _token(db, manager, settings),
        "outsider": _token(db, outsider, settings),
    }
    db.commit()

    created = client.post(
        "/v1/reviews",
        headers=_headers(tokens["operator"], org),
        json={
            "resource_id": resource.id,
            "base_snapshot_id": base.id,
            "category": "semantic",
            "rule_code": "TITLE_REVIEW",
            "field_path": "/front/titles/0/text/value",
            "message": "Confirm the title against IDML and PDF",
            "evidence": [
                {"source": "IDML", "locator": "Stories/Story_u1.xml"},
                {"source": "PDF", "page": 1, "bbox": [10, 20, 100, 40]},
            ],
            "alternatives": ["Synthetic title", "Corrected title"],
        },
    )
    assert created.status_code == 201
    item = created.json()

    assert (
        client.post(
            f"/v1/reviews/{item['id']}/decisions",
            headers=_headers(tokens["manager"], org),
            json={
                "expected_version": 1,
                "action": "reject",
                "justification": "Manager cannot perform reviewer action",
            },
        ).status_code
        == 403
    )
    assert (
        client.get(
            f"/v1/reviews/{item['id']}",
            headers=_headers(tokens["outsider"], other_org),
        ).status_code
        == 404
    )

    claim = client.post(
        f"/v1/reviews/{item['id']}/claim",
        headers=_headers(tokens["reviewer"], org),
        json={"expected_version": 1},
    )
    assert claim.status_code == 200
    assert claim.json()["version"] == 2
    stale = client.post(
        f"/v1/reviews/{item['id']}/claim",
        headers=_headers(tokens["reviewer"], org),
        json={"expected_version": 1},
    )
    assert stale.status_code == 409

    decision = client.post(
        f"/v1/reviews/{item['id']}/decisions",
        headers=_headers(tokens["reviewer"], org),
        json={
            "expected_version": 2,
            "action": "apply_patch",
            "patch": [
                {
                    "op": "replace",
                    "path": "/front/titles/0/text/value",
                    "value": "Corrected title",
                }
            ],
            "justification": "Title confirmed against both supplied sources",
        },
    )
    assert decision.status_code == 200, decision.text
    result = decision.json()
    assert result["state"] == "resolved"
    assert result["result_snapshot_id"] != base.id
    assert result["xml_sha256"]

    old = client.get(f"/v1/snapshots/{base.id}", headers=_headers(tokens["reviewer"], org)).json()
    new = client.get(
        f"/v1/snapshots/{result['result_snapshot_id']}",
        headers=_headers(tokens["reviewer"], org),
    ).json()
    assert old["payload"]["front"]["titles"][0]["text"]["value"] == "Synthetic title"
    assert new["payload"]["front"]["titles"][0]["text"]["value"] == "Corrected title"
    assert new["parent_snapshot_id"] == base.id
    diff = client.get(
        f"/v1/snapshots/{base.id}/diff/{result['result_snapshot_id']}",
        headers=_headers(tokens["reviewer"], org),
    ).json()
    assert any(row["path"] == "/front/titles/0/text/value" for row in diff)
    history = client.get(
        f"/v1/reviews/{item['id']}/history",
        headers=_headers(tokens["reviewer"], org),
    ).json()
    assert history[0]["actor_user_id"] == reviewer.id
    assert history[0]["patch_sha256"]
    xml = client.get(
        f"/v1/review-builds/{result['build_id']}/xml",
        headers=_headers(tokens["reviewer"], org),
    )
    assert xml.status_code == 200
    assert result["xml_sha256"] in {
        row.details["xml_sha256"]
        for row in db.scalars(select(AuditEvent).where(AuditEvent.action == "review.xml.download"))
    }

    persisted_base = db.get(DomainSnapshot, base.id)
    assert persisted_base is not None
    persisted_base.payload = {"tampered": True}
    with pytest.raises(ValueError, match="append-only"):
        db.flush()
    db.rollback()


def test_double_editorial_approval_requires_distinct_mfa_users_and_is_not_ready(
    client: TestClient, db: Session, settings: Settings
) -> None:
    org = Organization(slug="release-editorial", name="Editorial")
    db.add(org)
    db.flush()
    requester = _user(db, org, "requester@example.test", Role.RELEASE_MANAGER, mfa=True)
    first = _user(db, org, "first@example.test", Role.RELEASE_MANAGER, mfa=True)
    second = _user(db, org, "second@example.test", Role.RELEASE_MANAGER, mfa=True)
    resource = Resource(organization_id=org.id, title="Release article")
    db.add(resource)
    db.flush()
    snapshot, _ = store_snapshot(
        db,
        organization_id=org.id,
        resource_id=resource.id,
        document=canonical_article(),
        revision=1,
    )
    tokens = {user.id: _token(db, user, settings, mfa=True) for user in (requester, first, second)}
    db.commit()
    package_sha = "d" * 64
    created = client.post(
        "/v1/releases",
        headers=_headers(tokens[requester.id], org),
        json={
            "resource_id": resource.id,
            "snapshot_id": snapshot.id,
            "package_sha256": package_sha,
        },
    )
    assert created.status_code == 201
    request = created.json()
    approval = {
        "expected_version": 1,
        "justification": "Independent editorial approval with recorded evidence",
        "evidence_sha256": "e" * 64,
    }
    own = client.post(
        f"/v1/releases/{request['id']}/approvals",
        headers=_headers(tokens[requester.id], org),
        json=approval,
    )
    assert own.status_code == 403
    approved_first = client.post(
        f"/v1/releases/{request['id']}/approvals",
        headers=_headers(tokens[first.id], org),
        json=approval,
    )
    assert approved_first.status_code == 200
    assert approved_first.json()["request_state"] == "pending"
    approval["expected_version"] = 2
    approved_second = client.post(
        f"/v1/releases/{request['id']}/approvals",
        headers=_headers(tokens[second.id], org),
        json=approval,
    )
    assert approved_second.status_code == 200
    assert approved_second.json()["request_state"] == "editorially_approved"
    assert "READY" not in approved_second.json()["request_state"]
    history = client.get(
        f"/v1/releases/{request['id']}/approvals",
        headers=_headers(tokens[first.id], org),
    )
    assert [row["approver_user_id"] for row in history.json()] == [first.id, second.id]

    stored = db.scalar(select(ReleaseApproval).limit(1))
    assert stored is not None
    stored.justification = "tampered"
    with pytest.raises(ValueError, match="append-only"):
        db.flush()
    db.rollback()


def test_invitation_existing_identity_and_last_admin_guard(
    client: TestClient, db: Session, settings: Settings
) -> None:
    org = Organization(slug="membership-phase5", name="Membership Phase 5")
    db.add(org)
    db.flush()
    admin = _user(db, org, "membership-admin@example.com", Role.ORG_ADMIN, mfa=True)
    existing = User(
        email="existing-user@example.com",
        password_hash=hash_password(PASSWORD),
        is_active=True,
    )
    db.add(existing)
    db.flush()
    token = _token(db, admin, settings, mfa=True)
    admin_membership = db.scalar(
        select(Membership).where(
            Membership.user_id == admin.id,
            Membership.organization_id == org.id,
        )
    )
    assert admin_membership is not None
    db.commit()
    headers = _headers(token, org)

    invited = client.post(
        f"/v1/organizations/{org.id}/invitations",
        headers=headers,
        json={"email": "new-user@example.com", "role": "reviewer"},
    )
    assert invited.status_code == 200
    accepted = client.post(
        "/v1/organizations/invitations/accept",
        json={"token": invited.json()["development_token"], "password": PASSWORD},
    )
    assert accepted.status_code == 204
    assert (
        client.post(
            "/v1/auth/login",
            json={"email": "new-user@example.com", "password": PASSWORD},
        ).status_code
        == 200
    )

    existing_invite = client.post(
        f"/v1/organizations/{org.id}/invitations",
        headers=headers,
        json={"email": existing.email, "role": "operator"},
    )
    invitation_token = existing_invite.json()["development_token"]
    denied = client.post(
        "/v1/organizations/invitations/accept",
        json={"token": invitation_token, "password": "wrong password long enough"},
    )
    assert denied.status_code == 400
    accepted_existing = client.post(
        "/v1/organizations/invitations/accept",
        json={"token": invitation_token, "password": PASSWORD},
    )
    assert accepted_existing.status_code == 204
    assert (
        client.post(
            "/v1/auth/login",
            json={"email": existing.email, "password": PASSWORD},
        ).status_code
        == 200
    )

    last_admin = client.patch(
        f"/v1/organizations/{org.id}/members/{admin_membership.id}",
        headers=headers,
        json={"role": "operator", "is_active": True},
    )
    assert last_admin.status_code == 409
    assert "retain an active administrator" in last_admin.json()["detail"]


def test_interface_has_csp_and_phase_five_controls(client: TestClient) -> None:
    page = client.get("/app")
    assert page.status_code == 200
    assert "Review Queue" in page.text
    assert "Identidade, MFA e sessões" in page.text
    assert "Aprovação editorial" in page.text
    assert "script-src 'self'" in page.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in page.headers["content-security-policy"]
