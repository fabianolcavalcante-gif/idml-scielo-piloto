"""Owner-provisioned public-validation access for opted-in web organizations."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from idml_foundation.domain.common import StrictModel, content_digest

ROOT = Path("/run/idml-web-sources")
PROFILE = "esa-aop-1.1.0"


class ArticlePermit(StrictModel):
    decision_id: UUID
    supersedes_decision_id: UUID | None
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    issued_at: AwareDatetime
    expires_at: AwareDatetime

    @model_validator(mode="after")
    def bounded(self) -> Self:
        if not timedelta(0) < self.expires_at - self.issued_at <= timedelta(days=30):
            raise ValueError("invalid_public_source_window")
        return self


class PublicSourcePolicy(StrictModel):
    version: Literal["web-public-sources-1"]
    organization_id: UUID
    profile: Literal["esa-aop-1.1.0"]
    delegate_operators: bool = Field(strict=True)
    articles: dict[UUID, ArticlePermit]


def policy_for(org: str) -> PublicSourcePolicy | None:
    path = ROOT / (str(UUID(org)) + ".json")
    if ROOT.is_symlink() or path.is_symlink():
        raise ValueError("invalid_public_source_policy")
    try:
        with path.open("rb") as stream:
            raw = stream.read(65537)
    except FileNotFoundError:
        return None
    if len(raw) > 65536:
        raise ValueError("invalid_public_source_policy")
    policy = PublicSourcePolicy.model_validate_json(raw)
    if str(policy.organization_id) != org:
        raise ValueError("invalid_public_source_organization")
    return policy


def public_article_permit(scope: dict[str, str], latest_id: str | None) -> dict[str, str] | None:
    policy = policy_for(scope["organization_id"])
    if policy is None or scope["journal_profile_id"] != policy.profile:
        return None
    article = policy.articles.get(UUID(scope["resource_id"]))
    if article is None:
        return None
    previous = str(article.supersedes_decision_id) if article.supersedes_decision_id else None
    if (
        previous != latest_id
        or article.source_sha256 != scope["source_idml_sha256"]
        or not article.issued_at <= datetime.now(UTC) < article.expires_at
    ):
        return None
    return dict(
        decision_id=str(article.decision_id),
        decision_sha256=content_digest(
            dict(
                organization_id=scope["organization_id"],
                resource_id=scope["resource_id"],
                profile=policy.profile,
                permission=article.model_dump(mode="json"),
            )
        ),
        expires_at=article.expires_at.isoformat(),
    )
