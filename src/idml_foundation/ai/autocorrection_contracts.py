"""VH-08 contracts, separate from historical human-only assistive proposals.

Only AutomationIntent is model output. Context, evidence and findings are trusted
server inputs, resolved from authorized sources, never accepted from an agent.
"""

import re
from datetime import timedelta
from decimal import Decimal
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from idml_foundation.domain.canonical import SourcedText
from idml_foundation.domain.common import SHA256_PATTERN, StrictModel, content_digest

POLICY_VERSION = "vh1-autocorrection-1.0"
PROFILE_SHA256 = "c537f446c47a3ace615f64122dd7081eb5d9a60ac52016abfd5ed52d9752507f"
Operation = Literal["country-code-exact", "figure-asset-exact", "affiliation-original-literal"]
Digest = Annotated[str, Field(pattern=SHA256_PATTERN)]
Identifier = Annotated[str, Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_.:-]+$")]


class AutomationScope(StrictModel):
    organization_id: UUID
    resource_id: UUID
    snapshot_id: UUID
    snapshot_sha256: Digest
    source_idml_sha256: Digest
    article_id: Identifier
    profile_id: Literal["esa-aop-1.1.0"]
    review_version: int = Field(ge=1, strict=True)


class AutomationOperation(StrictModel):
    operation: Operation
    subject_id: Identifier
    evidence_id: Identifier
    finding_id: UUID
    expected_value_sha256: Digest


class AutomationIntent(StrictModel):
    version: Literal["autocorrection-intent-1.0"]
    policy_version: Literal["vh1-autocorrection-1.0"]
    proposal_id: UUID
    scope: AutomationScope
    needs_human: bool = Field(strict=True)
    operations: tuple[AutomationOperation, ...] = Field(min_length=1, max_length=5)

    @model_validator(mode="after")
    def unique_operations(self) -> Self:
        keys = [(o.operation, o.subject_id) for o in self.operations]
        if len(keys) != len(set(keys)) or len({o.finding_id for o in self.operations}) != len(keys):
            raise ValueError("duplicate_automation_operation_or_finding")
        return self


class AutomationLimits(StrictModel):
    max_cycles: int = Field(default=2, ge=1, le=2, strict=True)
    max_operations: int = Field(default=5, ge=1, le=5, strict=True)
    max_seconds: int = Field(default=300, ge=1, le=900, strict=True)
    max_tokens: int = Field(default=50_000, ge=1, le=200_000, strict=True)
    max_cost_usd: Decimal = Field(default=Decimal("5.00"), gt=0, le=100, allow_inf_nan=False)


class AutomationFinding(StrictModel):
    finding_id: UUID
    operation: Operation
    subject_id: Identifier
    requires_human: bool = Field(default=True, strict=True)
    human_decision_present: bool = Field(default=False, strict=True)
    origin: Literal["deterministic-vh1", "historical-assistive"]


class AutomationContext(StrictModel):
    scope: AutomationScope
    enabled: bool = Field(default=False, strict=True)
    policy_version: Literal["vh1-autocorrection-1.0"]
    policy_sha256: Digest
    limits: AutomationLimits = Field(default_factory=AutomationLimits)
    cycle: int = Field(ge=1, strict=True)
    started_at: AwareDatetime
    consumed_tokens: int = Field(ge=0, strict=True)
    consumed_cost_usd: Decimal = Field(ge=0, allow_inf_nan=False)
    other_active_executions: int = Field(ge=0, strict=True)
    findings: tuple[AutomationFinding, ...] = Field(max_length=100)
    # Includes human-protected parents, not merely exact leaf paths.
    protected_paths: tuple[str, ...] = ()
    attempted_intents: tuple[Digest, ...] = ()

    @model_validator(mode="after")
    def canonical_protected_paths(self) -> Self:
        for path in self.protected_paths:
            if path != "/" and not re.fullmatch(
                r"(?:/(?:[A-Za-z_][A-Za-z_0-9]*|0|[1-9]\d*))+", path
            ):
                raise ValueError("noncanonical_human_protected_path")
        return self


class AutomationEvidence(StrictModel):
    """Verified field-bound IDML extraction + operator grant, supplied by the server.

    Hashes alone do not authorize a source. VH-09/10 must resolve the live grant,
    exact extraction and asset bytes before creating this object.
    """

    version: Literal["autocorrection-evidence-1.0"]
    scope: AutomationScope
    evidence_id: Identifier
    operation: Operation
    subject_id: Identifier
    source_kind: Literal["idml"]
    artifact_sha256: Digest
    source_text: str = Field(min_length=1, max_length=4096)
    source_text_sha256: Digest
    # Content address of the trusted extraction, for audit, not an AI confidence.
    extraction_sha256: Digest
    authorization_id: UUID
    authorization_decision_sha256: Digest
    status: Literal["active", "revoked"]
    collected_at: AwareDatetime
    issued_at: AwareDatetime
    expires_at: AwareDatetime
    target_asset_sha256: Digest | None = None

    @model_validator(mode="after")
    def narrow_grant(self) -> Self:
        if not self.collected_at <= self.issued_at < self.expires_at:
            raise ValueError("automation_grant_dates_invalid")
        if self.expires_at - self.collected_at > timedelta(days=30):
            raise ValueError("automation_grant_too_long")
        if (self.operation == "figure-asset-exact") != (self.target_asset_sha256 is not None):
            raise ValueError("automation_asset_evidence_mismatch")
        return self


class PreparedAutomationOperation(StrictModel):
    operation: Operation
    subject_id: Identifier
    finding_id: UUID
    path: str
    before_sha256: Digest
    after_sha256: Digest
    # Private executor material; public diagnostics use hashes, not these values.
    value: SourcedText | str
    evidence_id: Identifier
    evidence_sha256: Digest
    authorization_id: UUID


class AutomationDecision(StrictModel):
    version: Literal["autocorrection-decision-1.0"] = "autocorrection-decision-1.0"
    policy_version: Literal["vh1-autocorrection-1.0"] = "vh1-autocorrection-1.0"
    scope: AutomationScope
    intent_sha256: Digest
    disposition: Literal["eligible_for_candidate", "refused", "abstained"]
    reason: str
    operations: tuple[PreparedAutomationOperation, ...] = ()
    applied: Literal[False] = False
    requires_revalidation: Literal[True] = True
    release_approved: Literal[False] = False

    @model_validator(mode="after")
    def no_partial_acceptance(self) -> Self:
        if bool(self.operations) != (self.disposition == "eligible_for_candidate"):
            raise ValueError("automation_decision_operations_inconsistent")
        return self


def intent_digest(intent: AutomationIntent) -> str:
    """Retry identity excludes a model-chosen ID: changing that ID cannot avoid loop detection."""
    payload = intent.model_dump(mode="json", exclude={"proposal_id"})
    payload["operations"] = sorted(
        payload["operations"], key=lambda op: (op["operation"], op["subject_id"])
    )
    return content_digest(payload)


class AutomationEvent(StrictModel):
    version: Literal["autocorrection-event-1.0"] = "autocorrection-event-1.0"
    actor: Literal["service:idml-autocorrection"] = "service:idml-autocorrection"
    scope: AutomationScope
    policy_sha256: Digest
    intent_sha256: Digest
    decision_sha256: Digest
    state: Literal["eligible_for_candidate", "refused", "abstained"]
    recorded_at: AwareDatetime
    previous_event_sha256: Digest | None = None
    applied: Literal[False] = False
    release_approved: Literal[False] = False
