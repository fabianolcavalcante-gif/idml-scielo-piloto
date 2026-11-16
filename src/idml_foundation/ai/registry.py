from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from idml_foundation.ai.outputs import AgentDomain


@dataclass(frozen=True)
class AgentProfile:
    domain: AgentDomain
    prompt_version: str
    output_schema_version: str
    config_version: str
    model_alias: str
    confidence_threshold: float
    max_repair_cycles: int


def repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def load_registry(path: Path | None = None) -> dict[AgentDomain, AgentProfile]:
    registry_path = path or repository_root() / "config" / "agent-model-registry-v1.json"
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    if payload.get("version") != "agent-config-1.5":
        raise ValueError("unsupported agent registry version")
    profiles: dict[AgentDomain, AgentProfile] = {}
    for key, value in payload["domains"].items():
        domain = AgentDomain(key)
        model_alias = str(value["model_alias"])
        provider, separator, model = model_alias.partition("/")
        if not separator or not provider or not model or model_alias != model_alias.casefold():
            raise ValueError("agent model alias must be exact provider/model")
        profiles[domain] = AgentProfile(
            domain=domain,
            prompt_version=value["prompt_version"],
            output_schema_version=value["output_schema_version"],
            config_version=payload["version"],
            model_alias=model_alias,
            confidence_threshold=float(value["confidence_threshold"]),
            max_repair_cycles=int(value["max_repair_cycles"]),
        )
    if set(profiles) != set(AgentDomain):
        raise ValueError("agent registry must define every supported domain")
    return profiles


def load_prompt(profile: AgentProfile, root: Path | None = None) -> str:
    prompt_root = root or repository_root() / "prompts" / "agents"
    path = prompt_root / f"{profile.domain.value}-{profile.prompt_version}.md"
    return path.read_text(encoding="utf-8")
