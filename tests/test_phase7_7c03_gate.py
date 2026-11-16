from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
GATE = ROOT / "ops" / "gate_phase7_7c03.py"
QUALIFICATION = (
    ROOT / "benchmarks/agents/reports/formula-transcription-qualification-e20240135-v1.json"
)


def _run_gate(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed interpreter/gate and test-controlled arguments
        [sys.executable, str(GATE), *arguments],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_phase7_7c03_metadata_gate_is_content_safe_and_approved() -> None:
    completed = _run_gate("--metadata-only")
    report = json.loads(completed.stdout)

    assert completed.returncode == 0
    assert report["approved"] is True
    assert report["metadata"]["approved"] is True
    assert report["metadata"]["mismatches"] == []
    assert report["metadata"]["qualification"]["formula_cases"] == 43
    assert report["metadata"]["qualification"]["critic_passes"] == 86
    assert report["metadata"]["qualification"]["adjudicator_accepts"] == 43
    assert report["restricted_content_emitted"] is False
    assert report["network_required_by_gate"] is False


def test_phase7_7c03_metadata_gate_rejects_tampered_qualification(
    tmp_path: Path,
) -> None:
    qualification = json.loads(QUALIFICATION.read_text(encoding="utf-8"))
    qualification["formula_cases"] = 42
    tampered = tmp_path / "qualification.json"
    tampered.write_text(json.dumps(qualification), encoding="utf-8")

    completed = _run_gate(
        "--metadata-only",
        "--qualification-report",
        str(tampered),
    )
    report = json.loads(completed.stdout)

    assert completed.returncode == 2
    assert report["approved"] is False
    assert report["metadata"]["approved"] is False
    assert "expected.qualification.report_sha256" in report["metadata"]["mismatches"]
    assert "expected.qualification.formula_cases" in report["metadata"]["mismatches"]
    assert report["restricted_content_emitted"] is False
