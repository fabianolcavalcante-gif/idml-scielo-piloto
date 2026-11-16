"""Execute the content-safe V-06 formal-validator qualification gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from idml_foundation.domain.common import canonical_bytes
from idml_foundation.pipeline.jats_builder import JatsBuilder
from idml_foundation.pipeline.validation import OfflineJatsValidator
from idml_foundation.release.package_builder import AssetPayload, PackageBuilder
from idml_foundation.release.validation_engine import (
    IssueCategory,
    ValidationEngine,
    ValidatorCommand,
    ValidatorStatus,
)
from idml_foundation.release.validator_registry import (
    ValidatorChannel,
    ValidatorRegistry,
    load_validator_registry,
)
from idml_foundation.release.xpm import XpmAttestation, XpmReportParser

sys.path.insert(0, str(Path(__file__).parents[1]))
from ops.v05_fixture import complete_article
from ops.validator_adapter_common import sanitize_validator_result

PROFILE = "sps-1.10/jats-1.3"


def _formal_offline_gate(vendor: Path) -> dict[str, Any]:
    article = complete_article()
    xml = JatsBuilder().build(article)
    report = OfflineJatsValidator(vendor).validate(
        xml,
        asset_names={asset.logical_name for asset in article.assets},
    )
    if not report.valid:
        raise AssertionError("formal offline baseline is invalid")
    return {
        "candidate_sha256": hashlib.sha256(xml).hexdigest(),
        "dtd_sps_issues": len(report.issues),
        "profile": report.validator_profile,
    }


def _adapter_sanitization_gate() -> dict[str, Any]:
    sample_content = "PRIVATE-CONTENT-MUST-NOT-LEAK"
    raw = {
        "rows": [
            {
                "status": "CRITICAL",
                "group": "article-id",
                "title": "required identifier",
                "message": sample_content,
                "advice": sample_content,
                "got_value": sample_content,
                "xpath": f"/article[@id='{sample_content}']",
            },
            {"status": "OK", "group": "article-id", "message": sample_content},
        ],
        "article": {"title": sample_content, "authors": [sample_content]},
    }
    sanitized = sanitize_validator_result(raw)
    payload = canonical_bytes(sanitized)
    if sample_content.encode() in payload:
        raise AssertionError("validator adapter leaked source-derived content")
    if sanitized["summary"] != {"critical": 1, "ok": 1}:
        raise AssertionError("validator adapter severity summary is incomplete")
    findings = sanitized["findings"]
    if not isinstance(findings, list) or len(findings) != 1:
        raise AssertionError("validator adapter did not retain the blocking finding")
    return {
        "raw_findings": 2,
        "retained_findings": 1,
        "sanitized_sha256": hashlib.sha256(payload).hexdigest(),
    }


def _command_contract_gate() -> dict[str, Any]:
    candidate = b"<article/>"
    candidate_sha = hashlib.sha256(candidate).hexdigest()
    program = (
        "import hashlib,json,sys;"
        "payload=open(sys.argv[1],'rb').read();"
        "print(json.dumps({"
        "'adapter_contract':'1.1.0','validator_name':'fixture',"
        "'validator_version':'1.0','profile_id':'sps-1.10/jats-1.3',"
        "'candidate_sha256':hashlib.sha256(payload).hexdigest(),"
        "'result':{'complete':True,'findings':[],'summary':{'ok':1}}"
        "},sort_keys=True))"
    )
    specification = ValidatorCommand(
        name="fixture",
        version="1.0",
        profile_id=PROFILE,
        command=(sys.executable, "-c", program, "{candidate}"),
        input_suffix=".xml",
        environment="qualification-fixture",
        timeout_seconds=10,
        max_output_bytes=8192,
        tool_sha256="a" * 64,
    )
    engine = ValidationEngine()
    completed = engine.execute(candidate, specification)
    if not completed.passed or completed.candidate_sha256 != candidate_sha:
        raise AssertionError("valid adapter contract did not pass")
    mutations = {
        "invalid-json": b"not-json",
        "candidate-mismatch": json.dumps(
            {
                "adapter_contract": "1.1.0",
                "validator_name": "fixture",
                "validator_version": "1.0",
                "profile_id": PROFILE,
                "candidate_sha256": "0" * 64,
                "result": [],
            }
        ).encode(),
        "version-mismatch": json.dumps(
            {
                "adapter_contract": "1.1.0",
                "validator_name": "fixture",
                "validator_version": "wrong",
                "profile_id": PROFILE,
                "candidate_sha256": candidate_sha,
                "result": [],
            }
        ).encode(),
    }
    expected = {
        "invalid-json": "validator-invalid-contract",
        "candidate-mismatch": "validator-candidate-mismatch",
        "version-mismatch": "validator-version-mismatch",
    }
    for name, output in mutations.items():
        failed = engine.ingest(candidate, specification, output)
        if failed.status != ValidatorStatus.FAILED or failed.failure_code != expected[name]:
            raise AssertionError(f"adapter contract mutation was not rejected: {name}")
    return {
        "positive_contracts": 1,
        "negative_contracts": len(mutations),
        "sanitized_output_sha256": completed.sanitized_output_sha256,
    }


def _xpm_gate() -> dict[str, Any]:
    report = b"""<html><body><!-- 4.0.096 22/04/2019 -->
    Total of blocking errors: 0 Total of fatal errors: 0
    Total of errors: 0 Total of warnings: 0</body></html>"""
    report_sha = hashlib.sha256(report).hexdigest()
    parser = XpmReportParser()
    result = parser.parse_attested(
        report,
        XpmAttestation(
            candidate_package_sha256="b" * 64,
            report_sha256=report_sha,
            tool_sha256="c" * 64,
            xpm_version="4.0.096",
            command_id="qualification-xpm",
            environment="dedicated-windows-worker-fixture",
        ),
    )
    if not result.passed:
        raise AssertionError("attested zero-error XPM report did not pass")
    if parser.parse(
        report,
        candidate_package_sha256="b" * 64,
        tool_sha256="c" * 64,
    ).passed:
        raise AssertionError("unattested XPM report passed")
    duplicate = report.replace(b"Total of warnings: 0", b"Total of warnings: 0 " * 2)
    try:
        parser.parse(
            duplicate,
            candidate_package_sha256="b" * 64,
            tool_sha256="c" * 64,
        )
    except ValueError:
        pass
    else:
        raise AssertionError("ambiguous XPM report passed")
    return {"attested_reports": 1, "negative_reports": 2, "report_sha256": report_sha}


def _package_gate() -> dict[str, Any]:
    xml = b"""<article xmlns:xlink="http://www.w3.org/1999/xlink"><body><p>
    <inline-graphic xlink:href="equation.svg"/></p></body></article>"""
    files = PackageBuilder().scielo_files(
        package_stem="article",
        xml=xml,
        pdf=b"%PDF-1.4 fixture",
        assets=(AssetPayload(source_name="equation.svg", data=b"<svg/>"),),
    )
    if [item.name for item in files] != [
        "article.xml",
        "article.pdf",
        "article-gf01.svg",
    ]:
        raise AssertionError("inline graphic was not packaged deterministically")
    return {"files": len(files), "inline_assets": 1}


def _registry_gate(root: Path) -> tuple[dict[str, Any], ValidatorRegistry]:
    registry_path = root / "config" / "validator-registry-v1.json"
    registry = load_validator_registry(registry_path)
    revisions: dict[str, dict[str, str]] = {}
    for name in ("packtools", "spsvalidator"):
        active = registry.select(name, ValidatorChannel.ACTIVE)
        rollback = registry.select(name, ValidatorChannel.ROLLBACK)
        if active.source_revision == rollback.source_revision:
            raise AssertionError("validator update and rollback revisions are identical")
        for artifact in (active, rollback):
            if not (root / artifact.dockerfile).is_file():
                raise AssertionError("validator Dockerfile is missing")
        revisions[name] = {
            "active": active.source_revision,
            "rollback": rollback.source_revision,
        }
    adapters = (
        root / "ops" / "packtools_validate.py",
        root / "ops" / "spsvalidator_validate.py",
        root / "ops" / "validator_adapter_common.py",
    )
    return (
        {
            "registry_sha256": hashlib.sha256(registry_path.read_bytes()).hexdigest(),
            "adapter_sha256": {
                path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in adapters
            },
            "revisions": revisions,
        },
        registry,
    )


def _external_evidence(
    entries: list[list[str]],
    registry: ValidatorRegistry,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    engine = ValidationEngine()
    seen: set[tuple[str, str]] = set()
    for name, channel_value, candidate_value, result_value in entries:
        channel = ValidatorChannel(channel_value)
        artifact = registry.select(name, channel)
        key = (name, channel.value)
        if key in seen:
            raise ValueError("external validator evidence cannot be duplicated")
        seen.add(key)
        specification = artifact.command_specification()
        candidate = Path(candidate_value).read_bytes()
        run = engine.ingest(candidate, specification, Path(result_value).read_bytes())
        if run.status != ValidatorStatus.COMPLETED:
            raise AssertionError(f"external validator did not complete: {name}/{channel.value}")
        if any(issue.category == IssueCategory.SYSTEM for issue in run.issues):
            raise AssertionError(
                f"external validator emitted a system issue: {name}/{channel.value}"
            )
        rows.append(
            {
                "name": name,
                "channel": channel.value,
                "version": run.version,
                "candidate_sha256": run.candidate_sha256,
                "tool_sha256": run.tool_sha256,
                "sanitized_output_sha256": run.sanitized_output_sha256,
                "counts": run.counts,
            }
        )
    expected = {
        (name, channel.value)
        for name in ("packtools", "spsvalidator")
        for channel in ValidatorChannel
    }
    if entries and seen != expected:
        raise ValueError("external evidence must cover active and rollback for both validators")
    return sorted(rows, key=lambda row: (str(row["name"]), str(row["channel"])))


def _historical_xpm(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    payload = path.read_bytes()
    parsed = XpmReportParser().parse(
        payload,
        candidate_package_sha256="d" * 64,
        tool_sha256=None,
    )
    return {
        "version": parsed.xpm_version,
        "report_sha256": parsed.report_sha256,
        "blocking_errors": parsed.blocking_errors,
        "fatal_errors": parsed.fatal_errors,
        "errors": parsed.errors,
        "warnings": parsed.warnings,
        "attested_for_candidate": parsed.attested,
        "passed_for_release": parsed.passed,
        "parser_recovered": parsed.parser_recovered,
        "parser_errors": parsed.parser_errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--vendor",
        type=Path,
        default=Path(__file__).parents[1] / "vendor" / "jats" / "1.3",
    )
    parser.add_argument(
        "--external-evidence",
        nargs=4,
        action="append",
        default=[],
        metavar=("VALIDATOR", "CHANNEL", "CANDIDATE", "RESULT"),
    )
    parser.add_argument("--historical-xpm", type=Path)
    parser.add_argument("--require-external", action="store_true")
    parser.add_argument("--require-historical-xpm", action="store_true")
    arguments = parser.parse_args()
    root = Path(__file__).parents[1]
    rows: list[dict[str, Any]] = []
    registry: ValidatorRegistry | None = None
    gates: tuple[tuple[str, Callable[[], dict[str, Any]]], ...] = (
        ("formal_offline", lambda: _formal_offline_gate(arguments.vendor)),
        ("adapter_sanitization", _adapter_sanitization_gate),
        ("command_contract", _command_contract_gate),
        ("xpm_contract", _xpm_gate),
        ("inline_package", _package_gate),
    )
    try:
        registry_metrics, registry = _registry_gate(root)
    except Exception as exc:
        rows.append({"case": "validator_registry", "passed": False, "error": type(exc).__name__})
    else:
        rows.append({"case": "validator_registry", "passed": True, "metrics": registry_metrics})
    for name, gate in gates:
        try:
            metrics = gate()
        except Exception as exc:
            rows.append({"case": name, "passed": False, "error": type(exc).__name__})
        else:
            rows.append({"case": name, "passed": True, "metrics": metrics})
    external: list[dict[str, Any]] = []
    if registry is not None:
        try:
            external = _external_evidence(arguments.external_evidence, registry)
        except Exception as exc:
            rows.append(
                {"case": "external_validators", "passed": False, "error": type(exc).__name__}
            )
        else:
            rows.append(
                {
                    "case": "external_validators",
                    "passed": bool(external) or not arguments.require_external,
                    "metrics": {"runs": external},
                }
            )
    try:
        historical = _historical_xpm(arguments.historical_xpm)
    except Exception as exc:
        rows.append({"case": "historical_xpm", "passed": False, "error": type(exc).__name__})
    else:
        rows.append(
            {
                "case": "historical_xpm",
                "passed": historical is not None or not arguments.require_historical_xpm,
                "metrics": historical,
            }
        )
    approved = all(bool(row["passed"]) for row in rows)
    report = {
        "version": "phase7-v06-gate-1.0",
        "family": "V-06",
        "approved": approved,
        "rows": rows,
        "external_validator_runs": len(external),
        "network_required_by_gate": False,
        "restricted_content_emitted": False,
        "release_candidate_approved": False,
        "xpm_windows_worker_pending": True,
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if approved else 2


if __name__ == "__main__":
    raise SystemExit(main())
