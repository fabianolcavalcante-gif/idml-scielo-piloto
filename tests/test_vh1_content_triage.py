import copy
import json

import pytest
from lxml import etree

from idml_foundation.ai.security import payload_digest
from ops.gate_vh1_content_triage import REPORT, ROOT, evaluate
from ops.triage_vh1_content import check_complete, formula_decision, fragment, sha


def example():
    math = '<mml:math xmlns:mml="http://www.w3.org/1998/Math/MathML"><mml:mi>x</mml:mi></mml:math>'
    entry = {
        "case_id": "example",
        "mathml": math,
        "mathml_sha256": sha(math.encode()),
        "qualification": {"human_review_required": True},
    }
    review = {
        "case_id": "example",
        "before_sha256": entry["mathml_sha256"],
        "page_index": 0,
        "status": "reviewed_no_confirmed_transcription_defect",
    }
    return entry, review


def test_source_review_does_not_grant_scientific_approval():
    entry, review = example()
    result = formula_decision("synthetic", entry, review, "a" * 64)
    assert result["disposition"] == "source_reviewed_gold_difference"
    assert result["human_review_required"]
    assert not result["scientific_fidelity_approved"]
    assert entry["mathml"] not in str(result)


@pytest.mark.parametrize("change", ["id", "hash", "math", "review_hash", "status"])
def test_unbound_or_unreviewed_transcriptions_cannot_be_adjudicated(change):
    entry, review = example()
    if change == "id":
        review["case_id"] = "other"
    elif change == "hash":
        entry["mathml_sha256"] = "0" * 64
    elif change == "math":
        entry["mathml"] = entry["mathml"].replace(">x<", ">y<")
    elif change == "review_hash":
        review["before_sha256"] = "0" * 64
    else:
        review["status"] = "glyph_or_style_review_pending"
    with pytest.raises(ValueError):
        formula_decision("synthetic", entry, review, "a" * 64)


def test_only_documented_abstention_is_carried_forward():
    entry, review = example()
    entry["case_id"] = review["case_id"] = "esa-math-notes-inline-005"
    review["status"] = "glyph_or_style_review_pending"
    assert formula_decision("esa-e20240135", entry, review, "a" * 64)["disposition"] == (
        "scientific_glyph_abstention"
    )
    with pytest.raises(ValueError):
        formula_decision("esa-e20240086", entry, review, "a" * 64)


@pytest.mark.parametrize(
    "change", [None, "pdf", "before", "after", "human", "gold", "autonomous", "status"]
)
def test_revisions_bind_original_and_corrected_mathml_to_source(change):
    entry, review = example()
    review["status"] = "source_correction"
    q = {
        "method": "development-visual-source-review-1.0",
        "source_pdf_sha256": "a" * 64,
        "previous_mathml_sha256": review["before_sha256"],
        "corrected_mathml_sha256": entry["mathml_sha256"],
        "human_review_required": True,
        "gold_exposed_to_agent": False,
        "autonomous_application": False,
    }
    entry["qualification"] = q
    keys = {
        "pdf": "source_pdf_sha256",
        "before": "previous_mathml_sha256",
        "after": "corrected_mathml_sha256",
        "human": "human_review_required",
        "gold": "gold_exposed_to_agent",
        "autonomous": "autonomous_application",
    }
    if change is None:
        assert formula_decision("synthetic", entry, review, "a" * 64)["disposition"] == (
            "source_corrected_gold_difference"
        )
        return
    if change == "status":
        review["status"] = "unreviewed"
    else:
        q[keys[change]] = (
            False if change == "human" else True if change in {"gold", "autonomous"} else "0" * 64
        )
    with pytest.raises(ValueError):
        formula_decision("synthetic", entry, review, "a" * 64)


@pytest.mark.parametrize("change", [None, "missing", "duplicate", "hash", "human", "approved"])
def test_coverage_cannot_hide_a_raw_blocking_finding(change):
    findings = [{"blocking": True, "domain": "synthetic"}]
    decisions = [
        {
            "raw_finding_sha256": payload_digest(findings[0]),
            "disposition": "reviewed",
            "human_review_required": True,
            "scientific_fidelity_approved": False,
        }
    ]
    if change is None:
        assert check_complete(findings, decisions) == {"reviewed": 1}
        return
    if change == "missing":
        decisions.clear()
    elif change == "duplicate":
        decisions.append(copy.deepcopy(decisions[0]))
    elif change == "hash":
        decisions[0]["raw_finding_sha256"] = "0" * 64
    else:
        decisions[0][
            "human_review_required" if change == "human" else "scientific_fidelity_approved"
        ] = change != "human"
    with pytest.raises(ValueError):
        check_complete(findings, decisions)


@pytest.mark.parametrize(
    "tag,identifier", [("inline-formula", "m-test"), ("disp-formula", "m-e-test")]
)
def test_only_generated_root_identifier_is_removed(tag, identifier):
    xml = (
        f'<{tag} id="e-test"><mml:math xmlns:mml="http://www.w3.org/1998/Math/MathML" '
        f'id="{identifier}"><mml:mi mathvariant="script">A</mml:mi></mml:math></{tag}>'
    )
    node = etree.fromstring(xml.encode())
    before = etree.tostring(node)
    assert 'mathvariant="script"' in fragment(node)
    assert etree.tostring(node) == before
    node[0].set("id", "unexpected")
    with pytest.raises(ValueError):
        fragment(node)


def test_published_triage_preserves_all_thirty_findings_and_abstention():
    result = evaluate(REPORT.read_bytes(), lambda p: (ROOT / p).read_bytes())
    assert result["passed"], result
    assert not result["scientific_fidelity_approved"]


@pytest.mark.parametrize(
    "change", ["decision", "count", "approved", "source", "candidate", "raw_passed"]
)
def test_published_triage_tampering_fails(change):
    report = json.loads(REPORT.read_bytes())
    case = report["cases"]["esa-e20240135"]
    if change == "decision":
        case["decisions"].pop()
    elif change == "count":
        case["raw_blocking_findings"] = 0
    elif change == "approved":
        report["scientific_fidelity_approved"] = True
    elif change == "source":
        report["source_sha256"]["ops/triage_vh1_content.py"] = "0" * 64
    elif change == "candidate":
        case["candidate_sha256"] = "0" * 64
    else:
        case["raw_comparison_passed"] = True
    assert not evaluate(json.dumps(report).encode(), lambda p: (ROOT / p).read_bytes())["passed"]
