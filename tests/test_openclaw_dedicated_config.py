import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "openclaw-idml-dedicated.json"
COMPOSE_PATH = ROOT / "deploy" / "docker-compose.dev.yml"
PROVIDER_COMPOSE_PATH = ROOT / "deploy" / "docker-compose.openclaw-provider.yml"
BENCHMARK_COMPOSE_PATH = ROOT / "deploy" / "docker-compose.openclaw-benchmark.yml"


def test_dedicated_openclaw_config_has_a_single_inert_agent() -> None:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    assert config["meta"]["lastTouchedVersion"] == "2026.6.11"
    assert config["env"]["shellEnv"]["enabled"] is False
    assert config["plugins"]["enabled"] is False
    assert config["skills"]["allowBundled"] == []

    agents = config["agents"]["list"]
    assert [agent["id"] for agent in agents] == ["idml-evaluator"]
    assert agents[0]["model"] == {
        "primary": "openai/gpt-5.4-mini",
        "fallbacks": [],
    }
    assert agents[0]["tools"]["allow"] == []
    assert agents[0]["tools"]["deny"] == ["*"]
    assert agents[0]["skills"] == []
    assert config["agents"]["defaults"]["heartbeat"]["every"] == "0m"
    assert agents[0]["heartbeat"]["every"] == "0m"
    heartbeat = (ROOT / "openclaw" / "idml-evaluator-workspace" / "HEARTBEAT.md").read_text(
        encoding="utf-8"
    )
    assert heartbeat.strip() == "# Heartbeat disabled"


def test_dedicated_openclaw_exposes_only_the_required_http_endpoint() -> None:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    gateway = config["gateway"]
    endpoints = gateway["http"]["endpoints"]

    assert gateway["mode"] == "local"
    assert gateway["bind"] == "lan"
    assert gateway["controlUi"]["enabled"] is False
    assert endpoints["responses"]["enabled"] is True
    assert endpoints["responses"]["maxUrlParts"] == 0
    assert endpoints["responses"]["files"]["allowUrl"] is False
    assert endpoints["responses"]["images"]["allowUrl"] is False
    assert endpoints["chatCompletions"]["enabled"] is False
    assert gateway["auth"]["mode"] == "token"
    assert "token" not in gateway["auth"]
    assert "secrets" not in config


def test_openai_provider_is_pinned_and_forced_through_the_proxy() -> None:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    provider = config["models"]["providers"]["openai"]

    assert config["models"]["mode"] == "replace"
    assert provider["baseUrl"] == "https://api.openai.com/v1"
    assert provider["api"] == "openai-responses"
    assert provider["auth"] == "api-key"
    assert provider["agentRuntime"] == {"id": "openclaw"}
    assert provider["request"] == {"allowPrivateNetwork": False}
    assert "apiKey" not in provider
    assert provider["models"] == [
        {
            "id": "gpt-5.4-mini",
            "name": "GPT-5.4 Mini",
            "reasoning": True,
            "input": ["text", "image"],
            "cost": {
                "input": 0.75,
                "output": 4.5,
                "cacheRead": 0.075,
                "cacheWrite": 0,
            },
            "contextWindow": 400000,
            "contextTokens": 32000,
            "maxTokens": 4000,
        }
    ]


def test_dedicated_openclaw_compose_is_private_and_has_no_provider_key() -> None:
    compose = COMPOSE_PATH.read_text(encoding="utf-8")
    service = compose.split("  openclaw-idml:\n", maxsplit=1)[1].split("\n  api:\n", maxsplit=1)[0]

    assert "ghcr.io/openclaw/openclaw@sha256:" in service
    assert "OPENCLAW_GATEWAY_TOKEN:" in service
    assert "OPENAI_API_KEY" not in service
    assert "ports:" not in service
    assert "read_only: true" in service
    assert "cap_drop:" in service
    assert "- idml_openclaw" in service
    assert "internal: true" in compose.split("  idml_openclaw:\n", maxsplit=1)[1]


def test_provider_overlay_uses_a_separate_allowlisted_proxy() -> None:
    overlay = PROVIDER_COMPOSE_PATH.read_text(encoding="utf-8")
    proxy_config = (ROOT / "config" / "squid-openai.conf").read_text(encoding="utf-8")
    dockerfile = (ROOT / "deploy" / "Dockerfile.openclaw-egress-proxy").read_text(encoding="utf-8")

    assert "OPENAI_API_KEY: ${IDML_OPENAI_API_KEY:?" in overlay
    assert 'NODE_USE_ENV_PROXY: "1"' in overlay
    assert "HTTPS_PROXY: http://openclaw-egress-proxy:3128" in overlay
    assert "ports:" not in overlay
    assert "/proc/net/tcp6" in overlay
    assert "squidclient" not in overlay
    assert "- idml_openclaw_provider" in overlay
    assert "- idml_openclaw_egress" in overlay
    assert "internal: true" in overlay
    assert "FROM alpine:3.21@sha256:" in dockerfile
    assert "squid=6.12-r0" in dockerfile
    assert "acl openai_api dstdomain api.openai.com" in proxy_config
    assert "http_access allow CONNECT openai_api" in proxy_config
    assert proxy_config.index("http_access allow CONNECT openai_api") < proxy_config.index(
        "http_access deny all"
    )

    stage_script = (ROOT / "ops" / "openclaw-provider-stage.sh").read_text(encoding="utf-8")
    disable_script = (ROOT / "ops" / "openclaw-provider-disable.sh").read_text(encoding="utf-8")
    assert "trap fail_closed EXIT" in stage_script
    assert '"$disable_script"' in stage_script
    assert "configured OpenAI model is not image-capable" in stage_script
    assert "docker rm -f idml-development-openclaw-egress-proxy-1" in disable_script
    assert "docker network rm idml_development_openclaw_provider" in disable_script
    assert "docker network rm idml_development_openclaw_egress" in disable_script


def test_controlled_benchmark_runner_is_private_and_double_gated() -> None:
    overlay = BENCHMARK_COMPOSE_PATH.read_text(encoding="utf-8")
    runner = (ROOT / "ops" / "openclaw-controlled-benchmark.sh").read_text(encoding="utf-8")
    plan = json.loads(
        (ROOT / "config" / "openclaw-controlled-benchmark-v1.json").read_text(encoding="utf-8")
    )

    assert "ports:" not in overlay
    assert 'IDML_FEATURE_OPENCLAW: "false"' in overlay
    assert 'IDML_FEATURE_AI_SWARM: "false"' in overlay
    assert "/benchmark/input:ro" in overlay
    assert "cap_drop:" in overlay
    assert 'profiles: ["benchmark"]' in overlay
    assert "RUN_IDML_OPENCLAW_BENCHMARK_V1" in runner
    assert "IDML_RESET_OPENCLAW_STATE=true" in runner
    assert "openclaw-provider-stage.sh" in runner
    assert "openclaw-provider-disable.sh" in runner
    assert plan["max_cases"] == 2
    assert plan["domains"] == ["metadata", "references"]
    assert plan["max_attempts"] == 1
    assert plan["max_total_cost_microusd"] == 50_000


def test_real_domain_multi_agent_lab_is_private_and_double_gated() -> None:
    runner = (ROOT / "ops" / "openclaw-multi-agent-lab.sh").read_text(encoding="utf-8")
    plan = json.loads(
        (ROOT / "config" / "openclaw-multi-agent-lab-v9.json").read_text(encoding="utf-8")
    )

    assert "dataset-real-domains-v1.0.json" in runner
    assert "multi-agent-manifest-v9.json" in runner
    assert "RUN_IDML_OPENCLAW_MULTI_AGENT_LAB_V9" in runner
    assert plan["dataset_version"] == "idml-agent-real-domain-eval-1.0"
    assert plan["selected_case_ids"] == [
        "esa-structure-derived-001",
        "esa-math-notes-observed-001",
    ]
    assert plan["max_attempts"] == 1
    assert plan["max_total_cost_microusd"] == 117_000
    assert plan["require_human_review"] is True
    assert plan["require_application_flags_false"] is True


def test_atomic_mathml_multi_agent_lab_is_private_and_budgeted() -> None:
    runner = (ROOT / "ops" / "openclaw-multi-agent-lab.sh").read_text(encoding="utf-8")
    plan = json.loads(
        (ROOT / "config" / "openclaw-multi-agent-lab-v10.json").read_text(encoding="utf-8")
    )

    assert "dataset-real-domains-v1.1.json" in runner
    assert "multi-agent-manifest-v10.json" in runner
    assert "RUN_IDML_OPENCLAW_MULTI_AGENT_LAB_V10" in runner
    assert plan["dataset_version"] == "idml-agent-real-domain-eval-1.1"
    assert plan["selected_case_ids"] == ["esa-math-notes-observed-001"]
    assert plan["max_attempts"] == 1
    assert plan["max_total_cost_microusd"] == 58_500
    assert plan["require_human_review"] is True
    assert plan["require_application_flags_false"] is True


def test_visual_mathml_multi_agent_lab_is_private_and_budgeted() -> None:
    runner = (ROOT / "ops" / "openclaw-multi-agent-lab.sh").read_text(encoding="utf-8")
    plan = json.loads(
        (ROOT / "config" / "openclaw-multi-agent-lab-v11.json").read_text(encoding="utf-8")
    )

    assert "dataset-real-domains-visual-v1.1.json" in runner
    assert "multi-agent-manifest-v11.json" in runner
    assert "RUN_IDML_OPENCLAW_MULTI_AGENT_LAB_V11" in runner
    assert plan["selected_case_ids"] == [
        "esa-math-notes-observed-001",
        "esa-math-notes-inline-001",
        "esa-math-notes-inline-002",
    ]
    assert plan["max_attempts"] == 1
    assert plan["max_total_cost_microusd"] == 175_500
    assert plan["require_human_review"] is True
    assert plan["require_application_flags_false"] is True


def test_semantic_repair_lab_is_bounded_private_and_double_gated() -> None:
    runner = (ROOT / "ops" / "openclaw-multi-agent-lab.sh").read_text(encoding="utf-8")
    plan = json.loads(
        (ROOT / "config" / "openclaw-multi-agent-lab-v14.json").read_text(encoding="utf-8")
    )

    assert "multi-agent-manifest-v14.json" in runner
    assert "RUN_IDML_OPENCLAW_MULTI_AGENT_LAB_V14" in runner
    assert plan["selected_case_ids"] == [
        "esa-math-notes-observed-001",
        "esa-math-notes-inline-001",
        "esa-math-notes-inline-002",
    ]
    assert plan["max_attempts"] == 2
    assert plan["max_repair_cycles"] == 2
    assert plan["thinking_level"] == "medium"
    assert plan["max_total_cost_microusd"] == 600_000
    assert plan["require_human_review"] is True
    assert plan["require_application_flags_false"] is True
    dedicated = json.loads((ROOT / "config" / "openclaw-idml-dedicated.json").read_text())
    evaluator = next(
        agent for agent in dedicated["agents"]["list"] if agent["id"] == "idml-evaluator"
    )
    assert evaluator["thinkingDefault"] == "medium"


def test_complete_visual_formula_lab_covers_remaining_display_equations() -> None:
    runner = (ROOT / "ops" / "openclaw-multi-agent-lab.sh").read_text(encoding="utf-8")
    plan = json.loads(
        (ROOT / "config" / "openclaw-multi-agent-lab-v15.json").read_text(encoding="utf-8")
    )

    assert "dataset-real-domains-visual-v1.2.json" in runner
    assert "multi-agent-manifest-v15.json" in runner
    assert "RUN_IDML_OPENCLAW_MULTI_AGENT_LAB_V15" in runner
    assert plan["dataset_version"] == "idml-agent-real-domain-eval-1.2"
    second_plan = json.loads(
        (ROOT / "config" / "openclaw-multi-agent-lab-v16.json").read_text(encoding="utf-8")
    )
    assert "multi-agent-manifest-v16.json" in runner
    assert "RUN_IDML_OPENCLAW_MULTI_AGENT_LAB_V16" in runner
    assert plan["selected_case_ids"] + second_plan["selected_case_ids"] == [
        f"esa-math-notes-observed-{index:03d}" for index in range(2, 16)
    ]
    assert plan["max_attempts"] == 2
    assert plan["max_repair_cycles"] == 2
    assert plan["require_hidden_gold_equivalence"] is False
    assert plan["thinking_level"] == "medium"
    assert plan["max_total_cost_microusd"] == 1_500_000
    assert plan["require_human_review"] is True
    assert plan["require_application_flags_false"] is True
    assert second_plan["dataset_version"] == "idml-agent-real-domain-eval-1.2"
    assert second_plan["max_attempts"] == 2
    assert second_plan["max_repair_cycles"] == 2
    assert second_plan["require_hidden_gold_equivalence"] is False
    assert second_plan["thinking_level"] == "medium"
    assert second_plan["max_total_cost_microusd"] == 1_500_000
    assert second_plan["require_human_review"] is True
    assert second_plan["require_application_flags_false"] is True
