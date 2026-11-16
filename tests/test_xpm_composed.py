"""Current independent receipts compose without rewriting report hashes or gates."""
# ruff: noqa: F811 -- imported pytest fixtures

import hashlib
import json
from datetime import timedelta

import pytest

from idml_foundation.release.xpm_query_semantics import QueryEvidence
from idml_foundation.release.xpm_sps_compatibility import (
    assess_xpm_sps_compatibility,
    bind_runtime_runs,
)
from idml_foundation.services.xpm_runtime_compatibility import (
    WaytaExecutionEvidence,
    assess_runtime_compatibility,
)
from tests.test_xpm_compatibility import inputs as doi_inputs  # noqa: F401
from tests.test_xpm_compatibility import sha
from tests.test_xpm_query_requirements import data as wayta_inputs  # noqa: F401
from tests.test_xpm_sps_compatibility import data as sps_inputs  # noqa: F401


def current(data):
    old = data["sps_evidence"]
    runs = tuple(
        r.model_copy(update={"sanitized_output_sha256": str(i + 1) * 64})
        for i, r in enumerate(old.runs)
    )
    data["sps_evidence"] = bind_runtime_runs(
        data["expected_scope"], sha(data["report"]), runs, data["now"]
    )
    return data


def test_current_report_hashes_preserved(sps_inputs):
    data = current(sps_inputs)
    result = assess_xpm_sps_compatibility(**data)
    assert len(result.exceptions) == 4
    assert [r.sanitized_output_sha256 for r in data["sps_evidence"].runs] == ["1" * 64, "2" * 64]
    assert (
        result.exceptions[0].independent_report_sha256
        == data["sps_evidence"].independent_report_sha256
    )
    assert result.base.original.errors == 4 and not result.release_approved


@pytest.mark.parametrize(
    "change",
    [
        "scope",
        "report",
        "digest",
        "stale",
        "future",
        "same_hash",
        "missing_hash",
        "failed",
        "error",
        "candidate",
        "image",
        "version",
    ],
)
def test_current_evidence_fails_closed(sps_inputs, change):
    data = current(sps_inputs)
    ev = data["sps_evidence"]
    if change == "scope":
        ev = ev.model_copy(
            update={"scope": {**ev.scope, "resource_id": ev.scope["organization_id"]}}
        )
    elif change == "report":
        ev = ev.model_copy(update={"xpm_report_sha256": "c" * 64})
    elif change == "digest":
        ev = ev.model_copy(update={"independent_report_sha256": "c" * 64})
    elif change in {"stale", "future"}:
        data["now"] += timedelta(hours=25 if change == "stale" else -1)
    else:
        update = {
            "same_hash": {"sanitized_output_sha256": "2" * 64},
            "missing_hash": {"sanitized_output_sha256": None},
            "failed": {"status": "unavailable"},
            "error": {"failure_code": "native-failure"},
            "candidate": {"candidate_sha256": "c" * 64},
            "image": {"tool_sha256": "c" * 64},
            "version": {"version": "other"},
        }[change]
        runs = (ev.runs[0].model_copy(update=update), ev.runs[1])
        ev = bind_runtime_runs(ev.scope, ev.xpm_report_sha256, runs, data["now"])
    data["sps_evidence"] = ev
    with pytest.raises(ValueError):
        assess_xpm_sps_compatibility(**data)


def runtime_arguments(data):
    data = current(data)
    original = data["wayta_evidence"]
    raw = json.dumps({"service_observation": original.observation.model_dump(mode="json")})
    requirement = original.model_copy(update={"service_report_sha256": sha(raw.encode())})
    wayta = WaytaExecutionEvidence(
        xpm_report_sha256=sha(data["report"]), service_report=raw, requirement=requirement
    )
    queries = QueryEvidence.model_validate(
        dict(
            version="xpm-query-evidence-1.0",
            scope=data["expected_scope"],
            report_sha256=sha(data["report"]),
            receipts=[
                dict(
                    kind="crossref",
                    identifier="10.1590/synthetic",
                    url="https://api.crossref.org/works/10.1590%2Fsynthetic",
                    status="available",
                    retrieved_at=data["now"],
                    response_sha256=sha(data["crossref"]),
                    payload=data["crossref"].decode(),
                )
            ],
        )
    )
    return dict(
        xml=data["xml"],
        package=data["package"],
        report=data["report"],
        scope=data["expected_scope"],
        image=data["trusted"].image,
        attestation=data["trusted"].attestation,
        queries=queries,
        selected={"checks": [{"kind": "crossref", "status": "matched"}]},
        now=data["now"],
        independent_runs=data["sps_evidence"].runs,
        wayta=wayta,
    )


def test_composed_wayta_timeout_stays_timeout_without_success(wayta_inputs):
    args = runtime_arguments(wayta_inputs)
    result = assess_runtime_compatibility(**args)
    assert result["sps_status"] == "assessed"
    assert len(result["exceptions"]) == 6
    assert result["unresolved_counts"] == dict(
        blocking_errors=1, fatal_errors=1, errors=1, warnings=1
    )
    assert result["wayta"]["requirement"] == "advisory_for_qualified_profile"
    assert result["wayta"]["service_observation"]["outcome"] == "timeout"
    assert not result["wayta"]["article_query_completed"] and not result["release_approved"]
    assert "synthetic-no-native-execution" not in json.dumps(result)
    from datetime import datetime

    rebound = bind_runtime_runs(
        args["scope"],
        sha(args["report"]),
        args["independent_runs"],
        datetime.fromisoformat(result["independent_assembled_at"]),
    )
    assert rebound.independent_report_sha256 == result["independent_evidence_sha256"]


@pytest.mark.parametrize(
    "change",
    [
        "missing",
        "hash",
        "report",
        "scope",
        "norm",
        "vendor",
        "expired",
        "future",
        "observation",
        "shape",
    ],
)
def test_wayta_invalid_preserves_sps_but_cannot_waive_query(wayta_inputs, change):
    args = runtime_arguments(wayta_inputs)
    w = args["wayta"]
    if change == "missing":
        args["wayta"] = None
    elif change == "hash":
        args["wayta"] = w.model_copy(update={"service_report": w.service_report + " "})
    elif change == "report":
        args["wayta"] = w.model_copy(update={"xpm_report_sha256": "c" * 64})
    else:
        requirement = w.requirement
        if change == "scope":
            update = {"scope": {**requirement.scope, "xml_sha256": "c" * 64}}
        elif change == "norm":
            update = {"normative_sha256": "c" * 64}
        elif change == "vendor":
            update = {"vendor_sha256": {}}
        else:
            observation = requirement.observation.model_dump(mode="json")
            if change in {"expired", "future"}:
                observation["observed_at"] = (
                    args["now"] + timedelta(hours=-25 if change == "expired" else 25)
                ).isoformat()
            elif change == "observation":
                observation["elapsed_seconds"] = 2
            else:
                observation["semantic_result_validated"] = True
            update = {"observation": observation}
        args["wayta"] = w.model_copy(update={"requirement": requirement.model_copy(update=update)})
    result = assess_runtime_compatibility(**args)
    assert result["sps_status"] == "assessed" and len(result["exceptions"]) == 6
    assert result["wayta"]["requirement"] == "undetermined" and not result["release_approved"]


def test_failed_modern_run_keeps_doi_but_cannot_apply_sps(wayta_inputs):
    args = runtime_arguments(wayta_inputs)
    args["independent_runs"] = args["independent_runs"][:1]
    result = assess_runtime_compatibility(**args)
    assert result["sps_status"] == "unavailable" and len(result["exceptions"]) == 2
    assert result["unresolved_counts"]["blocking_errors"] == 4


def test_wayta_collector_contract_constants_agree():
    from pathlib import Path

    from idml_foundation.release import xpm_query_requirements as rule
    from ops import xpm_wayta_collect as collector

    assert collector.NORM_SHA == rule.NORMATIVE_SHA256
    assert collector.PROOF_SHA == rule.NATIVE_PROOF_SHA256
    assert collector.VENDOR == rule.VENDOR_FILES
    assert (
        hashlib.sha256(
            Path("benchmarks/qualification/reports/vh1-wayta-native-v3.json").read_bytes()
        ).hexdigest()
        == collector.PROOF_SHA
    )


@pytest.mark.parametrize("failure", ["none", "norm", "proof", "timeout", "exit", "probe_hash"])
def test_service_collector_is_bounded_and_sources_are_pinned(tmp_path, monkeypatch, failure):
    import subprocess

    from ops import xpm_validator_broker as broker
    from ops import xpm_wayta_collect as collector

    original = broker.read_regular
    norm = b"synthetic norm"
    monkeypatch.setattr(collector, "NORM_SHA", sha(norm) if failure != "norm" else "f" * 64)

    def read(path, root, limit):
        if path == collector.NORM:
            return norm
        raw = original(path, root, limit)
        return raw + b" " if failure == "proof" and path.name == "vh1-wayta-native-v3.json" else raw

    calls = []
    monkeypatch.setattr(broker, "read_regular", read)

    def run(command, **kwargs):
        from pathlib import Path

        calls.append(command)
        assert kwargs["timeout"] == 30 and kwargs["capture_output"]
        assert command[1:3] == ["-m", "ops.probe_wayta_https"]
        if failure == "timeout":
            raise subprocess.TimeoutExpired(command, 30)
        raw = json.dumps(
            dict(
                probe_sha256="f" * 64
                if failure == "probe_hash"
                else sha(Path("ops/probe_wayta_https.py").read_bytes()),
                service_observation={"synthetic": True},
            )
        )
        (tmp_path / "wayta-service.json").write_text(raw)
        return subprocess.CompletedProcess(command, 1 if failure == "exit" else 0)

    monkeypatch.setattr(collector.subprocess, "run", run)
    if failure == "none":
        result = collector.collect({"synthetic": "scope"}, "a" * 64, tmp_path)
        assert result["xpm_report_sha256"] == "a" * 64
        assert (
            sha(result["service_report"].encode()) == result["requirement"]["service_report_sha256"]
        )
    else:
        with pytest.raises((ValueError, subprocess.TimeoutExpired)):
            collector.collect({}, "a" * 64, tmp_path)
    if failure in {"norm", "proof"}:
        assert not calls


@pytest.mark.parametrize("mode", ["composed", "missing_modern", "missing_wayta"])
def test_full_package_path_composes_only_current_evidence(wayta_inputs, mode):
    from pathlib import Path

    from idml_foundation.services.package_validation import assess_package
    from idml_foundation.services.xpm_execution import XpmExecutionEvidence
    from tests.test_xpm_query_requirements import bind_wayta

    data = wayta_inputs
    data["xml"] = data["xml"].replace(
        b"<xref", b"<name><given-names>Ana</given-names><surname>Silva</surname></name><xref"
    )
    crossref = json.loads(data["crossref"])
    crossref["message"]["author"] = [{"given": "Ana", "family": "Silva"}]
    data["crossref"] = json.dumps(crossref).encode()
    bind_wayta(data)
    args = runtime_arguments(data)
    evidence = XpmExecutionEvidence(
        scope=args["scope"],
        report=args["report"],
        image=args["image"],
        attestation=args["attestation"],
        required_queries_complete=False,
        query_evidence=args["queries"],
        wayta_evidence=None if mode == "missing_wayta" else args["wayta"],
    )
    runs = {r.name: r for r in args["independent_runs"]}
    result = assess_package(
        xml=args["xml"],
        package=args["package"],
        expected_scope=args["scope"],
        registry_path=Path("config/validator-registry-vh1-composed.json"),
        executor=None if mode == "missing_modern" else lambda _, spec: runs[spec.name],
        xpm_executor=lambda *_: evidence,
    )
    assert result["xpm"]["counts"]["blocking_errors"] == 4
    derived = result["xpm"]["compatibility"]
    assert len(derived["exceptions"]) == (2 if mode == "missing_modern" else 6)
    if mode == "composed":
        assert derived["wayta"]["requirement"] == "advisory_for_qualified_profile"
        assert [r["report_sha256"] for r in derived["independent_runs"]] == ["1" * 64, "2" * 64]
    assert (
        result["state"] == "blocked" and not result["complete"] and not result["ready_for_scielo"]
    )
