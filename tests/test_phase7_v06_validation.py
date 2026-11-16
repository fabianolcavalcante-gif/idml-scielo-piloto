import hashlib
import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from idml_foundation.release.package_builder import AssetPayload, PackageBuilder
from idml_foundation.release.validation_engine import (
    IssueSeverity,
    ValidationEngine,
    ValidatorCommand,
    ValidatorStatus,
    ValidatorWarningAcceptance,
)
from idml_foundation.release.validator_registry import (
    ValidatorChannel,
    load_validator_registry,
)
from idml_foundation.release.xpm import (
    XpmAttestation,
    XpmReportParser,
    XpmWarningAcceptance,
)

PROFILE = "sps-1.10/jats-1.3"
TOOL_SHA = "a" * 64
VERSION = "test-1.0"


def _adapter_program(
    *,
    version: str = VERSION,
    result: str = "[]",
    candidate_sha: str = "hashlib.sha256(payload).hexdigest()",
) -> str:
    return (
        "import hashlib,json,sys;"
        "payload=open(sys.argv[1],'rb').read();"
        f"result={result};"
        "print(json.dumps({"
        "'adapter_contract':'1.1.0',"
        f"'validator_name':'fixture','validator_version':{version!r},"
        f"'profile_id':{PROFILE!r},'candidate_sha256':{candidate_sha},"
        "'result':result},sort_keys=True))"
    )


def _command(program: str, *, timeout: int = 5, max_output: int = 8192) -> ValidatorCommand:
    return ValidatorCommand(
        name="fixture",
        version=VERSION,
        profile_id=PROFILE,
        command=(sys.executable, "-c", program, "{candidate}"),
        input_suffix=".xml",
        environment="test-fixture",
        timeout_seconds=timeout,
        max_output_bytes=max_output,
        tool_sha256=TOOL_SHA,
    )


def _xpm_report(*, warnings: int = 0) -> bytes:
    return f"""<html><body><!-- 4.0.096 22/04/2019 -->
    Total of blocking errors: 0
    Total of fatal errors: 0
    Total of errors: 0
    Total of warnings: {warnings}
    </body></html>""".encode()


def test_external_normalization_preserves_severity_and_fails_on_exceptions() -> None:
    candidate = b"<article/>"
    engine = ValidationEngine()
    run = engine.external_run(
        candidate,
        [
            {"response": "OK", "message": "valid"},
            {"status": "INFO", "message": "informational"},
            {"status": "WARNING", "message": "review this", "code": "warning-1"},
            {"status": "ERROR", "message": "invalid value", "code": "error-1"},
            {"status": "CRITICAL", "message": "missing asset", "code": "critical-1"},
            {"status": "BLOCKING", "message": "invalid package", "code": "blocking-1"},
        ],
        name="fixture",
        version=VERSION,
        tool_sha256=TOOL_SHA,
        profile_id=PROFILE,
    )
    assert run.status == ValidatorStatus.COMPLETED
    assert [issue.severity for issue in run.issues] == [
        IssueSeverity.BLOCKING,
        IssueSeverity.CRITICAL,
        IssueSeverity.ERROR,
        IssueSeverity.WARNING,
    ]
    assert run.counts == {"blocking": 1, "critical": 1, "error": 1, "warning": 1}
    assert not run.passed

    exception = engine.external_run(
        candidate,
        {"exceptions": [{"response": "exception", "error": "private path"}]},
        name="fixture",
        version=VERSION,
        tool_sha256=TOOL_SHA,
    )
    assert exception.status == ValidatorStatus.FAILED
    assert exception.failure_code == "validator-exception-or-invalid-output"
    assert exception.issues[0].severity == IssueSeverity.CRITICAL

    unknown = engine.external_run(
        candidate,
        [{"status": "SURPRISE", "message": "unknown"}],
        name="fixture",
        version=VERSION,
        tool_sha256=TOOL_SHA,
    )
    assert unknown.status == ValidatorStatus.FAILED
    assert unknown.issues[0].code == "adapter-unknown-severity"


def test_warning_requires_exact_auditable_acceptance() -> None:
    engine = ValidationEngine()
    run = engine.external_run(
        b"<article/>",
        [{"status": "WARNING", "message": "Known false positive", "code": "known-warning"}],
        name="fixture",
        version=VERSION,
        tool_sha256=TOOL_SHA,
        profile_id=PROFILE,
    )
    assert not run.passed
    warning = run.issues[0]
    accepted = engine.accept_warning(
        run,
        ValidatorWarningAcceptance(
            acceptance_id="wa-1",
            validator_name="fixture",
            validator_version=VERSION,
            profile_id=PROFILE,
            issue_sha256=warning.fingerprint,
            accepted_by="qualification-policy-v1",
            justification="Falso positivo reproduzido e documentado nesta fixture controlada.",
            evidence_sha256="b" * 64,
        ),
    )
    assert accepted.passed
    with pytest.raises(ValueError, match="exactly one"):
        engine.accept_warning(
            run,
            ValidatorWarningAcceptance(
                acceptance_id="wa-2",
                validator_name="fixture",
                validator_version=VERSION,
                profile_id=PROFILE,
                issue_sha256="c" * 64,
                accepted_by="qualification-policy-v1",
                justification="Esta aceitação deliberadamente não corresponde à advertência.",
                evidence_sha256="b" * 64,
            ),
        )


def test_validator_command_contract_success_and_fail_closed_paths() -> None:
    engine = ValidationEngine()
    candidate = b"<article/>"
    completed = engine.execute(candidate, _command(_adapter_program()))
    assert completed.status == ValidatorStatus.COMPLETED
    assert completed.passed
    assert completed.sanitized_output_sha256
    assert completed.command[-1] == "{candidate}"

    mismatch = engine.execute(
        candidate,
        _command(_adapter_program(candidate_sha="'0' * 64")),
    )
    assert mismatch.failure_code == "validator-candidate-mismatch"

    wrong_version = engine.execute(
        candidate,
        _command(_adapter_program(version="wrong-version")),
    )
    assert wrong_version.failure_code == "validator-version-mismatch"

    invalid = engine.execute(candidate, _command("print('not-json')"))
    assert invalid.failure_code == "validator-invalid-contract"

    nonzero = engine.execute(candidate, _command("raise SystemExit(3)"))
    assert nonzero.failure_code == "validator-nonzero-exit"

    timeout = engine.execute(
        candidate,
        _command("import time;time.sleep(2)", timeout=1),
    )
    assert timeout.failure_code == "validator-timeout"

    oversized = engine.execute(
        candidate,
        _command("print('x'*2048)", max_output=1024),
    )
    assert oversized.failure_code == "validator-output-too-large"


def test_validator_output_paths_and_control_characters_are_sanitized() -> None:
    result = (
        "[{'status':'WARNING','code':'path-warning',"
        "'message':sys.argv[1]+'\\u001b[31m\\u200b secret'}]"
    )
    run = ValidationEngine().execute(b"<article/>", _command(_adapter_program(result=result)))
    assert run.status == ValidatorStatus.COMPLETED
    assert run.issues[0].message == "<candidate-path> secret"


def test_xpm_requires_unique_bounded_attested_evidence_and_warning_acceptance() -> None:
    report = _xpm_report(warnings=1)
    package_sha = "d" * 64
    parser = XpmReportParser()
    unattested = parser.parse(
        report,
        candidate_package_sha256=package_sha,
        tool_sha256=TOOL_SHA,
    )
    assert not unattested.passed
    attestation = XpmAttestation(
        candidate_package_sha256=package_sha,
        report_sha256=hashlib.sha256(report).hexdigest(),
        tool_sha256=TOOL_SHA,
        xpm_version="4.0.096",
        command_id="xpm-package-maker",
        environment="dedicated-windows-worker",
    )
    attested = parser.parse_attested(report, attestation)
    assert not attested.passed
    accepted = parser.accept_warnings(
        attested,
        XpmWarningAcceptance(
            acceptance_id="xpm-wa-1",
            xpm_version="4.0.096",
            warning_count=1,
            report_sha256=attestation.report_sha256,
            accepted_by="qualification-policy-v1",
            justification="Advertência conhecida e reproduzida nesta fixture de qualificação.",
            evidence_sha256=attestation.report_sha256,
        ),
    )
    assert accepted.passed

    with pytest.raises(ValueError, match="hash mismatch"):
        parser.parse_attested(
            report,
            attestation.model_copy(update={"report_sha256": "e" * 64}),
        )
    duplicate = report.replace(
        b"Total of warnings: 1",
        b"Total of warnings: 1 Total of warnings: 0",
    )
    with pytest.raises(ValueError, match="exactly one warnings"):
        parser.parse(
            duplicate,
            candidate_package_sha256=package_sha,
            tool_sha256=TOOL_SHA,
        )
    with pytest.raises(ValueError, match="between 1 byte and 8 MiB"):
        parser.parse(
            b"x" * (8 * 1024 * 1024 + 1),
            candidate_package_sha256=package_sha,
            tool_sha256=TOOL_SHA,
        )


def test_inline_graphics_are_packaged_and_rebound() -> None:
    xml = b"""<article xmlns:xlink="http://www.w3.org/1999/xlink"><body><p>
    <inline-graphic xlink:href="equation.svg"/></p></body></article>"""
    files = PackageBuilder().scielo_files(
        package_stem="article",
        xml=xml,
        pdf=b"%PDF-fixture",
        assets=(AssetPayload(source_name="equation.svg", data=b"<svg/>"),),
    )
    assert [item.name for item in files] == [
        "article.xml",
        "article.pdf",
        "article-gf01.svg",
    ]
    assert b"article-gf01.svg" in files[0].data


def test_validator_registry_has_distinct_update_and_rollback_revisions() -> None:
    registry = load_validator_registry(
        Path(__file__).parents[1] / "config" / "validator-registry-v1.json"
    )
    for name in ("packtools", "spsvalidator"):
        active = registry.select(name, ValidatorChannel.ACTIVE)
        rollback = registry.select(name, ValidatorChannel.ROLLBACK)
        assert active.source_revision != rollback.source_revision
        assert active.version != rollback.version
        assert active.image_id is not None
        assert active.command_specification().tool_sha256 == active.image_id.removeprefix("sha256:")

    raw = json.loads(
        (Path(__file__).parents[1] / "config" / "validator-registry-v1.json").read_text()
    )
    raw["validators"] = raw["validators"][:-1]
    with pytest.raises(ValidationError, match="active and one rollback"):
        type(registry).model_validate(raw)
