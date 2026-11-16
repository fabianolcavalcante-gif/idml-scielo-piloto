#!/usr/bin/env python3
"""Run the deterministic V-10 operational-workflow qualification gate."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from idml_foundation.main import create_app
from idml_foundation.release.package_builder import PackageBuilder, PackageInput, PackageRole
from idml_foundation.routers.ui import _HTML, _JS
from idml_foundation.schemas import JobCreate
from idml_foundation.services.jobs import TRANSITIONS
from idml_foundation.settings import Settings

ROOT = Path(__file__).parents[1]
REPORT = ROOT / "benchmarks/qualification/reports/v10-operational-workflow-vh19-v1.json"


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("V-10 report must be a JSON object")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _published_report_gate(report: dict[str, Any]) -> dict[str, Any]:
    if report.get("version") != "phase7-v10-operational-workflow-1.0":
        raise ValueError("unsupported V-10 report version")
    if report.get("family") != "V-10" or report.get("v10_approved") is not True:
        raise ValueError("V-10 is not approved")
    scenarios = report.get("critical_scenarios", [])
    if len(scenarios) < 13 or any(row.get("result") != "passed" for row in scenarios):
        raise ValueError("V-10 critical scenario is not approved")
    if report.get("release_candidate_approved") is not False:
        raise ValueError("V-10 cannot approve the release candidate")
    if report.get("production_activation_authorized") is not False:
        raise ValueError("V-10 cannot authorize production activation")
    if any(report.get("privacy", {}).values()):
        raise ValueError("V-10 public report violates the content-safe contract")
    expected = report.get("source_sha256", {})
    actual = {name: _sha256(ROOT / name) for name in expected}
    if actual != expected:
        raise ValueError("V-10 source evidence hash mismatch")
    return {
        "report_sha256": _sha256(REPORT),
        "source_files": len(actual),
        "critical_scenarios": len(scenarios),
        "full_tests": report.get("full_tests"),
        "line_coverage_percent": report.get("line_coverage_percent"),
    }


def _api_contract_gate() -> dict[str, Any]:
    schema = create_app().openapi()
    required = {
        ("post", "/v1/resources"),
        ("post", "/v1/artifacts/idml"),
        ("post", "/v1/artifacts/assets"),
        ("get", "/v1/artifacts/{artifact_id}/download"),
        ("post", "/v1/jobs"),
        ("get", "/v1/jobs/{job_id}"),
        ("get", "/v1/jobs/{job_id}/events"),
        ("post", "/v1/jobs/{job_id}/cancel"),
        ("post", "/v1/jobs/{job_id}/retry"),
        ("post", "/v1/reviews"),
        ("post", "/v1/reviews/{item_id}/claim"),
        ("post", "/v1/reviews/{item_id}/decisions"),
        ("post", "/v1/releases"),
        ("post", "/v1/releases/{request_id}/approvals"),
    }
    missing = [
        f"{method} {path}" for method, path in required if method not in schema["paths"][path]
    ]
    if missing:
        raise AssertionError(f"V-10 operational endpoint missing: {missing}")
    for _method, path in required:
        operation = schema["paths"][path]
        if not any(item.get("security") for item in operation.values() if isinstance(item, dict)):
            raise AssertionError(f"V-10 endpoint is not authenticated: {path}")
    return {"operational_endpoints": len(required), "authenticated": True}


def _job_contract_gate() -> dict[str, Any]:
    process = JobCreate.model_validate(
        {
            "kind": "idml.process",
            "idempotency_key": "v10-gate-process",
            "payload": {"resource_id": "resource", "idml_artifact_id": "artifact"},
        }
    )
    package = JobCreate.model_validate(
        {
            "kind": "scielo.package",
            "idempotency_key": "v10-gate-package",
            "payload": {
                "resource_id": "resource",
                "canonical_snapshot_id": "snapshot",
                "idml_artifact_id": "idml",
                "pdf_artifact_id": "pdf",
                "asset_artifact_ids": ["asset"],
            },
        }
    )
    try:
        JobCreate.model_validate(
            {
                "kind": "idml.process",
                "idempotency_key": "v10-gate-invalid",
                "payload": {
                    "resource_id": "resource",
                    "idml_artifact_id": "artifact",
                    "organization_id": "forbidden",
                },
            }
        )
    except ValidationError:
        pass
    else:
        raise AssertionError("V-10 job payload accepted an unknown tenant field")
    expected_transitions = {
        ("queued", "running"),
        ("queued", "cancelled"),
        ("running", "failed_retryable"),
        ("failed_retryable", "queued"),
    }
    actual = {(source, target) for source, targets in TRANSITIONS.items() for target in targets}
    if not expected_transitions.issubset(actual):
        raise AssertionError("V-10 job control transitions are incomplete")
    return {
        "job_kinds": [process.kind, package.kind],
        "required_transitions": len(expected_transitions),
        "strict_payloads": True,
    }


def _package_integrity_gate() -> dict[str, Any]:
    files = (
        PackageInput(
            name="article.xml",
            role=PackageRole.XML,
            media_type="application/xml",
            data=b"<article/>",
        ),
        PackageInput(
            name="article.pdf",
            role=PackageRole.PDF,
            media_type="application/pdf",
            data=b"%PDF-1.4\n",
        ),
    )
    builder = PackageBuilder()
    first = builder.build(
        article_id="e20240001",
        profile_id="v10-gate",
        source_idml_sha256="a" * 64,
        files=files,
        validator_versions={"offline": "gate"},
    )
    second = builder.build(
        article_id="e20240001",
        profile_id="v10-gate",
        source_idml_sha256="a" * 64,
        files=tuple(reversed(files)),
        validator_versions={"offline": "gate"},
    )
    if first.archive != second.archive or first.package_sha256 != second.package_sha256:
        raise AssertionError("V-10 package output is not deterministic")
    if hashlib.sha256(first.archive).hexdigest() != first.package_sha256:
        raise AssertionError("V-10 package digest does not bind the archive")
    return {
        "deterministic": True,
        "manifest_files": len(first.manifest.files),
        "package_sha256": first.package_sha256,
    }


def _interface_and_degraded_gate() -> dict[str, Any]:
    html_markers = (
        "Criar artigo",
        "Converter IDML",
        "Revisão e pacote SciELO",
        'id="input-article"',
        'id="process-idml"',
        'id="package-pdf"',
        "Criar pendência",
        "Aprovação editorial",
        "Auditoria",
    )
    js_markers = (
        "idml.process",
        "scielo.package",
        "data-cancel-job",
        "data-retry-job",
        "error_code",
        "JSON.stringify(j.result",
    )
    missing = [marker for marker in html_markers if marker not in _HTML]
    missing += [marker for marker in js_markers if marker not in _JS]
    if missing:
        raise AssertionError(f"V-10 operator interface control missing: {missing}")
    settings = Settings(environment="test")
    if settings.feature_openclaw or settings.feature_ai_swarm:
        raise AssertionError("V-10 degraded mode defaults enabled an AI feature")
    return {
        "interface_controls": len(html_markers) + len(js_markers),
        "openclaw_enabled": False,
        "swarm_enabled": False,
    }


def main() -> int:
    report = _load(REPORT)
    gates = (
        ("published_report", lambda: _published_report_gate(report)),
        ("api_contract", _api_contract_gate),
        ("job_contract", _job_contract_gate),
        ("package_integrity", _package_integrity_gate),
        ("interface_degraded", _interface_and_degraded_gate),
    )
    rows: list[dict[str, Any]] = []
    for name, gate in gates:
        try:
            metrics = gate()
        except Exception as exc:
            rows.append({"case": name, "passed": False, "error": type(exc).__name__})
        else:
            rows.append({"case": name, "passed": True, "metrics": metrics})
    approved = all(row["passed"] for row in rows)
    result = {
        "version": "phase7-v10-gate-1.0",
        "family": "V-10",
        "approved": approved,
        "release_candidate_approved": False,
        "production_activation_authorized": False,
        "network_required_by_gate": False,
        "restricted_content_emitted": False,
        "rows": rows,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if approved else 1


if __name__ == "__main__":
    raise SystemExit(main())
