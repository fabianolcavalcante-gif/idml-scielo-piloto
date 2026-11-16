import pytest
from sqlalchemy.orm import Session

from idml_foundation.models import Organization, Resource
from idml_foundation.services.snapshots import load_snapshot, store_snapshot
from tests.domain_helpers import canonical_article, raw_article


def test_snapshot_is_tenant_bound_immutable_and_idempotent(db: Session) -> None:
    organization = Organization(slug="snapshot-org", name="Snapshot Org")
    other = Organization(slug="snapshot-other", name="Other Org")
    db.add_all([organization, other])
    db.flush()
    resource = Resource(organization_id=organization.id, title="Article")
    db.add(resource)
    db.flush()

    snapshot, created = store_snapshot(
        db,
        organization_id=organization.id,
        resource_id=resource.id,
        document=raw_article(),
        revision=1,
    )
    duplicate, duplicate_created = store_snapshot(
        db,
        organization_id=organization.id,
        resource_id=resource.id,
        document=raw_article(),
        revision=2,
    )
    assert created is True
    assert duplicate_created is False
    assert duplicate.id == snapshot.id
    assert load_snapshot(snapshot) == raw_article()

    canonical, canonical_created = store_snapshot(
        db,
        organization_id=organization.id,
        resource_id=resource.id,
        document=canonical_article(),
        revision=1,
    )
    assert canonical_created is True
    assert load_snapshot(canonical) == canonical_article()

    with pytest.raises(ValueError, match="does not belong"):
        store_snapshot(
            db,
            organization_id=other.id,
            resource_id=resource.id,
            document=raw_article(),
            revision=1,
        )
