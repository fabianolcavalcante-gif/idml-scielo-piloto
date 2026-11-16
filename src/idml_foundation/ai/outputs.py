from __future__ import annotations

import json
from enum import StrEnum
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AgentDomain(StrEnum):
    METADATA = "metadata"
    CONTRIBUTORS = "contributors_affiliations"
    STRUCTURE = "structure"
    REFERENCES = "references"
    FIGURES_TABLES = "figures_tables"
    MATH_NOTES = "math_notes"


EvidenceId = Annotated[str, Field(min_length=1, max_length=200)]


class AgentPatchOperation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    op: Literal["replace"]
    path: str = Field(pattern=r"^/", min_length=2, max_length=500)
    value: Any
    evidence_ids: tuple[EvidenceId, ...] = Field(
        min_length=1,
        max_length=20,
        json_schema_extra={"uniqueItems": True},
    )

    @model_validator(mode="after")
    def evidence_ids_are_unique(self) -> Self:
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("patch operation evidence_ids must be unique")
        return self


class AgentEvidenceValueSource(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    type: Literal["authorized_evidence"]
    evidence_id: EvidenceId


class AgentPatchIntentOperation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    op: Literal["replace"]
    path: str = Field(pattern=r"^/", min_length=2, max_length=500)
    value_source: AgentEvidenceValueSource


class AgentEvidenceSegmentReference(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    segment_id: str = Field(min_length=1, max_length=240)
    position: int = Field(ge=0, le=15)
    text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class AgentEvidenceReference(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    evidence_id: str = Field(min_length=1, max_length=200)
    source_kind: Literal["idml", "pdf", "validation", "canonical"]
    locator: str = Field(min_length=1, max_length=500)
    excerpt_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    segments: tuple[AgentEvidenceSegmentReference, ...] = Field(default=(), max_length=16)
    aggregate_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    image_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    media_type: Literal["image/png", "image/jpeg"] | None = None
    page_index: int | None = Field(default=None, ge=0, le=10_000)
    bbox: tuple[float, float, float, float] | None = None

    @model_validator(mode="after")
    def exactly_one_evidence_representation(self) -> Self:
        legacy = self.excerpt_sha256 is not None
        segmented = bool(self.segments) or self.aggregate_sha256 is not None
        visual = any(
            value is not None
            for value in (self.image_sha256, self.media_type, self.page_index, self.bbox)
        )
        if sum((legacy, segmented, visual)) != 1:
            raise ValueError("evidence reference must use exactly one representation")
        if segmented:
            if not self.segments or self.aggregate_sha256 is None:
                raise ValueError("segmented evidence reference is incomplete")
            if tuple(segment.position for segment in self.segments) != tuple(
                range(len(self.segments))
            ):
                raise ValueError("evidence segments must be contiguous and ordered")
            ids = tuple(segment.segment_id for segment in self.segments)
            if len(ids) != len(set(ids)):
                raise ValueError("evidence segment references must be unique")
        if visual:
            if None in (self.image_sha256, self.media_type, self.page_index, self.bbox):
                raise ValueError("visual evidence reference is incomplete")
            assert self.bbox is not None
            x0, y0, x1, y1 = self.bbox
            if not all(value >= 0 for value in self.bbox) or x1 <= x0 or y1 <= y0:
                raise ValueError("visual evidence bounding box is invalid")
        return self


class AgentProposalOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal["agent-proposal-1.1"]
    domain: AgentDomain
    patch: tuple[AgentPatchOperation, ...] = Field(min_length=1, max_length=5)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: tuple[AgentEvidenceReference, ...] = Field(min_length=1, max_length=20)
    alternatives: tuple[str, ...] = Field(min_length=1, max_length=10)
    reason: str = Field(min_length=20, max_length=2000)
    needs_human: bool

    @model_validator(mode="after")
    def proposal_invariants(self) -> Self:
        if self.confidence < 0.85 and not self.needs_human:
            raise ValueError("low-confidence proposals must require human review")
        declared = [reference.evidence_id for reference in self.evidence]
        if len(declared) != len(set(declared)):
            raise ValueError("proposal evidence references must be unique")
        used = {evidence_id for operation in self.patch for evidence_id in operation.evidence_ids}
        if used != set(declared):
            raise ValueError(
                "patch evidence_ids must use every and only declared evidence reference"
            )
        by_path = {operation.path: operation for operation in self.patch}
        for operation in self.patch:
            if operation.path.endswith("/plain/value"):
                suffix = "/plain/value"
                sibling = by_path.get(f"{operation.path[: -len(suffix)]}/inlines")
                if sibling is not None and sibling.evidence_ids != operation.evidence_ids:
                    raise ValueError("atomic RichText operations must cite identical evidence_ids")
                continue
            formula_pairs = (
                ("/source/value", "/representation"),
                ("/formula_source/value", "/formula_representation"),
            )
            for formula_suffix, representation_suffix in formula_pairs:
                if operation.path.endswith(formula_suffix):
                    sibling = by_path.get(
                        f"{operation.path[: -len(formula_suffix)]}{representation_suffix}"
                    )
                    if sibling is not None and sibling.evidence_ids != operation.evidence_ids:
                        raise ValueError(
                            "atomic formula operations must cite identical evidence_ids"
                        )
                    break
        return self


class AgentProposalIntentOutput(BaseModel):
    """Evidence-bound intent that the trusted backend materializes into a proposal."""

    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal["agent-proposal-intent-1.0"]
    domain: AgentDomain
    patch: tuple[AgentPatchIntentOperation, ...] = Field(min_length=1, max_length=5)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: tuple[AgentEvidenceReference, ...] = Field(min_length=1, max_length=20)
    alternatives: tuple[str, ...] = Field(min_length=1, max_length=10)
    reason: str = Field(min_length=20, max_length=2000)
    needs_human: bool

    @model_validator(mode="after")
    def intent_invariants(self) -> Self:
        if self.confidence < 0.85 and not self.needs_human:
            raise ValueError("low-confidence proposal intents must require human review")
        declared = [reference.evidence_id for reference in self.evidence]
        if len(declared) != len(set(declared)):
            raise ValueError("proposal intent evidence references must be unique")
        used = {operation.value_source.evidence_id for operation in self.patch}
        if used != set(declared):
            raise ValueError(
                "patch value_source must use every and only declared evidence reference"
            )
        return self


DOMAIN_PATH_PREFIXES: dict[AgentDomain, tuple[str, ...]] = {
    AgentDomain.METADATA: ("/front",),
    AgentDomain.CONTRIBUTORS: ("/front/contributors", "/front/affiliations"),
    AgentDomain.STRUCTURE: ("/body",),
    AgentDomain.REFERENCES: ("/back/references",),
    AgentDomain.FIGURES_TABLES: ("/body", "/assets"),
    AgentDomain.MATH_NOTES: ("/body", "/back/notes"),
}


def output_json_schema(domain: AgentDomain) -> dict[str, Any]:
    schema = AgentProposalOutput.model_json_schema()
    schema["$id"] = f"https://idml.local/schemas/agents/{domain.value}-proposal-1.1.json"
    schema["title"] = f"{domain.value} assistive proposal"
    schema["properties"]["domain"] = {"const": domain.value, "type": "string"}
    schema["additionalProperties"] = False
    return schema


def proposal_intent_json_schema(domain: AgentDomain) -> dict[str, Any]:
    schema = AgentProposalIntentOutput.model_json_schema()
    schema["$id"] = f"https://idml.local/schemas/agents/{domain.value}-intent-1.0.json"
    schema["title"] = f"{domain.value} evidence-bound proposal intent"
    schema["properties"]["domain"] = {"const": domain.value, "type": "string"}
    schema["additionalProperties"] = False
    return schema


def parse_agent_output(payload: dict[str, Any]) -> AgentProposalOutput:
    """Validate provider JSON while retaining strict Python-side models."""
    return AgentProposalOutput.model_validate_json(json.dumps(payload, ensure_ascii=False))


def parse_agent_intent(payload: dict[str, Any]) -> AgentProposalIntentOutput:
    """Validate a provider intent before trusted evidence materialization."""
    return AgentProposalIntentOutput.model_validate_json(json.dumps(payload, ensure_ascii=False))
