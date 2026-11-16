"""Server-owned batch consent -> exact field grants. No client/model authority endpoint."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal, Self
from uuid import UUID, uuid4, uuid5

from pydantic import AwareDatetime, Field, TypeAdapter, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from idml_foundation.ai.autocorrection_contracts import (
    AutomationFinding,
    AutomationIntent,
    AutomationOperation,
    AutomationScope,
    Digest,
)
from idml_foundation.autocorrection_models import AutomationGrantRecord, AutomationGrantRevocation
from idml_foundation.database import ensure_write_transaction as _ensure_transaction
from idml_foundation.domain.canonical import CanonicalArticle
from idml_foundation.domain.common import StrictModel, content_digest
from idml_foundation.models import Artifact, Resource
from idml_foundation.pipeline.autocorrection_evidence import qualify_fields
from idml_foundation.pipeline.profile import JournalProfile
from idml_foundation.services.autocorrection_sources import ExtractionGrant, SourceResolutionError
from idml_foundation.services.canonical_heads import current_canonical_snapshot
from idml_foundation.services.enrichment import _read
from idml_foundation.settings import Settings


class _BatchDecision(StrictModel):
    """New explicit permission, not a reinterpretation of old catalog grants.

    Provisioned by trusted administration once for the source/batch. File-system
    access is the authority boundary; decision hashes are traceability, not signatures.
    """

    policy_version: Literal["vh1-autocorrection-1.0"] = "vh1-autocorrection-1.0"
    authorization_id: UUID
    organization_id: UUID
    resource_id: UUID
    source_idml_sha256: Digest
    canonical_sha256: Digest
    catalog_sha256: Digest
    profile_id: Literal["esa-aop-1.1.0"] = "esa-aop-1.1.0"
    destination: Literal["local", "vps"]
    status: Literal["active", "revoked"]
    decision_sha256: Digest
    collected_at: AwareDatetime
    issued_at: AwareDatetime
    expires_at: AwareDatetime

    @model_validator(mode="after")
    def bounded_dates(self) -> Self:
        if (
            not self.collected_at <= self.issued_at < self.expires_at
            or self.expires_at - self.collected_at > timedelta(days=30)
        ):
            raise ValueError("batch_authorization_dates_invalid")
        return self


class AutomationBatchAuthorization(_BatchDecision):
    version: Literal["autocorrection-batch-authorization-1.0"] = (
        "autocorrection-batch-authorization-1.0"
    )


class RevisionEditAuthorization(_BatchDecision):
    version: Literal["autocorrection-batch-authorization-2.0"] = (
        "autocorrection-batch-authorization-2.0"
    )
    snapshot_id: UUID
    review_version: int = Field(ge=1, strict=True)


_Decision = AutomationBatchAuthorization | RevisionEditAuthorization
_DECISIONS: TypeAdapter[_Decision] = TypeAdapter(
    Annotated[_Decision, Field(discriminator="version")]
)


def load_batch_authorization(
    settings: Settings,
    *,
    authorization_id: UUID,
    scope: AutomationScope,
    catalog_sha256: str,
    now: datetime,
) -> _Decision:
    try:
        root = settings.automation_authorization_root or settings.enrichment_root
        if (
            now.utcoffset() is None
            or root is None
            or not root.is_dir()
            or settings.enrichment_location is None
            or any(p.is_symlink() or p.is_junction() for p in (root, *root.absolute().parents))
        ):
            raise ValueError("authorization_store_unavailable")
        raw = _read(
            root, Path("autocorrection-authorizations") / f"{authorization_id}.json", 16 * 1024
        )
        authorization = _DECISIONS.validate_json(raw)
        if (
            authorization.authorization_id != authorization_id
            or authorization.organization_id != scope.organization_id
            or authorization.resource_id != scope.resource_id
            or authorization.source_idml_sha256 != scope.source_idml_sha256
            or authorization.canonical_sha256 != scope.snapshot_sha256
            or authorization.catalog_sha256 != catalog_sha256
            or authorization.profile_id != scope.profile_id
            or (
                isinstance(authorization, RevisionEditAuthorization)
                and (authorization.snapshot_id, authorization.review_version)
                != (scope.snapshot_id, scope.review_version)
            )
            or authorization.destination != settings.enrichment_location
            or authorization.status != "active"
            or not authorization.issued_at <= now < authorization.expires_at
        ):
            raise ValueError("batch_authorization_scope_or_status")
        return authorization
    except (ValueError, OSError):
        raise SourceResolutionError("batch_authorization_unavailable_or_invalid") from None


def verify_parent_authorization(grant: ExtractionGrant, settings: Settings, now: datetime) -> None:
    if grant.parent_authorization_id is None:
        return  # Historical operator-issued field grants retain their existing contract.
    assert grant.catalog_sha256 is not None
    parent = load_batch_authorization(
        settings,
        authorization_id=grant.parent_authorization_id,
        scope=grant.scope,
        catalog_sha256=grant.catalog_sha256,
        now=now,
    )
    if (
        content_digest(parent) != grant.parent_authorization_sha256
        or parent.decision_sha256 != grant.decision_sha256
        or (parent.collected_at, parent.issued_at, parent.expires_at)
        != (grant.collected_at, grant.issued_at, grant.expires_at)
    ):
        raise SourceResolutionError("parent_authorization_changed")


@dataclass(frozen=True)
class ProvisionedAutomation:
    intent: AutomationIntent
    findings: tuple[AutomationFinding, ...]
    catalog_sha256: str
    parent_sha256: str


class NoEligibleFields(ValueError):
    def __init__(self, catalog_sha256: str):
        super().__init__("field_batch_empty_or_exceeds_policy_limit")
        self.catalog_sha256 = catalog_sha256


def provision_field_grants(
    db: Session,
    *,
    organization_id: str,
    scope: AutomationScope,
    authorization_id: UUID | None,
    profile: JournalProfile,
    settings: Settings,
    now: datetime,
    require_revision_decision: bool = False,
) -> ProvisionedAutomation:
    """Recompute the catalog from stored bytes, then provision an authorized batch atomically.

    The caller commits. No catalog, findings or source proof are accepted from an agent.
    This is an internal opt-in service, not a new user-accessible API.
    """
    from idml_foundation.services.autocorrection_executor import (
        _artifact,
        register_extraction_grant,
    )

    if str(scope.organization_id) != organization_id:
        raise PermissionError("automation_scope_mismatch")
    _ensure_transaction(db)
    with db.begin_nested():
        resource = db.scalar(
            select(Resource)
            .where(
                Resource.id == str(scope.resource_id),
                Resource.organization_id == organization_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        snapshot = current_canonical_snapshot(
            db, organization_id=organization_id, resource_id=str(scope.resource_id)
        )
        if (
            resource is None
            or resource.version != scope.review_version
            or snapshot is None
            or snapshot.id != str(scope.snapshot_id)
            or snapshot.content_sha256 != scope.snapshot_sha256
            or content_digest(snapshot.payload) != scope.snapshot_sha256
        ):
            raise ValueError("automation_stale_snapshot_or_revision")
        article = CanonicalArticle.model_validate(snapshot.payload)
        if (
            db.scalar(
                select(Artifact.id).where(
                    Artifact.id == snapshot.source_artifact_id,
                    Artifact.organization_id == organization_id,
                    Artifact.sha256 == scope.source_idml_sha256,
                )
            )
            is None
        ):
            raise ValueError("snapshot_source_mismatch")
        idml = _artifact(db, organization_id, scope.source_idml_sha256, settings)
        qualified = qualify_fields(article, idml=idml, profile=profile, settings=settings)
        if content_digest(qualified.article) != scope.snapshot_sha256:
            raise ValueError("snapshot_requires_field_evidence_preparation")
        catalog = qualified.catalog
        catalog_sha = content_digest(catalog)
        if not catalog.bindings:
            raise NoEligibleFields(catalog_sha)
        if len(catalog.bindings) > 5:
            raise ValueError("field_batch_empty_or_exceeds_policy_limit")
        if require_revision_decision and settings.automation_authorization_root is None:
            raise SourceResolutionError("edit_decision_store_unavailable")
        if authorization_id is None:
            raise SourceResolutionError("batch_authorization_required")
        parent = load_batch_authorization(
            settings,
            authorization_id=authorization_id,
            scope=scope,
            catalog_sha256=catalog_sha,
            now=now,
        )
        if require_revision_decision and not isinstance(parent, RevisionEditAuthorization):
            raise SourceResolutionError("revision_authorization_required")
        parent_sha = content_digest(parent)
        operations, findings = [], []
        for binding in catalog.bindings:
            source = next(e for e in article.evidence if e.id == binding.evidence_id)
            assert source.content_sha256 is not None
            identity = f"{scope.snapshot_id}:{content_digest(binding)}:{parent_sha}"
            grant_id = uuid5(authorization_id, identity)
            finding_id = uuid5(scope.snapshot_id, content_digest(binding))
            grant = ExtractionGrant(
                authorization_id=grant_id,
                decision_sha256=parent.decision_sha256,
                scope=scope,
                operation=binding.operation,
                subject_id=binding.subject_id,
                evidence_id=binding.evidence_id,
                locator=source.locator,
                source_text_sha256=source.content_sha256,
                collected_at=parent.collected_at,
                issued_at=parent.issued_at,
                expires_at=parent.expires_at,
                parent_authorization_id=authorization_id,
                parent_authorization_sha256=parent_sha,
                catalog_sha256=catalog_sha,
            )
            existing = db.get(AutomationGrantRecord, str(grant_id))
            if existing is None:
                register_extraction_grant(db, organization_id=organization_id, grant=grant)
            elif (
                existing.organization_id != organization_id
                or content_digest(existing.payload) != content_digest(grant)
                or existing.payload_sha256 != content_digest(grant)
            ):
                raise ValueError("existing_field_grant_conflict")
            if db.get(AutomationGrantRevocation, str(grant_id)) is not None:
                raise ValueError("field_grant_revoked")
            operations.append(AutomationOperation(**binding.model_dump(), finding_id=finding_id))
            findings.append(
                AutomationFinding(
                    finding_id=finding_id,
                    operation=binding.operation,
                    subject_id=binding.subject_id,
                    requires_human=False,
                    origin="deterministic-vh1",
                )
            )
        return ProvisionedAutomation(
            AutomationIntent(
                version="autocorrection-intent-1.0",
                policy_version="vh1-autocorrection-1.0",
                proposal_id=uuid4(),
                scope=scope,
                needs_human=False,
                operations=tuple(operations),
            ),
            tuple(findings),
            catalog_sha,
            parent_sha,
        )
