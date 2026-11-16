"""Activate the qualified VH1 candidate, preserving database and current documentation.

Uses the existing scoped backup/build/qualification helpers. Only API and worker
are replaced. Both rollback images understand the existing working-head schema.
"""

import argparse
import json
import os
import shutil
import urllib.error
import urllib.request

from ops import deploy_vh09 as deployment

NAME = "vh1-structural-20261028-v1"
PREVIOUS = "idml-foundation:vh09-heads-20261021-v1"
TESTS = (
    "canonical_heads",
    "snapshots",
    "xpm_structural_compatibility",
    "vh1_structural_sources",
    "vh1_composed_sources",
    "xpm_composed",
    "xpm_runtime_compatibility",
    "xpm_sps_compatibility",
    "xpm_query_requirements",
    "xpm_execution",
    "package_formal_validation",
    "validation_followups",
    "validation_diagnosis",
    "jats_doctype",
    "phase7_v10_workflow",
    "phase7_v11_robustness",
    "jobs",
    "api",
    "auth_and_rbac",
)


def configure():
    deployment.NAME = NAME
    deployment.STAGE = deployment.ROOT / "releases" / NAME
    deployment.IMAGE = f"idml-foundation:{NAME}"
    deployment.TEST_IMAGE = f"{deployment.IMAGE}-qualification"
    deployment.POSTGRES_QUALIFIER = "ops.qualify_vh09_heads_postgres"
    deployment.EXPECTED_MIGRATION = "c0e1f2031425"
    deployment.EXTRA_TESTS = tuple(f"tests/test_{name}.py" for name in TESTS)


def smoke():
    checks = {}
    for path, expected in (("/health/ready", 200), ("/app", 200), ("/v1/resources", 401)):
        try:
            response = urllib.request.urlopen("http://127.0.0.1:18080" + path, timeout=10)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            assert response.status == expected
            checks[path] = response.status
            if path == "/app":
                assert response.headers.get("Content-Security-Policy")
                assert response.headers.get("X-Content-Type-Options") == "nosniff"
    return checks


def refresh_backup():
    """Take a fresh checkpoint after a resumed deployment, preserving preparation."""
    d = deployment
    d.verify_sources()
    info = d.database_info()
    assert not info["restore_exists"]
    assert not any(info["jobs"].get(s, 0) for s in ("queued", "running", "failed_retryable"))
    before = d.snapshot()
    assert all(before[n]["image"] == PREVIOUS for n in d.APPS)
    assert not (d.STAGE / "preactivation.json").exists()
    paused = False
    try:
        d.run("docker", "pause", *sorted(d.APPS))
        paused = True
        backup = d.run("sh", "ops/backup.sh", log="preactivation-backup.log")
    finally:
        if paused:
            d.run("docker", "unpause", *sorted(d.APPS))
    assert d.Path(backup).resolve().parent == d.ROOT / "backups"
    d.run("sh", "ops/restore-test.sh", backup, log="preactivation-restore.log")
    d.healthy()
    d.unaffected(before)
    assert d.database_info() == info
    d.write("preactivation-before.json", before)
    d.write("preactivation.json", dict(backup=backup, restore_passed=True, previous_image=PREVIOUS))
    print("fresh backup and isolated restore passed", flush=True)


def activate():
    d = deployment
    manifest = d.verify_sources()
    assert json.loads((d.STAGE / "qualification.json").read_text())["postgresql_native"]
    checkpoint = (
        "preactivation.json" if (d.STAGE / "preactivation.json").exists() else "backup.json"
    )
    backup = json.loads((d.STAGE / checkpoint).read_text())
    assert backup["previous_image"] == PREVIOUS and backup["restore_passed"]
    baseline = "preactivation-before.json" if checkpoint == "preactivation.json" else "before.json"
    before = json.loads((d.STAGE / baseline).read_text())
    assert all(before[name]["image"] == PREVIOUS for name in d.APPS)
    initial = d.database_info()
    assert initial["migration"] == d.EXPECTED_MIGRATION
    assert not any(initial["jobs"].get(s, 0) for s in ("queued", "running", "failed_retryable"))

    # No migration/source extraction: schema is identical; newer closing docs stay intact.
    def switch(tag, log):
        d.run(
            *d.COMPOSE,
            "up",
            "-d",
            "--no-deps",
            "api",
            "worker",
            environment=os.environ | {"IDML_IMAGE_TAG": tag},
            log=log,
        )
        d.healthy()
        return smoke()

    try:
        switch(NAME, "activate.log")
        assert d.database_info() == initial
        switch(PREVIOUS.split(":", 1)[1], "rollback-test.log")
        assert all(d.snapshot()[n]["image"] == PREVIOUS for n in d.APPS)
        assert d.database_info() == initial
        checks = switch(NAME, "reapply.log")
        current = d.unaffected(before)
        assert all(current[n]["image"] == d.IMAGE for n in d.APPS)
        assert d.database_info() == initial
        runtime = {
            p: h
            for p, h in manifest["files"].items()
            if p.split("/")[0]
            in {"src", "config", "profiles", "schemas", "prompts", "migrations", "vendor"}
            or p in {"pyproject.toml", "requirements.lock", "alembic.ini"}
        }
        checker = (
            "import hashlib,json,os; from pathlib import Path; expected=json.loads("
            + repr(json.dumps(runtime))
            + "); "
            "assert all(hashlib.sha256((Path('/app')/p).read_bytes()).hexdigest()==h "
            "for p,h in expected.items()); "
            "assert all(not os.access(Path('/app')/p,os.W_OK) for p in expected); "
            "print(len(expected))"
        )
        verified = {
            name: int(d.run("docker", "exec", name, "python", "-c", checker))
            for name in sorted(d.APPS)
        }
        lines = (d.ROOT / ".env").read_text().splitlines()
        lines = [s for s in lines if not s.startswith("IDML_IMAGE_TAG=")]
        (d.ROOT / ".env").write_text("\n".join([*lines, f"IDML_IMAGE_TAG={NAME}", ""]))
        (d.ROOT / ".env").chmod(0o600)
        d.write("after.json", current)
        d.write(
            "deployment.json",
            dict(
                release=NAME,
                image=d.IMAGE,
                image_id=current["idml-development-api-1"]["image_id"],
                migration=initial["migration"],
                schema_changed=False,
                runtime_files_verified=verified,
                backup=backup["backup"],
                restore_test=True,
                image_rollback_test=True,
                other_services_unchanged=True,
                existing_data_counts_unchanged=True,
                flags_disabled=True,
                smoke=checks,
                homologation_ready=False,
                release_approved=False,
            ),
        )
        print(
            "candidate active; rollback and smoke passed; data and other services preserved",
            flush=True,
        )
    except Exception:
        shutil.copy2(d.STAGE / "rollback.env", d.ROOT / ".env")
        (d.ROOT / ".env").chmod(0o600)
        switch(PREVIOUS.split(":", 1)[1], "recovery.log")
        d.unaffected(before)
        raise


def qualify():
    # The expanded upload tests retain a 256 MiB free-space reserve. A 256 MiB
    # laboratory tmpfs cannot satisfy that reserve plus the uploaded file.
    # Increase only the test filesystem limit; keep application safeguards intact.
    original = deployment.run

    def laboratory_run(*args, **kwargs):
        args = tuple(
            "/tmp:rw,nosuid,nodev,size=512m,mode=1777"  # noqa: S108 - isolated test tmpfs
            if a == "/tmp:rw,nosuid,nodev,size=256m,mode=1777"  # noqa: S108 - isolated test tmpfs
            else a
            for a in args
        )
        return original(*args, **kwargs)

    deployment.run = laboratory_run
    try:
        deployment.qualify()
    finally:
        deployment.run = original


def main():
    os.umask(0o077)
    configure()
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action", choices=("prepare", "build", "qualify", "refresh-backup", "activate")
    )
    action = parser.parse_args().action
    {
        "prepare": deployment.prepare,
        "build": deployment.build,
        "qualify": qualify,
        "refresh-backup": refresh_backup,
        "activate": activate,
    }[action]()


if __name__ == "__main__":
    main()
