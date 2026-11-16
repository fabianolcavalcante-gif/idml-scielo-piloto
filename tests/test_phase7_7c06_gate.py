from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
GATE = ROOT / "ops" / "gate_phase7_7c06.py"
CONTRACT = ROOT / "benchmarks/qualification/contracts/e20240135-7c06-formal-v1.json"
FORMAL_REPORT = (
    ROOT / "benchmarks/qualification/reports/formal-metadata-authority-e20240135-v1.json"
)


def _run_gate(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed interpreter/gate and test-controlled arguments
        [sys.executable, str(GATE), *arguments],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_phase7_7c06_metadata_gate_is_content_safe_and_approved() -> None:
    completed = _run_gate("--metadata-only")
    report = json.loads(completed.stdout)

    assert completed.returncode == 0
    assert report["approved"] is True
    assert report["metadata"]["approved"] is True
    assert report["metadata"]["role_counts"]["figure_asset"] == 7
    assert report["metadata"]["formal_metadata_authority"]["publication_fields"] == 3
    assert report["restricted_content_emitted"] is False
    assert report["network_required_by_gate"] is False
    assert report["release_ready"] is False
    assert report["xpm_sps_1_10"]["status"] == "pending_windows_execution"


def test_phase7_7c06_metadata_gate_rejects_tampered_formal_report(
    tmp_path: Path,
) -> None:
    authority = json.loads(FORMAL_REPORT.read_text(encoding="utf-8"))
    authority["publication_fields"] = 2
    tampered = tmp_path / "formal-report.json"
    tampered.write_text(json.dumps(authority), encoding="utf-8")

    completed = _run_gate("--metadata-only", "--formal-report", str(tampered))
    report = json.loads(completed.stdout)

    assert completed.returncode == 2
    assert report["approved"] is False
    assert "expected.formal_metadata_authority.report_sha256" in report["metadata"]["mismatches"]
    assert (
        "expected.formal_metadata_authority.publication_fields" in report["metadata"]["mismatches"]
    )


def test_phase7_7c06_metadata_gate_rejects_tampered_contract(tmp_path: Path) -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    contract["expected"]["role_counts"]["figure_asset"] = 8
    tampered = tmp_path / "contract.json"
    tampered.write_text(json.dumps(contract), encoding="utf-8")

    completed = _run_gate("--metadata-only", "--contract", str(tampered))
    report = json.loads(completed.stdout)

    assert completed.returncode == 2
    assert report["approved"] is False
    assert "expected.role_counts.figure_asset" in report["metadata"]["mismatches"]


def test_phase7_7c06_rejects_incomplete_validator_payload() -> None:
    sys.path.insert(0, str(ROOT / "ops"))
    try:
        from gate_phase7_7c06 import _validator_findings

        with pytest.raises(ValueError, match="incomplete"):
            _validator_findings(
                {
                    "adapter_contract": "1.1.0",
                    "result": {"complete": False, "findings": [], "summary": {}},
                }
            )
    finally:
        sys.path.pop(0)
