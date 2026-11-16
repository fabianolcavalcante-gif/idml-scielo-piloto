from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


class StrictRequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginRequest(StrictRequestModel):
    email: EmailStr
    trust_browser: bool = False
    password: str = Field(min_length=14, max_length=1024)
    mfa_code: str | None = Field(default=None, pattern=r"^\d{6}$")
    recovery_code: str | None = Field(default=None, min_length=8, max_length=40)


class SessionResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 - OAuth token type, not a credential
    expires_at: datetime
    mfa_required: bool = False
    mfa_verified: bool = False


class CurrentUserRead(BaseModel):
    id: str
    email: EmailStr
    is_platform_admin: bool = False
    mfa_required: bool
    mfa_enabled: bool


class MfaSetupRequest(StrictRequestModel):
    password: str = Field(min_length=14, max_length=1024)


class MfaSetupResponse(BaseModel):
    secret: str
    provisioning_uri: str


class MfaConfirmRequest(StrictRequestModel):
    code: str = Field(pattern=r"^\d{6}$")


class MfaConfirmResponse(BaseModel):
    recovery_codes: tuple[str, ...]


class PasswordRecoveryRequest(StrictRequestModel):
    email: EmailStr


class PasswordRecoveryIssued(BaseModel):
    accepted: bool = True
    reset_token: str | None = None


class PasswordRecoveryComplete(StrictRequestModel):
    token: str = Field(min_length=32, max_length=200)
    new_password: str = Field(min_length=14, max_length=1024)


class SessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    expires_at: datetime
    last_seen_at: datetime | None
    revoked_at: datetime | None
    mfa_verified_at: datetime | None


class OrganizationRead(BaseModel):
    id: str
    slug: str
    name: str
    role: str


class MembershipRead(BaseModel):
    id: str
    user_id: str
    email: EmailStr
    role: str
    is_active: bool


class InvitationCreate(StrictRequestModel):
    email: EmailStr
    role: str = Field(pattern=r"^(org_admin|operator|reviewer|release_manager)$")


class InvitationIssued(BaseModel):
    accepted: bool = True
    development_token: str | None = None


class InvitationAccept(StrictRequestModel):
    token: str = Field(min_length=32, max_length=200)
    password: str = Field(min_length=14, max_length=1024)


class MembershipUpdate(StrictRequestModel):
    role: str = Field(pattern=r"^(org_admin|operator|reviewer|release_manager)$")
    is_active: bool = True


class ResourceCreate(StrictRequestModel):
    title: str = Field(min_length=1, max_length=300)


class ResourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    title: str
    version: int


class IdmlProcessPayload(StrictRequestModel):
    resource_id: str = Field(min_length=1, max_length=36)
    idml_artifact_id: str = Field(min_length=1, max_length=36)


class ScieloPackagePayload(StrictRequestModel):
    resource_id: str = Field(min_length=1, max_length=36)
    canonical_snapshot_id: str = Field(min_length=1, max_length=36)
    idml_artifact_id: str = Field(min_length=1, max_length=36)
    pdf_artifact_id: str = Field(min_length=1, max_length=36)
    asset_artifact_ids: tuple[str, ...] = Field(default=(), max_length=100)


class EditEvaluationPayload(StrictRequestModel):
    resource_id: UUID
    canonical_snapshot_id: UUID
    review_version: int = Field(ge=1, strict=True)


class EditRestorePayload(EditEvaluationPayload):
    action: Literal["undo", "recover"]


class EditPreflightPayload(EditEvaluationPayload):
    authorization_id: UUID | None = None


class JobCreate(StrictRequestModel):
    kind: str = Field(pattern=r"^[a-z][a-z0-9_.-]{1,79}$")
    idempotency_key: str = Field(min_length=8, max_length=200)
    payload: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_operational_payload(self) -> JobCreate:
        models: dict[str, type[BaseModel]] = {
            "idml.process": IdmlProcessPayload,
            "scielo.package": ScieloPackagePayload,
            "autocorrection.preflight": EditPreflightPayload,
            "autocorrection.evaluate": EditEvaluationPayload,
            "autocorrection.authorize": EditEvaluationPayload,
            "autocorrection.restore": EditRestorePayload,
        }
        model = models.get(self.kind)
        if model is not None:
            self.payload = model.model_validate(self.payload).model_dump(mode="json")
        elif self.kind == "foundation.noop" and self.payload:
            raise ValueError("foundation.noop does not accept payload")
        return self


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    kind: str
    state: str
    idempotency_key: str
    attempt_count: int
    version: int
    result: dict[str, Any] | None
    error_code: str | None
    available_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    cancelled_at: datetime | None


class JobControlRequest(StrictRequestModel):
    expected_version: int = Field(ge=1)


class JobEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    sequence: int
    from_state: str | None
    to_state: str
    actor_type: str
    actor_id: str | None
    correlation_id: str
    details: dict[str, Any]
    created_at: datetime


class ArtifactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    sha256: str
    size_bytes: int
    media_type: str
    original_name: str
    scanner_status: str


class AuditEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str | None
    actor_user_id: str | None
    action: str
    resource_type: str
    resource_id: str | None
    correlation_id: str
    outcome: str
    details: dict[str, Any]
    created_at: datetime


class HealthResponse(BaseModel):
    status: str
    checks: dict[str, str] = Field(default_factory=dict)


class ReviewItemCreate(StrictRequestModel):
    resource_id: str
    base_snapshot_id: str
    job_id: str | None = None
    category: str = Field(
        pattern=r"^(deterministic|semantic|missing-source|source-conflict|system)$"
    )
    rule_code: str = Field(min_length=1, max_length=200)
    field_path: str = Field(pattern=r"^/", max_length=500)
    message: str = Field(min_length=1, max_length=2000)
    evidence: list[dict[str, Any]] = Field(default_factory=list, max_length=50)
    alternatives: list[Any] = Field(default_factory=list, max_length=50)
    priority: int = Field(default=100, ge=1, le=1000)


class ReviewItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    resource_id: str
    base_snapshot_id: str
    job_id: str | None
    state: str
    category: str
    rule_code: str
    field_path: str
    message: str
    evidence: list[dict[str, Any]]
    alternatives: list[Any]
    assigned_user_id: str | None
    priority: int
    version: int
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None


class ReviewClaim(StrictRequestModel):
    expected_version: int = Field(ge=1)


class JsonPatchOperation(BaseModel):
    op: Literal["replace"]
    path: str = Field(pattern=r"^/", max_length=500)
    value: Any


class ReviewDecisionCreate(StrictRequestModel):
    expected_version: int = Field(ge=1)
    action: Literal["apply_patch", "reject"]
    patch: tuple[JsonPatchOperation, ...] = Field(default=(), max_length=10)
    justification: str = Field(min_length=10, max_length=2000)


class ReviewDecisionRead(BaseModel):
    decision_id: str
    review_item_id: str
    state: str
    result_snapshot_id: str | None
    xml_sha256: str | None
    validation_valid: bool | None
    build_id: str | None
    version: int


class ReviewDecisionHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    review_item_id: str
    actor_user_id: str
    base_snapshot_id: str
    result_snapshot_id: str | None
    action: str
    patch: list[dict[str, Any]]
    justification: str
    expected_version: int
    patch_sha256: str
    created_at: datetime


class SnapshotRead(BaseModel):
    id: str
    resource_id: str
    model_kind: str
    schema_version: str
    revision: int
    content_sha256: str
    parent_snapshot_id: str | None
    payload: dict[str, Any]


class SnapshotDiffEntry(BaseModel):
    path: str
    before: Any = None
    after: Any = None


class ReviewBuildRead(BaseModel):
    id: str
    snapshot_id: str
    xml_sha256: str
    validation: dict[str, Any]
    validation_valid: bool
    created_at: datetime


class ReleaseRequestCreate(StrictRequestModel):
    resource_id: str
    snapshot_id: str
    package_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ReleaseRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    resource_id: str
    snapshot_id: str
    package_sha256: str
    state: str
    required_approvals: int
    version: int
    requested_by_user_id: str
    approved_at: datetime | None
    created_at: datetime


class ReleaseApprovalCreate(StrictRequestModel):
    expected_version: int = Field(ge=1)
    justification: str = Field(min_length=20, max_length=2000)
    evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ReleaseApprovalRead(BaseModel):
    id: str
    release_request_id: str
    approver_user_id: str
    created_at: datetime
    request_state: str
    request_version: int
    approval_count: int


class ReleaseApprovalHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    release_request_id: str
    approver_user_id: str
    justification: str
    evidence_sha256: str
    created_at: datetime


class AgentCapabilitiesRead(BaseModel):
    enabled: bool
    swarm_enabled: bool
    auto_apply: Literal[False] = False
    release_authority: Literal[False] = False
    domains: list[str]
    tools: list[str]
    max_cost_microusd: int
    max_concurrency: int
    cost_policy: str
    pricing_version: str
    priced_models: list[str]
    default_model_key: str
    preflight_max_cost_microusd: int


class AgentRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    review_item_id: str
    base_snapshot_id: str
    task_type: str
    domain: str
    orchestrator: str
    status: str
    provider: str
    model: str
    prompt_version: str
    output_schema_version: str
    config_version: str
    input_sha256: str
    output_sha256: str | None
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    cost_microusd: int
    cost_source: str
    pricing_version: str | None
    pricing_model_key: str | None
    latency_ms: int
    attempts: int
    error_code: str | None
    created_at: datetime


class AgentProposalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    agent_run_id: str
    review_item_id: str
    base_snapshot_id: str
    domain: str
    patch: list[dict[str, Any]]
    confidence: float
    evidence: list[dict[str, Any]]
    alternatives: list[str]
    reason: str
    needs_human: bool
    proposal_sha256: str
    validation: dict[str, Any]
    created_at: datetime
