"""Isolated real XPM socket qualification; never changes active services or grants."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile

from ops.qualify_vh1_xpm_linux import checked_members, health, mutate
from ops.xpm_validator_broker import IMAGE

BASELINE = Path("/opt/idml-platform/private/qualification/vh1-journal-metadata-20261016T165250Z")
QUALIFICATION_IMAGE = "idml-foundation:vh09-heads-20261021-v1-qualification"


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def client():
    from idml_foundation.services.xpm_execution import assess_xpm_execution
    from idml_foundation.services.xpm_socket import XpmSocketExecutor

    scope = json.loads(Path("/case/scope.json").read_bytes())
    package = Path("/case/candidate.zip").read_bytes()
    with ZipFile(BytesIO(package)) as archive:
        xml = next(v for n, v in checked_members(archive).items() if n.endswith(".xml"))
    if Path("/case/modern-manifest.json").exists():
        from idml_foundation.release.validation_engine import ValidationEngine
        from idml_foundation.services.package_validation import assess_package
        from idml_foundation.services.scoped_validator_transport import check_evidence

        manifest = json.loads(Path("/case/modern-manifest.json").read_bytes())
        if manifest["scope"] != scope:
            raise ValueError("modern_scope_mismatch")

        def modern(candidate, specification):
            name = specification.name
            if name not in manifest["responses"]:
                return ValidationEngine().unavailable(
                    name,
                    specification.version,
                    candidate,
                    "qualification-native-input-refused",
                    tool_sha256=specification.tool_sha256,
                )
            raw = Path("/case/" + name + "-response.json").read_bytes()
            if hashlib.sha256(raw).hexdigest() != manifest["responses"][name]:
                raise ValueError("modern_report_changed")
            check_evidence(json.loads(raw)["result"]["authority_evidence"], scope)
            return ValidationEngine().ingest(candidate, specification, raw)

        result = assess_package(
            xml=xml,
            package=package,
            expected_scope=scope,
            registry_path=Path("/qualification/config/validator-registry-vh1-composed.json"),
            executor=modern,
            xpm_executor=XpmSocketExecutor(Path("/socket/xpm.sock")),
        )
        print(json.dumps(result))
        return
    result = assess_xpm_execution(
        xml=xml,
        package=package,
        expected_scope=scope,
        executor=XpmSocketExecutor(Path("/socket/xpm.sock")),
    )
    print(json.dumps(result))


def run(source, *, online=False, semantic=False, composed=False, modern_root=None):
    os.umask(0o077)
    root = BASELINE.parent / datetime.now(timezone.utc).strftime(  # noqa: UP017 - host 3.10
        (
            "vh1-xpm-composed-"
            if composed
            else "vh1-xpm-semantic-"
            if semantic
            else "vh1-xpm-socket-online-"
            if online
            else "vh1-xpm-socket-"
        )
        + "%Y%m%dT%H%M%SZ"
    )
    root.mkdir(mode=0o700)
    before = health()
    write(root / "before.json", before)
    plan = json.loads((BASELINE / "plan.json").read_bytes())
    cases = []
    matrix = [
        ("esa-e20240086", "baseline"),
        ("esa-e20240135", "baseline"),
        ("esa-e20240086", "missing_journal_title"),
        ("esa-e20240086", "malformed_xml"),
    ]
    for article, mutation in matrix:
        case = root / (article + "-" + mutation)
        case.mkdir(mode=0o700)
        package = (BASELINE / article / "candidate.zip").read_bytes()
        if hashlib.sha256(package).hexdigest() != plan["cases"][article]["package_sha256"]:
            raise ValueError("baseline_changed")
        with ZipFile(BytesIO(package)) as archive:
            members = mutate(checked_members(archive), mutation)
        if mutation != "baseline":
            stream = BytesIO()
            with ZipFile(stream, "w") as archive:
                for name, data in members.items():
                    archive.writestr(name, data)
            package = stream.getvalue()
        xml = next(v for n, v in members.items() if n.endswith(".xml"))
        if composed:
            prepared = (modern_root / case.name / "candidate.zip").read_bytes()
            with ZipFile(BytesIO(prepared)) as archive:
                if checked_members(archive) != members:
                    raise ValueError("modern_input_content_mismatch")
            package = prepared  # Same bytes; ZIP timestamps are not regenerated between validators.
        scope = json.loads((BASELINE / article / "scope.json").read_bytes())
        scope.update(
            package_sha256=hashlib.sha256(package).hexdigest(),
            xml_sha256=hashlib.sha256(xml).hexdigest(),
        )
        inputs = case / "inputs"
        inputs.mkdir(mode=0o755)
        inputs.chmod(0o755)  # Narrow mount must be traversable by UID 10001 despite umask.
        (inputs / "candidate.zip").write_bytes(package)
        write(inputs / "scope.json", scope)
        for path in inputs.iterdir():
            path.chmod(0o444)  # Narrow read-only mount; parent case remains root-private.
        if composed:
            if modern_root is None:
                raise ValueError("current_modern_runs_required")
            previous = modern_root / case.name
            manifest = json.loads((previous / "modern-manifest.json").read_bytes())
            if manifest["scope"] != scope:
                raise ValueError("modern_candidate_mismatch")
            for name in [
                "modern-manifest.json",
                *[n + "-response.json" for n in manifest["responses"]],
            ]:
                path = inputs / name
                path.write_bytes((previous / name).read_bytes())
                path.chmod(0o444)
        work = case / "private"
        # AF_UNIX addresses are limited to 108 bytes on Linux; evidence stays private.
        sockets = Path("/run") / ("idml-xpm-" + uuid4().hex)
        work.mkdir(mode=0o700)
        sockets.mkdir(mode=0o755)
        sockets.chmod(0o755)  # Override private umask for the authorized UID's traversal.
        registry = case / "registry.json"
        write(
            registry,
            dict(
                version="xpm-online-composed-1.0"
                if composed
                else "xpm-online-semantic-1.0"
                if semantic
                else "xpm-online-1.0"
                if online
                else "xpm-offline-1.0",
                image=IMAGE,
            ),
        )
        env = dict(os.environ, PYTHONPATH=f"{source}/src:{source}")
        with (case / "broker.log").open("wb") as log:
            process = subprocess.Popen(  # noqa: S603 - fixed admin broker, no shell
                [
                    sys.executable,
                    "-m",
                    "ops.xpm_validator_broker",
                    "--socket",
                    str(sockets / "xpm.sock"),
                    "--work",
                    str(work),
                    "--registry",
                    str(registry),
                    "--once",
                ],
                env=env,
                cwd=source,
                stdout=log,
                stderr=log,
            )
            try:
                deadline = time.monotonic() + 10
                while not (sockets / "xpm.sock").exists():
                    if process.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError("broker_start_failed")
                    time.sleep(0.1)
                command = [
                    "docker",
                    "run",
                    "--rm",
                    "--pull=never",
                    "--read-only",
                    "--network=none",
                    "--user=10001:10001",
                    "--cap-drop=ALL",
                    "--security-opt=no-new-privileges",
                    "--memory=256m",
                    "--cpus=0.25",
                    "--pids-limit=64",
                    "--tmpfs",
                    "/tmp:rw,nosuid,nodev,size=32m",  # noqa: S108 - isolated container tmpfs
                    "-e",
                    "PYTHONPATH=/qualification/src:/qualification",
                    "-v",
                    f"{source}:/qualification:ro",
                    "-v",
                    f"{inputs}:/case:ro",
                    "-v",
                    f"{sockets}:/socket:ro",
                    "-w",
                    "/qualification",
                    QUALIFICATION_IMAGE,
                    "python",
                    "-m",
                    "ops.qualify_vh1_xpm_socket",
                    "--client",
                ]
                result = subprocess.run(command, capture_output=True, timeout=390, check=False)  # noqa: S603
                (case / "client.log").write_bytes(result.stderr)
                if result.returncode:
                    raise RuntimeError("client_execution_failed")
                assessment = json.loads(result.stdout)
                process.wait(timeout=10)
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=25)
                if not list(sockets.iterdir()):
                    sockets.rmdir()
        row = dict(
            article=article,
            mutation=mutation,
            assessment=assessment,
            package_sha256=scope["package_sha256"],
            xml_sha256=scope["xml_sha256"],
        )
        if composed:
            row["package_assessment"] = assessment
            row["assessment"] = assessment["xpm"]
        cases.append(row)
        write(case / "assessment.json", row)
        print(json.dumps(row), flush=True)
    after = health()
    write(root / "after.json", after)
    unchanged = before == after
    report = dict(
        version="vh1-xpm-socket-real-1.0",
        root=str(root),
        cases=cases,
        active_services_unchanged=unchanged,
        production_activated=False,
        formal_xml_approved=False,
        laboratory_scope_only=True,
    )
    write(root / "summary.json", report)
    print(
        json.dumps(dict(summary=str(root / "summary.json"), services_unchanged=unchanged)),
        flush=True,
    )
    if not unchanged:
        raise RuntimeError("active_service_change_detected")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--client", action="store_true")
    parser.add_argument("--online", action="store_true")
    parser.add_argument("--semantic", action="store_true")
    parser.add_argument("--composed", action="store_true")
    parser.add_argument("--modern-root", type=Path)
    parser.add_argument("--source", type=Path)
    args = parser.parse_args()
    if args.client:
        client()
    else:
        run(
            args.source.resolve(strict=True),
            online=args.online or args.semantic or args.composed,
            semantic=args.semantic or args.composed,
            composed=args.composed,
            modern_root=args.modern_root,
        )
