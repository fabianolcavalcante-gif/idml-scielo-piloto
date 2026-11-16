from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from idml_foundation.ai.contracts import ToolResult, ToolScope
from idml_foundation.ai.evidence import evidence_reference as trusted_evidence_reference
from idml_foundation.ai.evidence import segment_evidence
from idml_foundation.ai.outputs import (
    DOMAIN_PATH_PREFIXES,
    AgentEvidenceReference,
    AgentProposalOutput,
    parse_agent_output,
)
from idml_foundation.ai.security import (
    contains_policy_override,
    payload_digest,
    redact_text,
    sanitize_untrusted,
)
from idml_foundation.models import DomainSnapshot, ReviewItem
from idml_foundation.pipeline.profile import load_profile
from idml_foundation.pipeline.validation import OfflineJatsValidator
from idml_foundation.schemas import JsonPatchOperation
from idml_foundation.services.reviews import validate_proposed_patch


def _segments(path: str) -> list[str]:
    if not path.startswith("/") or path == "/":
        raise ValueError("path must be a non-root JSON Pointer")
    parts = [part.replace("~1", "/").replace("~0", "~") for part in path[1:].split("/")]
    if any(not part for part in parts):
        raise ValueError("path contains an empty segment")
    return parts


def _pointer_value(payload: Any, path: str) -> Any:
    current = payload
    for segment in _segments(path):
        if isinstance(current, list):
            try:
                current = current[int(segment)]
            except (ValueError, IndexError) as exc:
                raise ValueError("path contains an invalid list index") from exc
        elif isinstance(current, dict) and segment in current:
            current = current[segment]
        else:
            raise ValueError("path does not exist")
    return current


def _atomic_rich_text_context(payload: dict[str, Any], path: str) -> dict[str, Any] | None:
    suffix = "/plain/value"
    if not path.endswith(suffix):
        return None
    root_path = path[: -len(suffix)]
    rich_text = _pointer_value(payload, root_path)
    if not (
        isinstance(rich_text, dict)
        and isinstance(rich_text.get("plain"), dict)
        and isinstance(rich_text.get("inlines"), list)
    ):
        return None
    compact_inlines = [
        {
            key: sanitize_untrusted(value)
            for key, value in inline.items()
            if key
            in {
                "id",
                "kind",
                "text",
                "target_id",
                "href",
                "name",
                "attributes",
                "evidence_ids",
            }
            and value not in (None, {}, [])
        }
        for inline in rich_text["inlines"]
        if isinstance(inline, dict)
    ]
    return {
        "root_path": root_path,
        "current_inlines": compact_inlines,
        "required_patch_paths": [path, f"{root_path}/inlines"],
    }


def _atomic_formula_context(payload: dict[str, Any], path: str) -> dict[str, Any] | None:
    suffix = "/source/value"
    if not path.endswith(suffix):
        return None
    root_path = path[: -len(suffix)]
    formula = _pointer_value(payload, root_path)
    if not (
        isinstance(formula, dict)
        and formula.get("kind") == "formula"
        and isinstance(formula.get("source"), dict)
        and "representation" in formula
    ):
        return None
    return {
        "root_path": root_path,
        "current_representation": sanitize_untrusted(formula["representation"]),
        "display": bool(formula.get("display")),
        "asset_id": sanitize_untrusted(formula.get("asset_id")),
        "required_patch_paths": [path, f"{root_path}/representation"],
        "allowed_target_representations": ["mathml"],
    }


def _source_kind(value: Any) -> str:
    normalized = str(value or "canonical").casefold().replace("_", "-")
    if normalized in {"idml", "pdf", "validation", "canonical"}:
        return normalized
    return "canonical"


def _normalize_evidence(item: ReviewItem) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for position, evidence in enumerate(item.evidence[:20]):
        evidence_id = str(evidence.get("evidence_id") or evidence.get("id") or position)
        locator_value = evidence.get("locator") or evidence.get("logical_path") or evidence
        locator = (
            locator_value
            if isinstance(locator_value, str)
            else json.dumps(locator_value, ensure_ascii=False, sort_keys=True)
        )
        raw_text = str(evidence.get("excerpt") or evidence.get("text") or "")
        excerpt = redact_text(raw_text, max_characters=len(raw_text) + 100)
        metadata = {
            "evidence_id": evidence_id[:200],
            "source_kind": _source_kind(evidence.get("source_kind") or evidence.get("source")),
            "locator": locator[:500],
        }
        if len(excerpt) <= 1_200:
            normalized.append(
                {
                    **metadata,
                    "excerpt": excerpt,
                    "excerpt_sha256": payload_digest(excerpt),
                }
            )
        else:
            normalized.append(
                segment_evidence(
                    evidence_id=metadata["evidence_id"],
                    source_kind=metadata["source_kind"],
                    locator=metadata["locator"],
                    text=excerpt,
                )
            )
    return normalized


class AgentToolService:
    """Tenant-bound tools with no shell, global filesystem, network, or free SQL."""

    def __init__(self, db: Session, scope: ToolScope) -> None:
        self.db = db
        self.scope = scope
        item = db.scalar(
            select(ReviewItem).where(
                ReviewItem.id == scope.review_item_id,
                ReviewItem.organization_id == scope.organization_id,
                ReviewItem.resource_id == scope.resource_id,
                ReviewItem.base_snapshot_id == scope.base_snapshot_id,
            )
        )
        if item is None:
            raise LookupError("review scope not found")
        if item.job_id != scope.job_id:
            raise PermissionError("job is outside the review scope")
        self.item: ReviewItem = item
        snapshot = db.scalar(
            select(DomainSnapshot).where(
                DomainSnapshot.id == scope.base_snapshot_id,
                DomainSnapshot.organization_id == scope.organization_id,
                DomainSnapshot.resource_id == scope.resource_id,
                DomainSnapshot.model_kind == "canonical",
            )
        )
        if snapshot is None:
            raise LookupError("snapshot scope not found")
        self.snapshot: DomainSnapshot = snapshot

    @staticmethod
    def _result(tool: str, payload: dict[str, Any]) -> ToolResult:
        return ToolResult(tool=tool, payload=payload, content_sha256=payload_digest(payload))

    def read_review_item(self) -> ToolResult:
        return self._result(
            "idml_read_review_item",
            {
                "review_item_id": self.item.id,
                "state": self.item.state,
                "version": self.item.version,
                "category": self.item.category,
                "rule_code": self.item.rule_code,
                "field_path": self.item.field_path,
                "message": sanitize_untrusted(self.item.message),
                "alternatives": sanitize_untrusted(self.item.alternatives),
            },
        )

    def read_canonical_fragment(self, path: str) -> ToolResult:
        if path != self.item.field_path and not path.startswith(f"{self.item.field_path}/"):
            raise PermissionError("canonical path is outside the review scope")
        value = _pointer_value(self.snapshot.payload, path)
        atomic_context = _atomic_rich_text_context(self.snapshot.payload, path)
        atomic_formula_context = _atomic_formula_context(self.snapshot.payload, path)
        payload: dict[str, Any] = {
            "snapshot_id": self.snapshot.id,
            "path": path,
            "value": sanitize_untrusted(value),
        }
        if atomic_context is not None:
            payload["atomic_rich_text"] = atomic_context
        if atomic_formula_context is not None:
            payload["atomic_formula"] = atomic_formula_context
        return self._result(
            "idml_read_canonical_fragment",
            payload,
        )

    def read_evidence(self) -> ToolResult:
        return self._result(
            "idml_read_evidence",
            {"review_item_id": self.item.id, "evidence": _normalize_evidence(self.item)},
        )

    def read_validation_issues(self) -> ToolResult:
        issues = [
            evidence
            for evidence in _normalize_evidence(self.item)
            if evidence["source_kind"] == "validation"
        ]
        return self._result(
            "idml_read_validation_issues",
            {"review_item_id": self.item.id, "issues": issues},
        )

    def validate_proposal(self, proposal: AgentProposalOutput) -> ToolResult:
        if proposal.domain != self.scope.domain:
            raise ValueError("proposal domain does not match the task")
        domain_prefixes = DOMAIN_PATH_PREFIXES[proposal.domain]
        for operation in proposal.patch:
            if not any(
                operation.path == prefix or operation.path.startswith(f"{prefix}/")
                for prefix in domain_prefixes
            ):
                raise ValueError("proposal path is outside the assisted domain")
        available_evidence = {
            evidence["evidence_id"]: evidence for evidence in _normalize_evidence(self.item)
        }
        for reference in proposal.evidence:
            expected = available_evidence.get(reference.evidence_id)
            if expected is None:
                raise ValueError("proposal cites evidence outside the review scope")
            observed_reference = reference.model_dump(
                mode="json", exclude_none=True, exclude_defaults=True
            )
            if observed_reference != trusted_evidence_reference(expected):
                raise ValueError("proposal evidence does not match the trusted locator")
        if contains_policy_override(
            {"reason": proposal.reason, "alternatives": proposal.alternatives}
        ):
            raise ValueError("proposal attempts to alter agent or release policy")
        patch = tuple(
            JsonPatchOperation.model_validate(operation.model_dump(mode="json"))
            for operation in proposal.patch
        )
        vendor = Path(__file__).resolve().parents[3] / "vendor" / "jats" / "1.3"
        validation = validate_proposed_patch(
            self.db,
            organization_id=self.scope.organization_id,
            item_id=self.scope.review_item_id,
            expected_version=self.scope.expected_review_version,
            patch=patch,
            profile=load_profile(),
            validator=OfflineJatsValidator(vendor),
        )
        return self._result("idml_validate_patch", validation)

    def propose_patch(self, raw_output: dict[str, Any]) -> tuple[AgentProposalOutput, ToolResult]:
        proposal = parse_agent_output(raw_output)
        return proposal, self.validate_proposal(proposal)


def evidence_reference(payload: dict[str, Any]) -> AgentEvidenceReference:
    return AgentEvidenceReference.model_validate(payload)
