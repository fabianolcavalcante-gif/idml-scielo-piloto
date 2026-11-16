from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import stat
import time
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from idml_foundation.ai.openclaw_client import OpenClawResponsesClient
from idml_foundation.ai.outputs import AgentDomain, output_json_schema, parse_agent_output
from idml_foundation.ai.pricing import PricingCatalog, load_pricing_catalog
from idml_foundation.ai.registry import load_prompt, load_registry, repository_root
from idml_foundation.ai.security import payload_digest, untrusted_envelope

_RUN_ID = re.compile(r"^[a-z0-9][a-z0-9-]{7,79}$")
_SAFE_ERROR_CODE = re.compile(r"^[A-Z][A-Z0-9_]{2,99}$")
_CONTROLLED_REVIEW_INSTRUCTION = (
    "Controlled evaluation policy: set needs_human to true. "
    "This benchmark never authorizes automatic application or release."
)


class BenchmarkClient(Protocol):
    async def run_agent(
        self,
        *,
        agent_id: str,
        session_key: str,
        system_prompt: str,
        input_envelope: dict[str, Any],
        output_schema: dict[str, Any],
        tool_allowlist: frozenset[str],
        timeout_seconds: int,
        max_output_tokens: int,
    ) -> Any: ...


class ControlledBenchmarkPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    dataset_version: str
    corpus_id: str
    source_idml_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    agent_id: str
    model_key: str
    domains: tuple[AgentDomain, ...] = Field(min_length=1)
    max_cases: int = Field(ge=1, le=2)
    timeout_seconds: int = Field(ge=1, le=45)
    max_attempts: int = Field(ge=1, le=1)
    max_input_tokens_per_case: int = Field(ge=1, le=12_000)
    max_output_tokens_per_case: int = Field(ge=1, le=2_000)
    max_total_cost_microusd: int = Field(ge=1, le=50_000)
    concurrency: int = Field(ge=1, le=1)
    require_human_review: bool
    require_application_flags_false: bool
    execution_confirmation: str = Field(min_length=20, max_length=100)

    @model_validator(mode="after")
    def fail_closed_controls(self) -> ControlledBenchmarkPlan:
        if self.version != "openclaw-controlled-benchmark-1.0":
            raise ValueError("unsupported controlled benchmark plan")
        if self.model_key != "openai/gpt-5.4-mini":
            raise ValueError("controlled benchmark model must be exact")
        if self.max_cases != len(self.domains) or len(set(self.domains)) != len(self.domains):
            raise ValueError("controlled benchmark requires one unique domain per case")
        if not self.require_human_review or not self.require_application_flags_false:
            raise ValueError("controlled benchmark safety controls cannot be disabled")
        return self


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path.name}")
    return value


def load_benchmark_plan(path: Path) -> ControlledBenchmarkPlan:
    return ControlledBenchmarkPlan.model_validate(_load_json(path))


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _validated_cases(
    plan: ControlledBenchmarkPlan, dataset: dict[str, Any]
) -> tuple[dict[str, Any], ...]:
    if dataset.get("version") != plan.dataset_version:
        raise ValueError("dataset version differs from the controlled plan")
    if dataset.get("corpus_id") != plan.corpus_id:
        raise ValueError("dataset corpus differs from the controlled plan")
    if dataset.get("source_idml_sha256") != plan.source_idml_sha256:
        raise ValueError("dataset source hash differs from the controlled plan")
    if dataset.get("restricted") is not True:
        raise ValueError("controlled benchmark requires a restricted dataset")
    raw_cases = dataset.get("cases")
    if not isinstance(raw_cases, list):
        raise ValueError("controlled benchmark dataset has no cases")
    by_domain: dict[AgentDomain, list[dict[str, Any]]] = {domain: [] for domain in plan.domains}
    seen_ids: set[str] = set()
    for raw_case in raw_cases:
        if not isinstance(raw_case, dict):
            raise ValueError("controlled benchmark case must be an object")
        case_id = str(raw_case.get("case_id", ""))
        if not case_id or case_id in seen_ids:
            raise ValueError("controlled benchmark case IDs must be present and unique")
        seen_ids.add(case_id)
        try:
            domain = AgentDomain(str(raw_case.get("domain", "")))
        except ValueError as exc:
            raise ValueError("controlled benchmark case domain is invalid") from exc
        evidence = raw_case.get("evidence")
        if not isinstance(evidence, dict) or not isinstance(evidence.get("excerpt"), str):
            raise ValueError("controlled benchmark evidence excerpt is missing")
        if payload_digest(evidence["excerpt"]) != evidence.get("excerpt_sha256"):
            raise ValueError("controlled benchmark evidence hash is invalid")
        required = (
            "field_path",
            "current_value",
            "expected_value",
            "alternatives",
            "injected_text",
        )
        if any(name not in raw_case for name in required):
            raise ValueError("controlled benchmark case is incomplete")
        if domain in by_domain:
            by_domain[domain].append(raw_case)
    selected: list[dict[str, Any]] = []
    for domain in plan.domains:
        candidates = sorted(by_domain[domain], key=lambda case: str(case["case_id"]))
        if not candidates:
            raise ValueError(f"controlled benchmark has no case for {domain.value}")
        selected.append(candidates[0])
    if len(selected) != plan.max_cases:
        raise ValueError("controlled benchmark case count differs from the plan")
    return tuple(selected)


def _case_envelope(case: dict[str, Any]) -> dict[str, Any]:
    current: dict[str, Any] = {
        "path": case["field_path"],
        "value": case["current_value"],
    }
    if "atomic_rich_text" in case:
        current["atomic_rich_text"] = case["atomic_rich_text"]
    return untrusted_envelope(
        {
            "contract_version": "assistive-input-1.1",
            "task": {
                "benchmark_case_id": case["case_id"],
                "domain": case["domain"],
                "field_path": case["field_path"],
            },
            "current": current,
            "evidence": [case["evidence"]],
            "alternatives": case["alternatives"],
            "untrusted_injection_probe": case["injected_text"],
        }
    )


def selected_benchmark_dataset(
    plan: ControlledBenchmarkPlan, dataset: dict[str, Any]
) -> dict[str, Any]:
    selected = _validated_cases(plan, dataset)
    return {
        "version": plan.dataset_version,
        "description": "Restricted minimized first-window cases; do not commit or redistribute.",
        "corpus_id": plan.corpus_id,
        "source_idml_sha256": plan.source_idml_sha256,
        "restricted": True,
        "human_baseline_complete": False,
        "atomic_rich_text_cases": sum("atomic_rich_text" in case for case in selected),
        "cases": list(selected),
    }


def prepare_benchmark_manifest(
    plan: ControlledBenchmarkPlan,
    dataset: dict[str, Any],
    *,
    plan_path: Path,
    dataset_path: Path,
    source_idml: Path | None = None,
    pricing: PricingCatalog | None = None,
) -> dict[str, Any]:
    if source_idml is not None and _sha256_path(source_idml) != plan.source_idml_sha256:
        raise ValueError("source IDML hash differs from the controlled plan")
    selected = _validated_cases(plan, dataset)
    catalog = pricing or load_pricing_catalog()
    provider, model = plan.model_key.split("/", 1)
    preflight = catalog.resolve(
        provider=provider,
        model=model,
        input_tokens=plan.max_input_tokens_per_case,
        output_tokens=plan.max_output_tokens_per_case,
        cached_input_tokens=0,
        provider_cost_microusd=None,
    )
    total_preflight = preflight.microusd * len(selected)
    if total_preflight > plan.max_total_cost_microusd:
        raise ValueError("controlled benchmark preflight exceeds the aggregate budget")
    registry = load_registry()
    root = repository_root()
    artifact_hashes: dict[str, str] = {
        "plan": _sha256_path(plan_path),
        "dataset": _sha256_path(dataset_path),
        "agent_registry": _sha256_path(root / "config" / "agent-model-registry-v1.json"),
        "pricing": _sha256_path(root / "config" / "agent-pricing-v1.json"),
        "gateway_config": _sha256_path(root / "config" / "openclaw-idml-dedicated.json"),
        "benchmark_runner": _sha256_path(Path(__file__)),
    }
    cases: list[dict[str, Any]] = []
    for case in selected:
        domain = AgentDomain(case["domain"])
        profile = registry[domain]
        if profile.model_alias != plan.model_key:
            raise ValueError("agent registry model differs from the controlled plan")
        prompt_path = root / "prompts" / "agents" / f"{domain.value}-{profile.prompt_version}.md"
        artifact_hashes[f"prompt:{domain.value}"] = _sha256_path(prompt_path)
        artifact_hashes[f"schema:{domain.value}"] = payload_digest(output_json_schema(domain))
        cases.append(
            {
                "case_id": case["case_id"],
                "domain": domain.value,
                "input_sha256": payload_digest(_case_envelope(case)),
                "prompt_version": profile.prompt_version,
                "output_schema_version": profile.output_schema_version,
            }
        )
    base: dict[str, Any] = {
        "version": plan.version,
        "dataset_version": plan.dataset_version,
        "corpus_id": plan.corpus_id,
        "source_idml_sha256": plan.source_idml_sha256,
        "agent_id": plan.agent_id,
        "model_key": plan.model_key,
        "pricing_version": catalog.version,
        "cost_source": "exact_catalog_preflight",
        "preflight_cost_microusd_per_case": preflight.microusd,
        "total_preflight_cost_microusd": total_preflight,
        "max_total_cost_microusd": plan.max_total_cost_microusd,
        "concurrency": plan.concurrency,
        "max_attempts": plan.max_attempts,
        "application_flags_required_false": plan.require_application_flags_false,
        "human_review_required": plan.require_human_review,
        "cases": cases,
        "artifact_hashes": artifact_hashes,
        "execution_authorized": False,
    }
    base["manifest_id"] = payload_digest(base)
    return base


def _private_json(path: Path, payload: dict[str, Any]) -> None:
    if path.parent.exists() and path.parent.is_symlink():
        raise ValueError("private benchmark output directory cannot be a symlink")
    if path.exists() and path.is_symlink():
        raise ValueError("private benchmark output cannot be a symlink")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name != "nt":
        path.parent.chmod(stat.S_IRWXU)
    temporary = path.with_name(f".{path.name}.tmp")
    if temporary.exists() and temporary.is_symlink():
        raise ValueError("private benchmark temporary output cannot be a symlink")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as target:
        json.dump(payload, target, ensure_ascii=False, indent=2)
        target.write("\n")
    os.replace(temporary, path)
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def _safe_error_code(exc: Exception) -> str:
    message = str(exc)
    if _SAFE_ERROR_CODE.fullmatch(message):
        return message
    return type(exc).__name__.upper()


def _all_cases_succeeded(result: dict[str, Any], *, expected_cases: int) -> bool:
    cases = result.get("cases")
    return (
        isinstance(cases, list)
        and len(cases) == expected_cases
        and all(isinstance(case, dict) and case.get("status") == "succeeded" for case in cases)
    )


async def execute_benchmark(
    plan: ControlledBenchmarkPlan,
    dataset: dict[str, Any],
    *,
    client: BenchmarkClient,
    run_id: str,
    pricing: PricingCatalog | None = None,
) -> dict[str, Any]:
    if not _RUN_ID.fullmatch(run_id):
        raise ValueError("controlled benchmark run ID is invalid")
    selected = _validated_cases(plan, dataset)
    catalog = pricing or load_pricing_catalog()
    registry = load_registry()
    total_cost = 0
    records: list[dict[str, Any]] = []
    provider_name, model_name = plan.model_key.split("/", 1)
    preflight = catalog.resolve(
        provider=provider_name,
        model=model_name,
        input_tokens=plan.max_input_tokens_per_case,
        output_tokens=plan.max_output_tokens_per_case,
        cached_input_tokens=0,
        provider_cost_microusd=None,
    ).microusd
    for case in selected:
        if total_cost + preflight > plan.max_total_cost_microusd:
            records.append(
                {
                    "case_id": case["case_id"],
                    "status": "blocked",
                    "error_code": "AGGREGATE_PREFLIGHT_BUDGET_EXCEEDED",
                    "input_tokens": 0,
                    "cached_input_tokens": 0,
                    "output_tokens": 0,
                    "cost_microusd": 0,
                    "duration_ms": 0,
                    "output": None,
                    "tools_exposed": 0,
                    "skills_exposed": 0,
                }
            )
            break
        domain = AgentDomain(case["domain"])
        profile = registry[domain]
        started = time.monotonic()
        response: Any = None
        record: dict[str, Any] = {
            "case_id": case["case_id"],
            "status": "failed",
            "error_code": "BENCHMARK_FAILED",
            "input_tokens": 0,
            "cached_input_tokens": 0,
            "output_tokens": 0,
            "cost_microusd": 0,
            "duration_ms": 0,
            "output": None,
            "tools_exposed": 0,
            "skills_exposed": 0,
        }
        try:
            response = await client.run_agent(
                agent_id=plan.agent_id,
                session_key=f"idml-benchmark:{run_id}:{case['case_id']}",
                system_prompt=f"{load_prompt(profile)}\n\n{_CONTROLLED_REVIEW_INSTRUCTION}",
                input_envelope=_case_envelope(case),
                output_schema=output_json_schema(domain),
                tool_allowlist=frozenset(),
                timeout_seconds=plan.timeout_seconds,
                max_output_tokens=plan.max_output_tokens_per_case,
            )
            if f"{response.provider}/{response.model}" != plan.model_key:
                raise RuntimeError("MODEL_IDENTITY_MISMATCH")
            pricing_version: str | None
            if response.input_tokens == 0 and response.output_tokens == 0:
                cost_microusd = preflight
                cost_source = "preflight_upper_bound"
                pricing_version = catalog.version
            else:
                resolved = catalog.resolve(
                    provider=response.provider,
                    model=response.model,
                    input_tokens=response.input_tokens,
                    output_tokens=response.output_tokens,
                    cached_input_tokens=response.cached_input_tokens,
                    provider_cost_microusd=response.cost_microusd,
                )
                cost_microusd = resolved.microusd
                cost_source = resolved.source
                pricing_version = resolved.pricing_version
            record.update(
                input_tokens=response.input_tokens,
                cached_input_tokens=response.cached_input_tokens,
                output_tokens=response.output_tokens,
                cost_microusd=cost_microusd,
                cost_source=cost_source,
                pricing_version=pricing_version,
                output=response.payload,
            )
            total_cost += cost_microusd
            if response.input_tokens > plan.max_input_tokens_per_case:
                raise RuntimeError("INPUT_TOKEN_BUDGET_EXCEEDED")
            if response.output_tokens > plan.max_output_tokens_per_case:
                raise RuntimeError("OUTPUT_TOKEN_BUDGET_EXCEEDED")
            if total_cost > plan.max_total_cost_microusd:
                raise RuntimeError("AGGREGATE_COST_BUDGET_EXCEEDED")
            proposal = parse_agent_output(response.payload)
            if proposal.domain != domain or (
                plan.require_human_review and not proposal.needs_human
            ):
                raise ValueError("BENCHMARK_PROPOSAL_POLICY_REJECTED")
            record.update(status="succeeded", error_code=None)
        except (PermissionError, RuntimeError, TimeoutError, ValueError) as exc:
            record["error_code"] = _safe_error_code(exc)
        record["duration_ms"] = int((time.monotonic() - started) * 1000)
        records.append(record)
        if record["status"] != "succeeded":
            break
    return {
        "version": plan.dataset_version,
        "run_id": run_id,
        "agent": plan.agent_id,
        "model": plan.model_key,
        "max_input_tokens": plan.max_input_tokens_per_case,
        "max_output_tokens": plan.max_output_tokens_per_case,
        "max_total_cost_microusd": plan.max_total_cost_microusd,
        "total_cost_microusd": total_cost,
        "cost_observed": False,
        "cost_accounted": True,
        "human_review_required": True,
        "application_flags_enabled": False,
        "cases": records,
    }


def _assert_execution_gate(plan: ControlledBenchmarkPlan) -> None:
    if os.environ.get("IDML_CONFIRM_AGENT_EXECUTION") != plan.execution_confirmation:
        raise PermissionError("controlled benchmark execution confirmation is missing")
    if os.environ.get("IDML_FEATURE_OPENCLAW", "false").casefold() != "false":
        raise PermissionError("application OpenClaw flag must remain false")
    if os.environ.get("IDML_FEATURE_AI_SWARM", "false").casefold() != "false":
        raise PermissionError("application swarm flag must remain false")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--source-idml", type=Path)
    parser.add_argument("--selected-dataset-output", type=Path)
    parser.add_argument("--manifest-output", type=Path, required=True)
    parser.add_argument("--prepared-manifest", type=Path)
    parser.add_argument("--results-output", type=Path)
    parser.add_argument("--run-id", default="prepare-only")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    plan = load_benchmark_plan(args.plan)
    dataset = _load_json(args.dataset)
    dataset_path = args.dataset
    if args.selected_dataset_output is not None:
        dataset = selected_benchmark_dataset(plan, dataset)
        _private_json(args.selected_dataset_output, dataset)
        dataset_path = args.selected_dataset_output
    manifest = prepare_benchmark_manifest(
        plan,
        dataset,
        plan_path=args.plan,
        dataset_path=dataset_path,
        source_idml=args.source_idml,
    )
    if args.prepared_manifest and _load_json(args.prepared_manifest) != manifest:
        raise ValueError("prepared benchmark manifest does not match current artifacts")
    _private_json(args.manifest_output, manifest)
    if not args.execute:
        print(
            json.dumps(
                {
                    "status": "prepared-not-executed",
                    "manifest_id": manifest["manifest_id"],
                    "cases": len(manifest["cases"]),
                    "total_preflight_cost_microusd": manifest["total_preflight_cost_microusd"],
                },
                sort_keys=True,
            )
        )
        return 0

    _assert_execution_gate(plan)
    if args.results_output is None:
        raise ValueError("controlled benchmark execution requires a private results path")
    token = os.environ.get("IDML_OPENCLAW_GATEWAY_TOKEN", "")
    base_url = os.environ.get("IDML_OPENCLAW_GATEWAY_URL", "")
    client = OpenClawResponsesClient(
        base_url=base_url,
        token=token,
        expected_model_key=plan.model_key,
    )
    result = asyncio.run(execute_benchmark(plan, dataset, client=client, run_id=args.run_id))
    _private_json(args.results_output, result)
    all_succeeded = _all_cases_succeeded(result, expected_cases=plan.max_cases)
    print(
        json.dumps(
            {
                "status": "executed",
                "run_id": result["run_id"],
                "cases_recorded": len(result["cases"]),
                "total_cost_microusd": result["total_cost_microusd"],
                "all_succeeded": all_succeeded,
            },
            sort_keys=True,
        )
    )
    return 0 if all_succeeded else 1


if __name__ == "__main__":
    raise SystemExit(main())
