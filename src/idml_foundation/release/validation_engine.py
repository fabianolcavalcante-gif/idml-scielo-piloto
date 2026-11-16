from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import unicodedata
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import Field, model_validator

from idml_foundation.domain.common import SHA256_PATTERN, StrictModel, canonical_bytes
from idml_foundation.pipeline.validation import ValidationReport

_ANSI_ESCAPE = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


class ValidatorStatus(StrEnum):
    COMPLETED = "completed"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


class IssueSeverity(StrEnum):
    BLOCKING = "blocking"
    CRITICAL = "critical"
    ERROR = "error"
    WARNING = "warning"


_SEVERITY_RANK = {
    IssueSeverity.BLOCKING: 0,
    IssueSeverity.CRITICAL: 1,
    IssueSeverity.ERROR: 2,
    IssueSeverity.WARNING: 3,
}


class IssueCategory(StrEnum):
    DETERMINISTIC = "deterministic"
    SEMANTIC = "semantic"
    MISSING_SOURCE = "missing-source"
    SOURCE_CONFLICT = "source-conflict"
    SYSTEM = "system"


class UnifiedIssue(StrictModel):
    validator: str
    severity: IssueSeverity
    category: IssueCategory
    code: str
    message: str
    location: str | None = None
    warning_acceptance_id: str | None = None
    warning_justification: str | None = Field(default=None, min_length=20, max_length=1000)

    @model_validator(mode="after")
    def warning_acceptance_is_explicit(self) -> Self:
        accepted = self.warning_acceptance_id is not None or self.warning_justification is not None
        if accepted and self.severity != IssueSeverity.WARNING:
            raise ValueError("only warnings can be accepted")
        if (self.warning_acceptance_id is None) != (self.warning_justification is None):
            raise ValueError("warning acceptance requires id and justification")
        return self

    @property
    def accepted(self) -> bool:
        return self.warning_acceptance_id is not None

    @property
    def fingerprint(self) -> str:
        payload = self.model_dump(
            mode="json", exclude={"warning_acceptance_id", "warning_justification"}
        )
        return hashlib.sha256(canonical_bytes(payload)).hexdigest()


class ValidatorWarningAcceptance(StrictModel):
    acceptance_id: str = Field(min_length=1, max_length=100)
    validator_name: str = Field(min_length=1, max_length=100)
    validator_version: str = Field(min_length=1, max_length=100)
    profile_id: str = Field(min_length=1, max_length=100)
    issue_sha256: str = Field(pattern=SHA256_PATTERN)
    accepted_by: str = Field(min_length=1, max_length=200)
    justification: str = Field(min_length=20, max_length=1000)
    evidence_sha256: str = Field(pattern=SHA256_PATTERN)


class ValidatorRun(StrictModel):
    name: str
    version: str
    status: ValidatorStatus
    candidate_sha256: str = Field(pattern=SHA256_PATTERN)
    tool_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    adapter_contract: str | None = None
    profile_id: str | None = None
    command: tuple[str, ...] = ()
    environment: str | None = None
    sanitized_output_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    issues: tuple[UnifiedIssue, ...] = ()
    failure_code: str | None = None

    @property
    def passed(self) -> bool:
        return self.status == ValidatorStatus.COMPLETED and not any(
            issue.severity != IssueSeverity.WARNING or not issue.accepted for issue in self.issues
        )

    @property
    def counts(self) -> dict[str, int]:
        return {
            severity.value: sum(issue.severity == severity for issue in self.issues)
            for severity in IssueSeverity
        }


class UnifiedValidationReport(StrictModel):
    report_version: str = "1.1.0"
    candidate_sha256: str = Field(pattern=SHA256_PATTERN)
    required_validators: tuple[str, ...]
    runs: tuple[ValidatorRun, ...]

    @property
    def complete(self) -> bool:
        completed = {run.name for run in self.runs if run.status == ValidatorStatus.COMPLETED}
        return set(self.required_validators) <= completed

    @property
    def valid(self) -> bool:
        required = set(self.required_validators)
        return self.complete and all(run.passed for run in self.runs if run.name in required)


class ValidatorCommand(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=100)
    profile_id: str = Field(min_length=1, max_length=100)
    adapter_contract: Literal["1.1.0"] = "1.1.0"
    command: tuple[str, ...] = Field(min_length=1, max_length=30)
    input_suffix: Literal[".xml", ".zip"]
    environment: str = Field(min_length=1, max_length=200)
    timeout_seconds: int = Field(default=300, ge=1, le=1800)
    max_output_bytes: int = Field(default=8 * 1024 * 1024, ge=1024, le=64 * 1024 * 1024)
    tool_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def candidate_placeholder_is_exact(self) -> Self:
        if sum(part.count("{candidate}") for part in self.command) != 1:
            raise ValueError("validator command requires exactly one {candidate} placeholder")
        return self


class AdapterEnvelope(StrictModel):
    adapter_contract: Literal["1.1.0"]
    validator_name: str
    validator_version: str
    profile_id: str
    candidate_sha256: str = Field(pattern=SHA256_PATTERN)
    result: Any


class ValidationEngine:
    """Normalize and execute validators while failing closed on incomplete evidence."""

    def offline_run(
        self, report: ValidationReport, *, candidate_sha256: str | None = None
    ) -> ValidatorRun:
        issues = tuple(
            UnifiedIssue(
                validator="offline-jats",
                severity=IssueSeverity(issue.severity.value),
                category=IssueCategory.DETERMINISTIC,
                code=issue.code,
                message=self._sanitize(issue.message, ()),
                location=str(issue.line) if issue.line else issue.element_id,
            )
            for issue in report.issues
        )
        return ValidatorRun(
            name="offline-jats",
            version=report.validator_profile,
            status=ValidatorStatus.COMPLETED,
            candidate_sha256=candidate_sha256 or report.xml_sha256,
            profile_id=report.validator_profile,
            environment="application-runtime/offline-catalog",
            issues=issues,
        )

    def packtools_run(
        self,
        xml: bytes,
        raw_results: object,
        *,
        version: str = "4.17.2",
        tool_sha256: str,
    ) -> ValidatorRun:
        return self.external_run(
            xml,
            raw_results,
            name="packtools",
            version=version,
            tool_sha256=tool_sha256,
        )

    def external_run(
        self,
        candidate: bytes,
        raw_results: object,
        *,
        name: str,
        version: str,
        tool_sha256: str,
        adapter_contract: str | None = None,
        profile_id: str | None = None,
        command: tuple[str, ...] = (),
        environment: str | None = None,
        sanitized_output_sha256: str | None = None,
        sanitization_tokens: tuple[str, ...] = (),
    ) -> ValidatorRun:
        candidate_sha = hashlib.sha256(candidate).hexdigest()
        issues: list[UnifiedIssue] = []
        validator_failed = False
        for position, item in enumerate(self._result_items(raw_results)):
            severity, unknown = self._severity(item)
            if severity is None and not unknown:
                continue
            if unknown:
                validator_failed = True
                severity = IssueSeverity.CRITICAL
                item = {
                    "code": "adapter-unknown-severity",
                    "message": "Validator emitted an unsupported severity value",
                }
            response = str(item.get("response", "")).casefold()
            if response == "exception":
                validator_failed = True
                severity = IssueSeverity.CRITICAL
            code_value = item.get(
                "code",
                item.get(
                    "id",
                    item.get("rule", item.get("item", item.get("group", f"{name}-{position + 1}"))),
                ),
            )
            code = self._sanitize(str(code_value), sanitization_tokens)[:200] or f"{name}-issue"
            message_value = item.get(
                "message",
                item.get("msg", item.get("text", item.get("error", code))),
            )
            message = self._sanitize(str(message_value), sanitization_tokens)[:2000] or code
            location_value = item.get(
                "xpath",
                item.get("path", item.get("line", item.get("parent", item.get("parent_id")))),
            )
            issues.append(
                UnifiedIssue(
                    validator=name,
                    severity=severity or IssueSeverity.CRITICAL,
                    category=(
                        IssueCategory.SYSTEM
                        if response == "exception" or unknown
                        else self._category(code, message)
                    ),
                    code=code,
                    message=message,
                    location=(
                        self._sanitize(str(location_value), sanitization_tokens)[:500]
                        if location_value is not None
                        else None
                    ),
                )
            )
        issues.sort(
            key=lambda issue: (_SEVERITY_RANK[issue.severity], issue.code, issue.location or "")
        )
        return ValidatorRun(
            name=name,
            version=version,
            status=ValidatorStatus.FAILED if validator_failed else ValidatorStatus.COMPLETED,
            candidate_sha256=candidate_sha,
            tool_sha256=tool_sha256,
            adapter_contract=adapter_contract,
            profile_id=profile_id,
            command=command,
            environment=environment,
            sanitized_output_sha256=sanitized_output_sha256,
            issues=tuple(issues),
            failure_code="validator-exception-or-invalid-output" if validator_failed else None,
        )

    def execute(self, candidate: bytes, specification: ValidatorCommand) -> ValidatorRun:
        command_template = specification.command
        with tempfile.TemporaryDirectory(prefix="idml-validator-") as temporary:
            candidate_path = Path(temporary) / f"candidate{specification.input_suffix}"
            candidate_path.write_bytes(candidate)
            command = tuple(
                part.replace("{candidate}", str(candidate_path)) for part in command_template
            )
            try:
                completed = subprocess.run(  # noqa: S603 - explicit immutable command tuple
                    command,
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    check=False,
                    timeout=specification.timeout_seconds,
                    env=self._subprocess_environment(),
                )
            except FileNotFoundError:
                return self._failed_from_spec(
                    candidate, specification, "validator-executable-missing"
                )
            except subprocess.TimeoutExpired:
                return self._failed_from_spec(candidate, specification, "validator-timeout")
            if completed.returncode != 0:
                return self._failed_from_spec(candidate, specification, "validator-nonzero-exit")
            return self.ingest(
                candidate,
                specification,
                completed.stdout,
                sanitization_tokens=(temporary, str(candidate_path)),
            )

    def ingest(
        self,
        candidate: bytes,
        specification: ValidatorCommand,
        adapter_output: bytes,
        *,
        sanitization_tokens: tuple[str, ...] = (),
    ) -> ValidatorRun:
        if len(adapter_output) > specification.max_output_bytes:
            return self._failed_from_spec(candidate, specification, "validator-output-too-large")
        try:
            decoded = adapter_output.decode("utf-8", errors="strict")
            raw_envelope = json.loads(decoded)
            envelope = AdapterEnvelope.model_validate(raw_envelope)
            sanitized_hash = hashlib.sha256(canonical_bytes(raw_envelope)).hexdigest()
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError):
            return self._failed_from_spec(candidate, specification, "validator-invalid-contract")
        expected_sha = hashlib.sha256(candidate).hexdigest()
        if envelope.candidate_sha256 != expected_sha:
            return self._failed_from_spec(candidate, specification, "validator-candidate-mismatch")
        if (
            envelope.validator_name != specification.name
            or envelope.validator_version != specification.version
            or envelope.profile_id != specification.profile_id
            or envelope.adapter_contract != specification.adapter_contract
        ):
            return self._failed_from_spec(candidate, specification, "validator-version-mismatch")
        return self.external_run(
            candidate,
            envelope.result,
            name=specification.name,
            version=specification.version,
            tool_sha256=specification.tool_sha256,
            adapter_contract=specification.adapter_contract,
            profile_id=specification.profile_id,
            command=specification.command,
            environment=specification.environment,
            sanitized_output_sha256=sanitized_hash,
            sanitization_tokens=sanitization_tokens,
        )

    def unavailable(
        self,
        name: str,
        version: str,
        candidate: bytes,
        code: str,
        *,
        tool_sha256: str | None = None,
    ) -> ValidatorRun:
        return ValidatorRun(
            name=name,
            version=version,
            status=ValidatorStatus.UNAVAILABLE,
            candidate_sha256=hashlib.sha256(candidate).hexdigest(),
            tool_sha256=tool_sha256,
            failure_code=code,
        )

    def aggregate(
        self, candidate: bytes, runs: tuple[ValidatorRun, ...], required: tuple[str, ...]
    ) -> UnifiedValidationReport:
        digest = hashlib.sha256(candidate).hexdigest()
        if any(run.candidate_sha256 != digest for run in runs):
            raise ValueError("validator result does not belong to this candidate")
        if len({run.name for run in runs}) != len(runs):
            raise ValueError("validator names must be unique")
        if len(set(required)) != len(required):
            raise ValueError("required validator names must be unique")
        if not set(required) <= {run.name for run in runs}:
            raise ValueError("required validators must have a run result")
        return UnifiedValidationReport(
            candidate_sha256=digest,
            required_validators=required,
            runs=runs,
        )

    def accept_warning(
        self, run: ValidatorRun, acceptance: ValidatorWarningAcceptance
    ) -> ValidatorRun:
        if (
            acceptance.validator_name != run.name
            or acceptance.validator_version != run.version
            or acceptance.profile_id != run.profile_id
        ):
            raise ValueError("warning acceptance does not match validator provenance")
        matches = [
            position
            for position, issue in enumerate(run.issues)
            if issue.severity == IssueSeverity.WARNING
            and issue.fingerprint == acceptance.issue_sha256
        ]
        if len(matches) != 1:
            raise ValueError("warning acceptance must identify exactly one warning")
        updated = list(run.issues)
        warning = updated[matches[0]]
        updated[matches[0]] = warning.model_copy(
            update={
                "warning_acceptance_id": acceptance.acceptance_id,
                "warning_justification": acceptance.justification,
            }
        )
        return run.model_copy(update={"issues": tuple(updated)})

    def _failed_from_spec(
        self, candidate: bytes, specification: ValidatorCommand, code: str
    ) -> ValidatorRun:
        return ValidatorRun(
            name=specification.name,
            version=specification.version,
            status=ValidatorStatus.FAILED,
            candidate_sha256=hashlib.sha256(candidate).hexdigest(),
            tool_sha256=specification.tool_sha256,
            adapter_contract=specification.adapter_contract,
            profile_id=specification.profile_id,
            command=specification.command,
            environment=specification.environment,
            failure_code=code,
        )

    def _result_items(self, value: object, *, depth: int = 0) -> list[dict[str, Any]]:
        if depth > 20:
            return [
                {
                    "response": "exception",
                    "code": "adapter-result-too-deep",
                    "error": "Validator output exceeded the nesting limit",
                }
            ]
        found: list[dict[str, Any]] = []
        if isinstance(value, dict):
            keys = {str(key) for key in value}
            if keys & {"message", "msg", "text", "error"} and keys & {
                "level",
                "severity",
                "status",
                "response",
                "type",
            }:
                found.append({str(key): item for key, item in value.items()})
            else:
                for item in value.values():
                    found.extend(self._result_items(item, depth=depth + 1))
        elif isinstance(value, (list, tuple)):
            for item in value:
                found.extend(self._result_items(item, depth=depth + 1))
        if len(found) > 100_000:
            return [
                {
                    "response": "exception",
                    "code": "adapter-result-too-large",
                    "error": "Validator output exceeded the issue limit",
                }
            ]
        return found

    def _severity(self, item: dict[str, Any]) -> tuple[IssueSeverity | None, bool]:
        raw = item.get(
            "level",
            item.get("severity", item.get("status", item.get("response", "error"))),
        )
        value = str(raw).strip().casefold().replace("_", "-")
        if value in {"ok", "pass", "passed", "success", "valid", "info", "not-applicable"}:
            return None, False
        if value in {"blocking", "blocking-error", "blocker"}:
            return IssueSeverity.BLOCKING, False
        if value in {"critical", "fatal", "exception"}:
            return IssueSeverity.CRITICAL, False
        if value in {"error", "invalid", "failure", "failed"}:
            return IssueSeverity.ERROR, False
        if value in {"warning", "warn"}:
            return IssueSeverity.WARNING, False
        return None, True

    def _sanitize(self, value: str, tokens: tuple[str, ...]) -> str:
        sanitized = _ANSI_ESCAPE.sub("", value)
        for token in sorted((item for item in tokens if item), key=len, reverse=True):
            sanitized = sanitized.replace(token, "<candidate-path>")
        sanitized = "".join(
            character
            for character in sanitized
            if character in "\t\n\r" or unicodedata.category(character) not in {"Cc", "Cf"}
        )
        return " ".join(sanitized.split())

    def _subprocess_environment(self) -> dict[str, str]:
        allowed = ("PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "TEMP", "TMP")
        environment = {key: os.environ[key] for key in allowed if key in os.environ}
        environment.update({"PYTHONIOENCODING": "utf-8", "LANG": "C.UTF-8"})
        return environment

    def _category(self, code: str, message: str) -> IssueCategory:
        if code.startswith("external-verification-unavailable-"):
            return IssueCategory.SYSTEM
        text = f"{code} {message}".casefold()
        if any(token in text for token in ("missing", "required", "not found", "absent")):
            return IssueCategory.MISSING_SOURCE
        if any(token in text for token in ("conflict", "inconsistent", "mismatch")):
            return IssueCategory.SOURCE_CONFLICT
        if any(token in text for token in ("xpath", "schema", "dtd", "attribute", "element")):
            return IssueCategory.DETERMINISTIC
        return IssueCategory.SEMANTIC
