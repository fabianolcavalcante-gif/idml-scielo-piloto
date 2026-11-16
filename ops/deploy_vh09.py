"""Scoped VH-09 VPS deployment, additive migration, verified backup and image rollback.

No secrets are printed. Only API/worker are replaced; the prior image and all
backups remain. This is a development update, not G-HOMOLOG or automatic release.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import time
from pathlib import Path

from ops.phase7_7c08_vps import snapshot

ROOT = Path("/opt/idml-platform")
NAME = "vh09-20261020-v1"
STAGE = ROOT / "releases" / NAME
IMAGE = f"idml-foundation:{NAME}"
TEST_IMAGE = f"idml-foundation:{NAME}-qualification"
POSTGRES_QUALIFIER = "ops.qualify_vh09_postgres"
EXPECTED_MIGRATION = "b9d0e1f20314"
EXTRA_TESTS = ()
COMPOSE = [
    "docker",
    "compose",
    "--env-file",
    str(ROOT / ".env"),
    "-f",
    str(ROOT / "deploy/docker-compose.dev.yml"),
]
APPS = {"idml-development-api-1", "idml-development-worker-1"}


def run(*args, environment=None, log=None, timeout=900):
    result = subprocess.run(  # noqa: S603 - trusted fixed operational commands
        args,
        cwd=ROOT,
        env=environment,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if log:
        (STAGE / log).write_bytes(result.stdout + result.stderr)
        (STAGE / log).chmod(0o600)
    if result.returncode:
        raise RuntimeError(f"deployment_command_failed:{log or args[0]}")
    return result.stdout.decode().strip()


def write(name, payload):
    (STAGE / name).write_text(json.dumps(payload, indent=2))
    (STAGE / name).chmod(0o600)


def database_info():
    return json.loads(
        run(
            "docker",
            "exec",
            "idml-development-api-1",
            "python",
            "-c",
            "import os,json; from sqlalchemy import create_engine,text; "
            "e=create_engine(os.environ['IDML_DATABASE_URL']); c=e.connect(); "
            "print(json.dumps({'migration':c.scalar("
            "text('select version_num from alembic_version')),"
            "'jobs':dict(c.execute(text('select state,count(*) from jobs group by state')).all()),"
            "'counts':{t:c.scalar(text('select count(*) from '+t)) for t in "
            "('organizations','users','artifacts','domain_snapshots','agent_runs','agent_proposals')},"
            "'restore_exists':bool(c.scalar(text(\"select 1 from pg_database "
            "where datname='idml_restore_test'\")))})); c.close(); e.dispose()",
        )
    )


def verify_sources():
    manifest = json.loads((STAGE / "release-source-manifest.json").read_text())
    assert manifest["release"] == NAME and manifest["private_inputs_included"] is False
    for name, expected in manifest["files"].items():
        path = STAGE / name
        assert path.resolve().is_relative_to(STAGE) and not path.is_symlink()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, name
    return manifest


def healthy():
    for _ in range(60):
        rows = snapshot()
        if all(rows.get(n, {}).get("health") == "healthy" for n in APPS):
            run("curl", "--fail", "--silent", "http://127.0.0.1:18080/health/ready", timeout=10)
            return
        time.sleep(2)
    raise RuntimeError("candidate_health_timeout")


def unaffected(before):
    current = snapshot()
    assert all(current.get(n) == row for n, row in before.items() if n not in APPS)
    assert all(current[n]["flags_disabled"] for n in APPS)
    assert all(not current[n]["provider_credential_present"] for n in APPS)
    return current


def prepare():
    assert not (STAGE / "backup.json").exists(), "prepare_already_completed"
    verify_sources()
    assert shutil.disk_usage(ROOT).free > 7 * 1024**3, "insufficient_disk"
    # Preserve server-specific Compose changes instead of silently overwriting them.
    assert (ROOT / "deploy/docker-compose.dev.yml").read_bytes() == (
        STAGE / "deploy/docker-compose.dev.yml"
    ).read_bytes(), "compose_diff_requires_review"
    before = snapshot()
    info = database_info()
    assert not info["restore_exists"], "existing_restore_database_refused"
    assert not any(
        info["jobs"].get(state, 0) for state in ("queued", "running", "failed_retryable")
    ), "active_jobs_require_drain"
    write("before.json", before)
    write("database-before.json", info)
    paused = False
    try:
        run("docker", "pause", *sorted(APPS))
        paused = True
        backup = run("sh", "ops/backup.sh", log="backup.log")
    finally:
        if paused:
            run("docker", "unpause", *sorted(APPS))
    assert Path(backup).resolve().parent == ROOT / "backups"
    run("sh", "ops/restore-test.sh", backup, log="restore-test.log")
    paths = [
        "src",
        "config",
        "profiles",
        "schemas",
        "prompts",
        "ops",
        "deploy",
        "tests",
        "docs",
        "openclaw",
        "migrations",
        "benchmarks/agents",
        "benchmarks/qualification",
        "corpus",
        "vendor",
        "pyproject.toml",
        "requirements.lock",
        "requirements-dev.lock",
        "alembic.ini",
        "README.md",
        ".dockerignore",
    ]
    paths = [p for p in paths if (ROOT / p).exists()]
    run("tar", "-czf", str(STAGE / "rollback-source.tar.gz"), *paths)
    shutil.copy2(ROOT / ".env", STAGE / "rollback.env")
    (STAGE / "rollback.env").chmod(0o600)
    healthy()
    unaffected(before)
    write(
        "backup.json",
        {
            "backup": backup,
            "restore_passed": True,
            "previous_image": before["idml-development-api-1"]["image"],
        },
    )
    print("backup and isolated restore passed; existing services preserved", flush=True)


def build():
    verify_sources()
    assert json.loads((STAGE / "backup.json").read_text())["restore_passed"]
    # Source must be traversable by the unprivileged qualification container.
    # Recovery archive may contain private corpus: protect it before opening the directory.
    (STAGE / "rollback-source.tar.gz").chmod(0o600)
    (STAGE / "rollback.env").chmod(0o600)
    STAGE.chmod(0o755)
    run(
        "docker",
        "build",
        "--memory=768m",
        "--cpu-period=100000",
        "--cpu-quota=50000",
        "-t",
        IMAGE,
        "-f",
        str(STAGE / "deploy/Dockerfile"),
        str(STAGE),
        log="build.log",
    )
    run(
        "docker",
        "build",
        "--memory=512m",
        "--cpu-period=100000",
        "--cpu-quota=35000",
        "--build-arg",
        f"BASE_IMAGE={IMAGE}",
        "-t",
        TEST_IMAGE,
        "-f",
        str(STAGE / "deploy/Dockerfile.qualification"),
        str(STAGE),
        log="qualification-build.log",
    )
    print("runtime and isolated qualification images built", flush=True)


def qualify():
    verify_sources()
    # Tests use /tmp only and have no network/provider access.
    run(
        "docker",
        "run",
        "--rm",
        "--read-only",
        "--network",
        "none",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--memory=512m",
        "--cpus=0.5",
        "--pids-limit=128",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,size=256m,mode=1777",  # noqa: S108 - isolated container tmpfs
        "-e",
        "IDML_ARTIFACT_DISK_RESERVE_BYTES=1",
        "-e",
        "PYTHONPATH=/app/src:/qualification",
        "-v",
        f"{STAGE}:/qualification:ro",
        "-w",
        "/qualification",
        TEST_IMAGE,
        "python",
        "-m",
        "pytest",
        "-o",
        "addopts=-q --strict-markers",
        "-p",
        "no:cacheprovider",
        "--no-cov",
        "tests/test_autocorrection_history.py",
        "tests/test_autocorrection_package.py",
        "tests/test_autocorrection_sources.py",
        "tests/test_autocorrection_executor.py",
        "tests/test_autocorrection_evidence_pipeline.py",
        "tests/test_phase3_pipeline.py",
        "tests/test_phase5_review_ui.py",
        *EXTRA_TESTS,
        log="linux-tests.log",
    )
    environment = os.environ | {"IDML_IMAGE_TAG": f"{NAME}-qualification"}
    run(
        *COMPOSE,
        "run",
        "--rm",
        "--no-deps",
        "-T",
        "-v",
        f"{STAGE}:/qualification:ro",
        "-w",
        "/qualification",
        "-e",
        "PYTHONPATH=/app/src:/qualification",
        "migrate",
        "python",
        "-m",
        POSTGRES_QUALIFIER,
        environment=environment,
        log="postgres-tests.log",
    )
    assert '"passed": true' in (STAGE / "postgres-tests.log").read_text()
    unaffected(json.loads((STAGE / "before.json").read_text()))
    write(
        "qualification.json",
        {
            "linux_tests": True,
            "postgresql_native": True,
            "migration": EXPECTED_MIGRATION,
            "release_approved": False,
        },
    )
    print("Linux regressions and isolated PostgreSQL migration/concurrency passed", flush=True)


def activate():
    manifest = verify_sources()
    assert json.loads((STAGE / "qualification.json").read_text())["postgresql_native"]
    backup = json.loads((STAGE / "backup.json").read_text())
    previous = backup["previous_image"]
    before = json.loads((STAGE / "before.json").read_text())
    info = database_info()
    assert not any(info["jobs"].get(s, 0) for s in ("queued", "running", "failed_retryable"))
    # Only allowlisted source members (no .env, corpus bytes or symlinks).
    with tarfile.open(STAGE / "source.tar.gz") as archive:
        for item in archive:
            assert item.isfile() and item.name in {
                *manifest["files"],
                "release-source-manifest.json",
            }
        archive.extractall(ROOT, filter="data")
    environment = os.environ | {"IDML_IMAGE_TAG": NAME}
    try:
        run(
            *COMPOSE,
            "run",
            "--rm",
            "--no-deps",
            "-T",
            "migrate",
            environment=environment,
            log="migration.log",
        )
        run(
            *COMPOSE,
            "up",
            "-d",
            "--no-deps",
            "api",
            "worker",
            environment=environment,
            log="activate.log",
        )
        healthy()
        assert database_info()["migration"] == EXPECTED_MIGRATION
        if EXPECTED_MIGRATION == "c0e1f2031425":
            # A pre-head image cannot interpret restored heads. This initial rollout
            # must remain free of transitions while exercising the old image.
            heads = run(
                "docker",
                "exec",
                "idml-development-api-1",
                "python",
                "-c",
                "import os; from sqlalchemy import create_engine,text; "
                "e=create_engine(os.environ['IDML_DATABASE_URL']); "
                "c=e.connect(); "
                "print(c.scalar(text('select count(*) from canonical_head_events'))); "
                "c.close(); e.dispose()",
            )
            assert int(heads) == 0, "head_transitions_require_head_aware_rollback"
        # Additive schema must also support the retained previous image.
        old_env = os.environ | {"IDML_IMAGE_TAG": previous.split(":", 1)[1]}
        run(
            *COMPOSE,
            "up",
            "-d",
            "--no-deps",
            "api",
            "worker",
            environment=old_env,
            log="rollback-test.log",
        )
        healthy()
        assert all(snapshot()[n]["image"] == previous for n in APPS)
        run(
            *COMPOSE,
            "up",
            "-d",
            "--no-deps",
            "api",
            "worker",
            environment=environment,
            log="reapply.log",
        )
        healthy()
        current = unaffected(before)
        assert all(current[n]["image"] == IMAGE for n in APPS)
        after_info = database_info()
        assert after_info["counts"] == info["counts"], "existing_data_counts_changed"
        # Verify bytes in the actual running image, not only the uploaded checkout.
        runtime = {
            p: digest
            for p, digest in manifest["files"].items()
            if p.split("/")[0]
            in {"src", "config", "profiles", "schemas", "prompts", "migrations", "vendor"}
            or p in {"pyproject.toml", "requirements.lock", "alembic.ini"}
        }
        checker = (
            "import hashlib,json,os; from pathlib import Path; "
            "expected=json.loads(" + repr(json.dumps(runtime)) + "); "
            "assert all(hashlib.sha256((Path('/app')/p).read_bytes()).hexdigest()==h "
            "for p,h in expected.items()); "
            "assert all(not os.access(Path('/app')/p,os.W_OK) for p in expected); "
            "print(len(expected))"
        )
        verified = int(run("docker", "exec", "idml-development-api-1", "python", "-c", checker))
        lines = (ROOT / ".env").read_text().splitlines()
        lines = [s for s in lines if not s.startswith("IDML_IMAGE_TAG=")]
        (ROOT / ".env").write_text("\n".join([*lines, f"IDML_IMAGE_TAG={NAME}", ""]))
        (ROOT / ".env").chmod(0o600)
        write("after.json", current)
        write(
            "deployment.json",
            {
                "release": NAME,
                "image": IMAGE,
                "migration": after_info["migration"],
                "runtime_files_verified": verified,
                "backup": backup["backup"],
                "restore_test": True,
                "image_rollback_test": True,
                "other_services_unchanged": True,
                "existing_data_counts_unchanged": True,
                "flags_disabled": True,
                "homologation_ready": False,
                "release_approved": False,
            },
        )
        print(
            "candidate deployed; image rollback tested; existing services and data preserved",
            flush=True,
        )
    except Exception:
        if EXPECTED_MIGRATION == "c0e1f2031425":
            # After activation, refuse blind downgrade to a head-unaware image.
            # This also fails closed if the current state cannot be inspected.
            state = snapshot()
            if state.get("idml-development-api-1", {}).get("image") == IMAGE:
                heads = run(
                    "docker",
                    "exec",
                    "idml-development-api-1",
                    "python",
                    "-c",
                    "import os; from sqlalchemy import create_engine,text; "
                    "e=create_engine(os.environ['IDML_DATABASE_URL']); c=e.connect(); "
                    "print(c.scalar(text('select count(*) from canonical_head_events'))); "
                    "c.close(); e.dispose()",
                )
                if int(heads):
                    lines = (ROOT / ".env").read_text().splitlines()
                    lines = [s for s in lines if not s.startswith("IDML_IMAGE_TAG=")]
                    (ROOT / ".env").write_text("\n".join([*lines, f"IDML_IMAGE_TAG={NAME}", ""]))
                    (ROOT / ".env").chmod(0o600)
                    raise RuntimeError("head_transitions_present_keep_head_aware_image") from None
        shutil.copy2(STAGE / "rollback.env", ROOT / ".env")
        run(*COMPOSE, "up", "-d", "--no-deps", "api", "worker", log="recovery.log")
        run("tar", "-xzf", str(STAGE / "rollback-source.tar.gz"), "-C", str(ROOT))
        healthy()
        # Additive tables remain: never downgrade an active database on failure.
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "build", "qualify", "activate"))
    args = parser.parse_args()
    assert STAGE.resolve() == STAGE and STAGE.is_dir()
    {"prepare": prepare, "build": build, "qualify": qualify, "activate": activate}[args.action]()


if __name__ == "__main__":
    main()
