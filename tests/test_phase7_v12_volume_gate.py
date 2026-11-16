import json
from pathlib import Path

import pytest

from ops.gate_phase7_v12_volume import evaluate, main


def evidence():
    return json.loads(
        (
            Path(__file__).parents[1]
            / "benchmarks/qualification/reports/v12-volume-observation-v1.json"
        ).read_text(encoding="utf-8")
    )


def test_volume_gate_approves_only_measured_profiles():
    result = evaluate(evidence())
    assert result["approved"]
    assert (
        result["v12_2_complete"]
        is result["production_capacity_qualified"]
        is result["release_ready"]
        is False
    )


@pytest.mark.parametrize(
    "mutation",
    ["missing", "oom", "size", "text", "quota", "disk", "rss", "cleanup", "services", "host"],
)
def test_volume_gate_rejects_regressions(mutation):
    report = evidence()
    if mutation == "missing":
        report["cases"].pop()
    elif mutation == "oom":
        report["cases"][0]["oom_killed"] = True
    elif mutation == "size":
        report["cases"][1]["probe"]["input_bytes"] = 1024
    elif mutation == "text":
        report["cases"][3]["probe"]["xml_bytes"] = 1024
    elif mutation == "quota":
        report["cases"][4]["probe"]["usage"] = [1, 1]
    elif mutation == "disk":
        report["cases"][5]["probe"]["status"] = "accepted"
    elif mutation == "rss":
        report["cases"][0]["probe"]["peak_rss_bytes"] = 257 * 1024**2
    elif mutation == "cleanup":
        report["cleanup_errors"] = ["scratch"]
    elif mutation == "services":
        report["existing_services_unchanged"] = False
    else:
        report["samples"][0]["memory_available_bytes"] = 511 * 1024**2
    assert not evaluate(report)["approved"]


def test_volume_cli_rejects_stale_source(tmp_path, monkeypatch):
    report = evidence()
    report["source_sha256"]["src/idml_foundation/services/artifacts.py"] = "0" * 64
    input_path, output_path = tmp_path / "input.json", tmp_path / "output.json"
    input_path.write_text(json.dumps(report), encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv", ["gate", "--report", str(input_path), "--output", str(output_path)]
    )
    assert main() == 2
    assert not json.loads(output_path.read_text())["checks"]["sources"]
