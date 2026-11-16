from __future__ import annotations

import json
import subprocess

import pytest

from ops import gate_phase7_7c08 as gate
from ops.gate_phase7_v03 import synthetic_gate, verify_package
from ops.gate_phase7_v10 import REPORT as V10_REPORT
from ops.gate_phase7_v10 import _published_report_gate as check_v10
from ops.gate_phase7_v11 import REPORT as V11_REPORT
from ops.gate_phase7_v11 import _published_report_gate as check_v11
from tests.phase3_helpers import synthetic_idml
from tests.test_phase7_7c03_formulas import _mutate_story


@pytest.mark.parametrize("split_style_range", [False, True])
def test_reading_gate_does_not_duplicate_separately_styled_formula_label(split_style_range):
    source = synthetic_idml(include_formula=True)
    if split_style_range:
        source = _mutate_story(
            source,
            "Stories/Story_u2.xml",
            lambda data: data.replace(
                b"</PDF></Rectangle><TextVariableInstance",
                b"</PDF></Rectangle></CharacterStyleRange><CharacterStyleRange "
                b'AppliedCharacterStyle="CharacterStyle/none"><TextVariableInstance',
            ),
        )
    _, metrics = verify_package(source, "ESA_2024001_AOP.idml")
    assert metrics["source_stories"] == metrics["exact_stories"]


@pytest.mark.parametrize(
    ("name", "arguments", "report", "exit_code", "passed"),
    [
        ("v07", [], {"qualification_approved": True, "approved": False}, 0, True),
        (
            "v07",
            ["--require-candidate-pass"],
            {"qualification_approved": True, "approved": False},
            0,
            False,
        ),
        ("v01", [], {"approved": True}, 2, False),
        ("v01", [], {"approved": False}, 0, False),
    ],
)
def test_aggregate_gate_fails_closed(monkeypatch, name, arguments, report, exit_code, passed):
    monkeypatch.setattr(
        gate.subprocess,
        "run",
        lambda *a, **kw: subprocess.CompletedProcess(
            args=[], returncode=exit_code, stdout=json.dumps(report), stderr=""
        ),
    )
    assert gate.run_gate(name, arguments)["passed"] is passed


def test_current_v03_profile_gate_preserves_single_item_content():
    assert synthetic_gate()["checks"] == 10


@pytest.mark.parametrize(("path", "check"), [(V10_REPORT, check_v10), (V11_REPORT, check_v11)])
def test_requalified_evidence_rejects_source_tampering(path, check):
    report = json.loads(path.read_text(encoding="utf-8"))
    assert check(report)["source_files"] > 0
    first = next(iter(report["source_sha256"]))
    report["source_sha256"][first] = "0" * 64
    with pytest.raises(ValueError, match="source evidence hash mismatch"):
        check(report)
