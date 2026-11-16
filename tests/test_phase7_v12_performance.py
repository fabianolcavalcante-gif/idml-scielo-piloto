import time

import pytest

from idml_foundation.pipeline.service import DeterministicPipeline
from ops.benchmark_phase7_v12 import fixture, measure, percentile
from ops.gate_phase7_v12 import evaluate
from ops.observe_phase7_v12 import violations


def healthy_sample():
    return {
        "memory_available_bytes": 1024**3,
        "disk_used_percent": 84,
        "disk_free_bytes": 15 * 1024**3,
        "ready": True,
        "ready_ms": 10,
        "cpu_total": 100,
        "cpu_idle": 80,
    }


@pytest.mark.parametrize(
    ("key", "value", "code"),
    [
        ("memory_available_bytes", 511 * 1024**2, "memory_reserve"),
        ("disk_used_percent", 90, "disk_reserve"),
        ("disk_free_bytes", 1024**3, "disk_reserve"),
        ("ready", False, "readiness_degradation"),
        ("ready_ms", 501, "readiness_degradation"),
        ("cpu_idle", 0, "host_cpu_pressure"),
        ("cpu_total", 0, "invalid_cpu_sample"),
    ],
)
def test_capacity_watchdog_fails_closed(key, value, code):
    current = healthy_sample()
    current[key] = value
    assert code in violations(current, {"cpu_total": 0, "cpu_idle": 0}, ready_limit_ms=500)


def test_capacity_watchdog_allows_healthy_baseline():
    assert violations(healthy_sample(), None, ready_limit_ms=500) == []


def test_nearest_rank_percentile_and_empty_samples():
    assert percentile(list(range(1, 101))) == 95
    with pytest.raises(ValueError):
        percentile([])


def test_synthetic_benchmark_preserves_output_and_records_queue():
    source = fixture(16)
    assert source == fixture(16)
    first = measure(source, time.perf_counter() - 0.01)
    second = measure(source, time.perf_counter())
    assert first["status"] == second["status"] == "valid"
    assert first["xml_sha256"] == second["xml_sha256"]
    assert first["queue_ms"] >= 10
    assert set(first["stages_ms"]) == {"parse", "map", "build", "validate"}
    assert "Synthetic observation" not in str(first)


def test_pathological_fixture_is_rejected_and_sizes_are_bounded():
    result = measure(fixture(1, pathological=True), time.perf_counter())
    assert result["status"].startswith("rejected:")
    assert result["xml_sha256"] is None
    with pytest.raises(ValueError):
        fixture(513)


@pytest.mark.parametrize("pathological", [False, True])
def test_benchmark_instrumentation_does_not_retain_bound_method_cycles(pathological):
    pipeline = DeterministicPipeline()
    measure(fixture(1, pathological=pathological), time.perf_counter(), pipeline=pipeline)
    for obj, name in (
        (pipeline._parser, "parse"),
        (pipeline._mapper, "map"),
        (pipeline._builder, "build"),
        (pipeline._validator, "validate"),
    ):
        assert name not in vars(obj)


def capacity_evidence():
    rows = [
        {
            "case": case,
            "concurrency": concurrency,
            "all_valid": True,
            "deterministic": True,
            "samples": [{"status": "valid", "xml_sha256": "a" * 64}] * 3,
        }
        for case in ("small", "typical", "large")
        for concurrency in (1, 2)
    ]
    vps = {
        "version": "phase7-v12-vps-observation-1.0",
        "approved": True,
        "failures": [],
        "existing_services_unchanged": True,
        "container_removed": True,
        "limits": {"network": "none", "read_only": True, "memory_mib": 256, "cpus": 0.25},
        "samples": [healthy_sample()] * 100,
        "restricted_content_emitted": False,
        "benchmark": {
            "approved": True,
            "rows": rows,
            "provider_calls": 0,
            "pathological": {"status": "rejected:compression_ratio"},
            "soak": {
                "requested_seconds": 300,
                "elapsed_seconds": 301,
                "conversions": 50,
                "rss_growth_bytes": 1024,
            },
        },
    }
    corpus = {
        "version": "phase7-v12-local-corpus-1.0",
        "approved": True,
        "restricted_content_emitted": False,
        "articles": [
            {"corpus_id": article, "all_valid": True, "candidate_matches_qualification": True}
            for article in ("esa-e20240086", "esa-e20240135")
        ],
    }
    costs = {
        "version": "phase7-v12-historical-cost-1.0",
        "new_provider_calls": 0,
        "runs": [{"recorded_cost_microusd": 5, "failed_role_cost_microusd": 1}],
        "recorded_cost_microusd": 5,
        "failed_role_cost_microusd": 1,
        "assistive_domains": [str(i) for i in range(6)],
        "restricted_content_emitted": False,
    }
    return vps, corpus, costs


def test_capacity_gate_never_approves_full_phase_or_release():
    report = evaluate(*capacity_evidence())
    assert report["approved"] is True
    assert report["v12_complete"] is report["release_ready"] is False
    assert report["production_throughput_qualified"] is False


@pytest.mark.parametrize("amount", [None, -1, True, "1", float("nan"), float("inf"), 0.5])
def test_capacity_gate_rejects_unknown_or_invalid_costs(amount):
    vps, corpus, costs = capacity_evidence()
    costs["runs"][0]["failed_role_cost_microusd"] = amount
    report = evaluate(vps, corpus, costs)
    assert report["approved"] is False
    assert report["checks"]["historical_cost_accounting"] is False


@pytest.mark.parametrize(
    "mutation",
    ["missing_case", "short_soak", "memory_growth", "service_restart", "cost_mismatch", "privacy"],
)
def test_capacity_gate_rejects_incomplete_or_weakened_evidence(mutation):
    vps, corpus, costs = capacity_evidence()
    if mutation == "missing_case":
        vps["benchmark"]["rows"].pop()
    elif mutation == "short_soak":
        vps["benchmark"]["soak"]["elapsed_seconds"] = 299
    elif mutation == "memory_growth":
        vps["benchmark"]["soak"]["rss_growth_bytes"] = 33 * 1024**2
    elif mutation == "service_restart":
        vps["existing_services_unchanged"] = False
    elif mutation == "cost_mismatch":
        costs["recorded_cost_microusd"] = 4
    else:
        corpus["restricted_content_emitted"] = True
    assert evaluate(vps, corpus, costs)["approved"] is False
