import json
from pathlib import Path

import pytest

from ops.gate_phase7_v12_ingest import evaluate


def evidence():
    path = (
        Path(__file__).parents[1]
        / "benchmarks/qualification/reports/v12-ingest-observation-after-v2.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))


def test_bounded_ingest_gate_does_not_approve_production():
    result = evaluate(evidence())
    assert result["approved"] is True
    assert result["release_ready"] is result["v12_2_complete"] is False
    assert result["production_capacity_qualified"] is False


@pytest.mark.parametrize(
    "mutation", ["missing", "oom", "rss", "status", "cleanup", "memory", "service", "privacy"]
)
def test_ingest_gate_rejects_incomplete_or_failed_evidence(mutation):
    report = evidence()
    if mutation == "missing":
        report["cases"].pop()
    elif mutation == "oom":
        report["cases"][0]["oom_killed"] = True
    elif mutation == "rss":
        report["cases"][0]["probe"]["peak_rss_bytes"] = 193 * 1024**2
    elif mutation == "status":
        report["cases"][0]["probe"]["status"] = "unexpected"
    elif mutation == "cleanup":
        report["cleanup_errors"] = ["leftover"]
    elif mutation == "memory":
        report["samples"][0]["memory_available_bytes"] = 511 * 1024**2
    elif mutation == "service":
        report["existing_services_unchanged"] = False
    else:
        report["cases"][0]["probe"]["restricted_content_emitted"] = True
    assert evaluate(report)["approved"] is False
