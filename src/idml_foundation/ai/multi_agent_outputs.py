from __future__ import annotations

import json
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from idml_foundation.ai.outputs import EvidenceId

CriticRole = Literal["xml_critic", "editorial_critic"]
CriticVerdict = Literal["pass", "reject", "abstain"]
FindingSeverity = Literal["blocker", "critical", "major", "minor", "info"]
AdjudicationDecision = Literal["accept", "reject", "abstain"]
Agreement = Literal[
    "unanimous_accept",
    "unanimous_reject",
    "mixed",
    "insufficient",
]
ReasonCode = Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]{2,79}$")]


class CriticFinding(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    code: ReasonCode
    severity: FindingSeverity
    message: str = Field(min_length=20, max_length=500)
    paths: tuple[str, ...] = Field(max_length=5)
    evidence_ids: tuple[EvidenceId, ...] = Field(
        max_length=20,
        json_schema_extra={"uniqueItems": True},
    )

    @model_validator(mode="after")
    def references_are_unique_and_scoped(self) -> Self:
        if len(self.paths) != len(set(self.paths)):
            raise ValueError("critic finding paths must be unique")
        if any(not path.startswith("/") for path in self.paths):
            raise ValueError("critic finding paths must be JSON pointers")
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("critic finding evidence_ids must be unique")
        return self


class CritiqueOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal["agent-critique-1.0"]
    role: CriticRole
    proposal_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    verdict: CriticVerdict
    confidence: float = Field(ge=0.0, le=1.0)
    findings: tuple[CriticFinding, ...] = Field(max_length=20)
    evidence_ids_considered: tuple[EvidenceId, ...] = Field(
        min_length=1,
        max_length=20,
        json_schema_extra={"uniqueItems": True},
    )
    summary: str = Field(min_length=20, max_length=1000)
    needs_human: Literal[True]

    @model_validator(mode="after")
    def critique_is_consistent(self) -> Self:
        if len(self.evidence_ids_considered) != len(set(self.evidence_ids_considered)):
            raise ValueError("critique evidence_ids_considered must be unique")
        severe = any(
            finding.severity in {"blocker", "critical", "major"} for finding in self.findings
        )
        if self.verdict == "reject" and not severe:
            raise ValueError("reject critique requires a blocker, critical, or major finding")
        if self.verdict == "pass" and severe:
            raise ValueError("pass critique cannot contain severe findings")
        if self.verdict == "abstain" and not self.findings:
            raise ValueError("abstain critique requires an explanatory finding")
        return self


class AdjudicationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal["agent-adjudication-1.0"]
    proposal_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    xml_critique_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    editorial_critique_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision: AdjudicationDecision
    agreement: Agreement
    false_consensus_risk: bool
    confidence: float = Field(ge=0.0, le=1.0)
    reason_codes: tuple[ReasonCode, ...] = Field(
        min_length=1,
        max_length=20,
        json_schema_extra={"uniqueItems": True},
    )
    summary: str = Field(min_length=20, max_length=1000)
    needs_human: Literal[True]

    @model_validator(mode="after")
    def adjudication_is_consistent(self) -> Self:
        if len(self.reason_codes) != len(set(self.reason_codes)):
            raise ValueError("adjudication reason_codes must be unique")
        if self.decision == "accept" and (
            self.agreement != "unanimous_accept"
            or self.false_consensus_risk
            or self.confidence < 0.85
        ):
            raise ValueError("accept adjudication requires strong unanimous agreement")
        if self.agreement == "insufficient" and self.decision != "abstain":
            raise ValueError("insufficient agreement must abstain")
        return self


def critique_json_schema(role: CriticRole) -> dict[str, Any]:
    schema = CritiqueOutput.model_json_schema()
    schema["$id"] = f"https://idml.local/schemas/agents/{role}-critique-1.0.json"
    schema["title"] = f"{role} structured critique"
    schema["properties"]["role"] = {"const": role, "type": "string"}
    schema["additionalProperties"] = False
    return schema


def adjudication_json_schema() -> dict[str, Any]:
    schema = AdjudicationOutput.model_json_schema()
    schema["$id"] = "https://idml.local/schemas/agents/adjudication-1.0.json"
    schema["title"] = "multi-agent structured adjudication"
    schema["additionalProperties"] = False
    return schema


def parse_critique(payload: dict[str, Any], *, role: CriticRole) -> CritiqueOutput:
    parsed = CritiqueOutput.model_validate_json(json.dumps(payload, ensure_ascii=False))
    if parsed.role != role:
        raise ValueError("critic role does not match the requested role")
    return parsed


def parse_adjudication(payload: dict[str, Any]) -> AdjudicationOutput:
    return AdjudicationOutput.model_validate_json(json.dumps(payload, ensure_ascii=False))
