import copy
import hashlib
from pathlib import Path

import pytest

from idml_foundation.services.autocorrection_promotion_policy import RULES, draft_admission
from idml_foundation.services.package_validation import assess_package
from idml_foundation.services.validation_scope import scope_digest
from tests.test_package_formal_validation import completed
from tests.test_xpm_execution import execution
from tests.test_xpm_execution import inputs as inputs


@pytest.fixture
def reports(inputs):
    scope = inputs["expected_scope"]
    formal = assess_package(
        **inputs,
        executor=completed,
        xpm_executor=execution,
        registry_path=Path(__file__).parents[1] / "config/validator-registry-vh1-composed.json",
    )
    return dict(
        offline=dict(valid=True, xml_sha256=scope["xml_sha256"], issues=[]),
        formal=formal,
        xml_sha256=scope["xml_sha256"],
        package_sha256=scope["package_sha256"],
        validation_scope=scope,
    )


def test_clean_draft_is_eligible_not_release(reports):
    decision = draft_admission(**reports)
    assert decision["eligible"] and not decision["release_approved"]
    assert not decision["warnings_accepted"] and not decision["homologation_ready"]


@pytest.mark.parametrize(
    "fault",
    [
        "offline_hash",
        "offline_error",
        "offline_missing",
        "xml",
        "package",
        "missing_run",
        "duplicate_run",
        "modern_status",
        "modern_error",
        "modern_tool",
        "modern_version",
        "modern_receipt",
        "external_unavailable",
        "xpm_missing",
        "xpm_unattested",
        "xpm_error",
        "xpm_hash",
        "xpm_tool",
        "query_missing",
        "query_conflict",
        "negative_count",
        "bool_count",
        "extra_count",
    ],
)
def test_incomplete_inconsistent_or_failed_validation_blocks(reports, fault):
    formal = reports["formal"]
    run = formal["external_runs"][0]
    xpm = formal["xpm"]
    if fault == "offline_hash":
        reports["offline"]["xml_sha256"] = "f" * 64
    elif fault == "offline_error":
        reports["offline"]["issues"] = [dict(severity="error")]
    elif fault == "offline_missing":
        reports["offline"] = None
    elif fault in {"xml", "package"}:
        formal[fault + "_sha256"] = "f" * 64
    elif fault == "missing_run":
        formal["external_runs"].pop()
    elif fault == "duplicate_run":
        formal["external_runs"][1] = copy.deepcopy(run)
    elif fault == "modern_status":
        run["status"] = "unavailable"
    elif fault == "modern_error":
        run["counts"]["error"] = 1
    elif fault == "modern_tool":
        run["tool_sha256"] = "f" * 64
    elif fault == "modern_version":
        run["version"] = "unknown"
    elif fault == "modern_receipt":
        run["report_sha256"] = None
    elif fault == "external_unavailable":
        run["unavailable_external_checks"] = ["wayta"]
    elif fault == "xpm_missing":
        formal["xpm"] = {}
    elif fault == "xpm_unattested":
        xpm["attested"] = False
    elif fault == "xpm_error":
        xpm["counts"]["errors"] = 1
    elif fault == "xpm_hash":
        xpm["candidate_package_sha256"] = "f" * 64
    elif fault == "xpm_tool":
        xpm["tool_sha256"] = "f" * 64
    elif fault == "query_missing":
        xpm["required_queries_complete"] = False
    elif fault == "query_conflict":
        xpm.update(
            required_queries_complete=False, selected_queries=dict(selected_checks_matched=False)
        )
    elif fault == "negative_count":
        run["counts"]["error"] = -1
    elif fault == "bool_count":
        run["counts"]["error"] = False
    else:
        run["counts"]["other"] = 0
    assert not draft_admission(**reports)["eligible"]


def compatibility(reports):
    from idml_foundation.release.xpm_structural_compatibility import NATIVE_QUALIFICATION_SHA256

    xpm = reports["formal"]["xpm"]
    xpm["counts"] = dict(blocking_errors=3, fatal_errors=1, errors=4, warnings=2)
    xpm["parser_recovered"] = True
    xpm["parser_errors"] = 15
    xpm["compatibility"] = dict(
        status="assessed",
        structural_status="assessed",
        structural_policy_version="xpm-homologation-structural-compatibility-1.0",
        technical_errors_resolved=True,
        scope_sha256=scope_digest(reports["validation_scope"]),
        homologation_ready=False,
        release_approved=False,
        unresolved_counts=dict(blocking_errors=0, fatal_errors=0, errors=0, warnings=2),
        exceptions=[
            dict(
                rule_id=r,
                occurrence_sha256=hashlib.sha256(str(i).encode()).hexdigest(),
                native_qualification_sha256=NATIVE_QUALIFICATION_SHA256,
            )
            for i, r in enumerate([*RULES, "xpm-sps110-date-type-1.0"])
        ],
    )
    return xpm["compatibility"]


def test_exact_compatibility_can_admit_draft_but_retains_raw_findings_and_warnings(reports):
    compatibility(reports)
    before = copy.deepcopy(reports)
    decision = draft_admission(**reports)
    assert decision["eligible"] and "xpm-warnings-review" in decision["pending_review"]
    assert "delivery-doctype-editorial-review" in decision["pending_review"]
    assert reports == before and not decision["warnings_accepted"]


@pytest.mark.parametrize(
    "fault",
    ["missing", "duplicate", "unknown", "zero_claim", "wrong_scope", "bad_pin", "extra_error"],
)
def test_compatibility_cannot_hide_unknown_or_duplicate_findings(reports, fault):
    comp = compatibility(reports)
    if fault == "missing":
        comp["exceptions"].pop()
    elif fault == "duplicate":
        comp["exceptions"][1] = comp["exceptions"][0]
    elif fault == "unknown":
        comp["exceptions"][0]["rule_id"] = "unknown"
    elif fault == "zero_claim":
        comp["exceptions"] = []
    elif fault == "wrong_scope":
        comp["scope_sha256"] = "f" * 64
    elif fault == "bad_pin":
        comp["exceptions"][-2]["native_qualification_sha256"] = "f" * 64
    else:
        reports["formal"]["xpm"]["counts"]["errors"] += 1
    assert not draft_admission(**reports)["eligible"]


@pytest.mark.parametrize(
    "fault", ["none", "conflict", "missing", "forged_matched", "wayta", "wayta_pin"]
)
def test_selected_queries_and_qualified_advisory_never_hide_conflicts(reports, fault):
    import json

    from tests.test_validation_followups import selected

    comp = compatibility(reports)
    archived = json.loads(
        (
            Path(__file__).parents[1]
            / "benchmarks/qualification/reports/vh1-structural-native-replay-v1.json"
        ).read_bytes()
    )
    comp["wayta"] = archived["cases"][0]["compatibility"]["wayta"]
    xpm = reports["formal"]["xpm"]
    xpm["required_queries_complete"] = False
    xpm["selected_queries"] = selected()
    if fault in {"conflict", "forged_matched"}:
        xpm["selected_queries"] = selected(public_change=lambda b: b["name"].pop("family-name"))
        if fault == "forged_matched":
            xpm["selected_queries"]["selected_checks_matched"] = True
    elif fault == "missing":
        xpm["selected_queries"]["checks"].pop()
    elif fault == "wayta":
        comp["wayta"]["requirement"] = "undetermined"
    elif fault == "wayta_pin":
        comp["wayta"]["native_proof_sha256"] = "f" * 64
    result = draft_admission(**reports)
    assert result["eligible"] is (fault == "none")
    if fault == "none":
        assert "affiliation-source-review" in result["pending_review"]
        assert "orcid-ownership-not-authenticated" in result["pending_review"]


def test_scope_cannot_claim_other_candidate_even_with_clean_reports(reports):
    reports["validation_scope"]["xml_sha256"] = "f" * 64
    assert not draft_admission(**reports)["eligible"]
