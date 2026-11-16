"""Authorize only an isolated qualification article through the actual HTTP route."""

from fastapi.testclient import TestClient

from idml_foundation.database import get_db
from idml_foundation.main import create_app
from idml_foundation.models import Membership, User
from idml_foundation.security import issue_session
from idml_foundation.settings import get_settings


def authorize(factory, settings, scope):
    from uuid import uuid4

    with factory() as db:
        user = User(
            email="isolated-source-" + uuid4().hex + "@example.invalid",
            password_hash="qualification-disabled-login",  # noqa: S106 - not a usable password hash
        )
        db.add(user)
        db.flush()
        db.add(
            Membership(organization_id=scope["organization_id"], user_id=user.id, role="org_admin")
        )
        token = issue_session(db, user, settings).raw_token
        db.commit()

    def database():
        with factory() as db:
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise

    app = create_app()
    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as client:
        response = client.post(
            f"/v1/resources/{scope['resource_id']}/public-sources",
            headers={
                "Authorization": "Bearer " + token,
                "X-Organization-ID": scope["organization_id"],
            },
            json=dict(request_id=str(uuid4()), expected_sequence=0, action="grant", days=1),
        )
        assert response.status_code == 200
    app.dependency_overrides.clear()
