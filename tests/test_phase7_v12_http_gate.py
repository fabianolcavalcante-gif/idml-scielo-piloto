import json
from pathlib import Path

import pytest

from ops.gate_phase7_v12_http import evaluate


def evidence():
    path = (
        Path(__file__).parents[1] / "benchmarks/qualification/reports/v12-http-observation-v3.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))


def test_http_gate_is_not_production_capacity():
    result = evaluate(evidence())
    assert result["approved"] is True
    assert result["release_ready"] is result["v12_2_complete"] is False
    assert result["production_capacity_qualified"] is False


@pytest.mark.parametrize(
    "mutation",
    ["missing", "open_file", "no_spool", "rss", "oom", "service", "status", "memory", "admission"],
)
def test_http_gate_rejects_incomplete_evidence(mutation):
    report = evidence()
    if mutation == "missing":
        report["probe"]["cases"].pop()
    elif mutation == "open_file":
        report["probe"]["cases"][0]["stats"]["open_files"] = 1
    elif mutation == "no_spool":
        report["probe"]["cases"][3]["stats"]["rolled_files"] = 0
    elif mutation == "rss":
        report["probe"]["cases"][0]["stats"]["peak_rss_bytes"] = 129 * 1024**2
    elif mutation == "oom":
        report["container_exit"]["OOMKilled"] = True
    elif mutation == "service":
        report["existing_services_unchanged"] = False
    elif mutation == "status":
        report["probe"]["cases"][-1]["status"] = 200
    elif mutation == "admission":
        report["probe"]["admission"]["busy_status"] = 200
    else:
        report["samples"][0]["memory_available_bytes"] = 511 * 1024**2
    assert evaluate(report)["approved"] is False
