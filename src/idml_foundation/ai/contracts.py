from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from idml_foundation.ai.outputs import AgentDomain

READ_TOOLS = frozenset(
    {
        "idml_read_review_item",
        "idml_read_canonical_fragment",
        "idml_read_evidence",
        "idml_read_validation_issues",
    }
)
PROPOSAL_TOOLS = frozenset({"idml_propose_patch", "idml_validate_patch"})
ALLOWED_TOOLS = READ_TOOLS | PROPOSAL_TOOLS
FORBIDDEN_CAPABILITIES = frozenset(
    {
        "shell",
        "exec",
        "browser",
        "filesystem",
        "sql",
        "network",
        "release",
        "spawn",
    }
)


@dataclass(frozen=True)
class ToolScope:
    organization_id: str
    job_id: str | None
    resource_id: str
    review_item_id: str
    base_snapshot_id: str
    expected_review_version: int
    domain: AgentDomain


@dataclass(frozen=True)
class ToolResult:
    tool: str
    payload: dict[str, Any]
    content_sha256: str


def enforce_tool_allowlist(tools: frozenset[str]) -> None:
    unknown = tools - ALLOWED_TOOLS
    if unknown:
        raise PermissionError(f"tools are outside the assistive allowlist: {sorted(unknown)}")


def assert_no_forbidden_capabilities(capabilities: frozenset[str]) -> None:
    forbidden = capabilities & FORBIDDEN_CAPABILITIES
    if forbidden:
        raise PermissionError(f"forbidden agent capabilities requested: {sorted(forbidden)}")
