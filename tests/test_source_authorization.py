from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from idml_foundation.services.source_authorization import SourceAuthorization


def authorization():
    now = datetime(2026, 10, 1, tzinfo=UTC)
    org, article, identity = uuid4(), uuid4(), uuid4()
    grant = SourceAuthorization.model_validate(
        {
            "version": "source-authorization-1.0",
            "authorization_id": identity,
            "organization_id": org,
            "resource_id": article,
            "source_idml_sha256": "a" * 64,
            "profile_id": "esa-aop-1.1.0",
            "destination": "local",
            "status": "active",
            "decision_id": uuid4(),
            "decision_sha256": "b" * 64,
            "issued_at": now,
            "expires_at": now + timedelta(days=30),
            "catalogs": {
                "crossref_metadata_catalog": {
                    "source": "crossref_public_record",
                    "catalog_sha256": "c" * 64,
                    "evidence_sha256": "d" * 64,
                    "collected_at": now,
                }
            },
        }
    )
    request = {
        "authorization_id": identity,
        "organization_id": str(org),
        "resource_id": str(article),
        "source_sha256": "a" * 64,
        "profile_id": "esa-aop-1.1.0",
        "destination": "local",
        "catalog_hashes": {"crossref_metadata_catalog": "c" * 64},
        "now": now,
    }
    return grant, request


def test_crossref_expires_before_longer_operator_grant():
    grant, request = authorization()
    grant.check(**request)
    request["now"] += timedelta(days=7, seconds=1)
    with pytest.raises(ValueError, match="source_authorization_invalid"):
        grant.check(**request)


def test_exact_expiry_is_not_valid():
    grant, request = authorization()
    request["now"] = grant.expires_at
    with pytest.raises(ValueError, match="source_authorization_invalid"):
        grant.check(**request)


def test_ambiguous_clock_is_rejected():
    grant, request = authorization()
    request["now"] = request["now"].replace(tzinfo=None)
    with pytest.raises(ValueError, match="source_authorization_invalid"):
        grant.check(**request)


def test_future_evidence_cannot_be_authorized():
    grant, request = authorization()
    payload = grant.model_dump()
    payload["catalogs"]["crossref_metadata_catalog"]["collected_at"] += timedelta(seconds=1)
    with pytest.raises(ValueError, match="source_authorization_invalid"):
        SourceAuthorization.model_validate(payload).check(**request)
