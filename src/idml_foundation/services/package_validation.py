"""Package-bound external validation orchestration; never implies editorial/go-live approval."""

import hashlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

from idml_foundation.release.validation_engine import (
    ValidationEngine,
    ValidatorCommand,
    ValidatorRun,
    ValidatorStatus,
)
from idml_foundation.release.validator_registry import (
    ValidatorChannel,
    ValidatorRegistry,
    load_validator_registry,
)
from idml_foundation.services.scoped_validator_transport import ScopedValidatorExecutor
from idml_foundation.services.xpm_execution import XpmExecutor, assess_xpm_execution
from idml_foundation.services.xpm_socket import XpmSocketExecutor
from idml_foundation.settings import Settings

Executor = Callable[[bytes, ValidatorCommand], ValidatorRun]


def assess_rebuilt_package(
    *,
    xml: bytes,
    package: bytes,
    scope: dict[str, str],
    settings: Settings,
    offline_valid: bool,
    executor: Executor | None,
    xpm_executor: XpmExecutor | None,
) -> dict[str, Any]:
    """Bind transports only after the corrected or restored bytes are known."""
    if not offline_valid:
        executor = xpm_executor = None
    elif executor is None and xpm_executor is None and settings.validator_scoped_authorities:
        if settings.validator_socket is not None:
            executor = ScopedValidatorExecutor(settings.validator_socket, scope=scope)
        if settings.xpm_socket is not None:
            xpm_executor = XpmSocketExecutor(settings.xpm_socket)
    return assess_package(
        xml=xml,
        package=package,
        executor=executor,
        xpm_executor=xpm_executor,
        registry_path=settings.validator_registry_path,
        expected_scope=scope,
    )


def assess_package(
    *,
    xml: bytes,
    package: bytes,
    registry: ValidatorRegistry | None = None,
    executor: Executor | None = None,
    registry_path: Path | None = None,
    xpm_executor: XpmExecutor | None = None,
    expected_scope: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Executors/scope are server dependencies, never request data or model output."""
    engine = ValidationEngine()
    runs = []
    evidence = []
    xpm = assess_xpm_execution(
        xml=xml, package=package, expected_scope=expected_scope, executor=None
    )
    try:
        registry = registry or load_validator_registry(
            registry_path
            or Path(__file__).resolve().parents[3] / "config/validator-registry-v1.json"
        )
        for name in ("packtools", "spsvalidator"):
            artifact = registry.select(name, ValidatorChannel.ACTIVE)
            specification = artifact.command_specification()
            candidate = xml if specification.input_suffix == ".xml" else package
            digest = hashlib.sha256(candidate).hexdigest()
            if executor is None:
                run = engine.unavailable(
                    name,
                    specification.version,
                    candidate,
                    "executor-not-configured",
                    tool_sha256=specification.tool_sha256,
                )
            else:
                try:
                    run = executor(candidate, specification)
                    if (
                        run.name != name
                        or run.version != specification.version
                        or run.candidate_sha256 != digest
                        or run.tool_sha256 != specification.tool_sha256
                        or run.profile_id != specification.profile_id
                        or run.adapter_contract != specification.adapter_contract
                        or (
                            run.status == ValidatorStatus.COMPLETED
                            and not run.sanitized_output_sha256
                        )
                    ):
                        raise ValueError("external evidence mismatch")
                except Exception:
                    # Execution diagnostics can contain article text or environment secrets.
                    run = engine.unavailable(
                        name,
                        specification.version,
                        candidate,
                        "executor-failed-or-evidence-mismatch",
                        tool_sha256=specification.tool_sha256,
                    )
            runs.append(run)
            evidence.append(
                {
                    "name": name,
                    "version": run.version,
                    "status": run.status.value,
                    "candidate_sha256": digest,
                    "input_kind": specification.input_suffix,
                    "tool_sha256": run.tool_sha256,
                    "passed": run.passed,
                    "counts": run.counts,
                    "unavailable_external_checks": sorted(
                        {
                            issue.code.removeprefix("external-verification-unavailable-")
                            for issue in run.issues
                            if issue.code.startswith("external-verification-unavailable-")
                        }
                    ),
                    "report_sha256": run.sanitized_output_sha256,
                    "failure_code": None
                    if run.status == ValidatorStatus.COMPLETED
                    else "validator-unavailable-or-failed",
                }
            )
            if isinstance(executor, ScopedValidatorExecutor) and name in executor.evidence:
                evidence[-1]["authority_verification"] = executor.evidence[name]
        xpm = assess_xpm_execution(
            xml=xml,
            package=package,
            expected_scope=expected_scope,
            executor=xpm_executor,
            independent_runs=tuple(runs),
        )
        known_errors = any(
            run.status == ValidatorStatus.COMPLETED and not run.passed for run in runs
        )
        reasons = []
        if xpm["status"] != "completed":
            reasons.append(xpm["failure_code"])
        else:
            if any(xpm["counts"][key] for key in ("blocking_errors", "fatal_errors", "errors")):
                known_errors = True
                reasons.append("xpm-validator-findings")
            if xpm["counts"]["warnings"]:
                reasons.append("xpm-warnings-pending")
            if not xpm["required_queries_complete"]:
                reasons.append("xpm-required-queries-incomplete")
            queries = xpm.get("selected_queries", {})
            query_checks = queries.get("checks", []) + queries.get("crossref_author_links", {}).get(
                "checks", []
            )
            if any(check["status"] == "conflict" for check in query_checks):
                known_errors = True
                reasons.append("xpm-authority-response-conflict")
            if queries.get("status") == "unavailable" or any(
                check["status"] == "unavailable" for check in query_checks
            ):
                reasons.append("xpm-authority-response-unavailable")
            # Transport success is not qualification of compatibility or promotion.
            reasons.append("formal-approval-integration-pending")
        state = "blocked" if known_errors else "validation-unavailable"
        if known_errors:
            reasons.append("external-validator-findings")
        if any(row["unavailable_external_checks"] for row in evidence):
            reasons.append("external-verification-unavailable")
        if any(run.status != ValidatorStatus.COMPLETED for run in runs):
            reasons.append("required-validator-unavailable")
    except (OSError, ValueError):
        state, reasons = "validation-unavailable", ["validator-registry-unavailable"]
    return {
        "version": "package-formal-assessment-1.0",
        "package_sha256": hashlib.sha256(package).hexdigest(),
        "xml_sha256": hashlib.sha256(xml).hexdigest(),
        "state": state,
        "reasons": reasons,
        "required_validators": ["packtools", "spsvalidator", "xpm"],
        "external_runs": evidence,
        "xpm": xpm,
        "complete": False,
        "ready_for_scielo": False,
        "editorial_approval": "separate-workflow",
        "production_activation_authorized": False,
    }
