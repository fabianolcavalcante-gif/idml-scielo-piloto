import json

import pytest

from ops.gate_vh1_final_warnings import REPORT, ROOT, evaluate


def test_published_warning_triage_is_current_but_not_a_release():
    result = evaluate(REPORT.read_bytes(), lambda p: (ROOT / p).read_bytes())
    assert result["passed"], result
    assert not result["formal_xml_approved"] and not result["vh07_complete"]


@pytest.mark.parametrize(
    "mutation",
    [
        "approved",
        "xpm",
        "accepted",
        "severity",
        "deleted",
        "extra",
        "candidate",
        "source",
        "abstention",
        "group",
    ],
)
def test_report_cannot_silently_become_an_acceptance(mutation):
    report = json.loads(REPORT.read_bytes())
    case = report["cases"]["esa-e20240086"]
    row = case["validators"][0]["decisions"][0]
    if mutation == "approved":
        report["formal_xml_approved"] = True
    elif mutation == "xpm":
        case["xpm"]["status"] = "completed"
    elif mutation == "accepted":
        row["accepted_for_release"] = True
    elif mutation == "severity":
        row["severity_retained"] = "info"
    elif mutation == "deleted":
        case["validators"][0]["decisions"].pop()
    elif mutation == "extra":
        case["validators"][0]["decisions"].append(row.copy())
    elif mutation == "candidate":
        case["xml_sha256"] = "0" * 64
    elif mutation == "source":
        report["source_sha256"] = {}
    elif mutation == "abstention":
        report["remaining_ambiguous_glyphs"] = 0
    else:
        row["structural_group_sha256"] = "0" * 64
    assert not evaluate(json.dumps(report).encode(), lambda p: (ROOT / p).read_bytes())["passed"]


def test_tampered_underlying_native_source_fails_closed():
    assert not evaluate(REPORT.read_bytes(), lambda p: b"changed")["passed"]
