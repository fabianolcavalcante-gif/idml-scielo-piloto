"""Host-only, isolated restore drill for one existing backup; never starts restored agents."""

import argparse
import json
import re
import shutil
import sqlite3
import subprocess
import tempfile
import time
from pathlib import Path

from ops.observe_phase7_v12 import containers, sample, violations
from ops.plan_backup_retention import inventory
from ops.verify_backup import restore_tar, verify_checksums

STAGE = Path("/opt/idml-platform/qualification/v12-backup-v1")
ROOT = Path("/opt/idml-platform/backups")
NAME = "idml-v12-backup-restore"


def command(*args, input_file=None):
    # Capture diagnostics, which may contain SQL or credentials; expose only generic errors.
    result = subprocess.run(  # noqa: S603 - fixed commands and validated local paths
        args, stdin=input_file, capture_output=True, timeout=45, check=False
    )
    if result.returncode:
        raise RuntimeError("restore_command_failed")
    return result.stdout.decode().strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backup", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"\d{8}T\d{6}Z", args.backup):
        parser.error("canonical backup timestamp required")
    backup = ROOT / args.backup
    if backup.is_symlink() or backup.resolve().parent != ROOT.resolve():
        parser.error("unsafe backup path")
    if STAGE.is_symlink() or not STAGE.is_dir():
        parser.error("qualification stage missing")
    report = {"version": "backup-restore-1.0", "approved": False, "backup": args.backup}
    cid = scratch = None
    baseline = containers()
    samples = []
    began = time.monotonic()

    def check():
        current = sample()
        failures = violations(current, None, ready_limit_ms=500)
        samples.append(current)
        current_services = containers()
        if any(current_services.get(k) != v for k, v in baseline.items()):
            failures.append("existing_service_changed")
        if time.monotonic() - began > 180:
            failures.append("deadline")
        if failures:
            raise RuntimeError("resource_or_service_guard")

    try:
        check()
        if samples[-1]["memory_available_bytes"] < 768 * 1024**2:
            raise RuntimeError("insufficient_memory_headroom")
        if NAME in command("docker", "ps", "-a", "--format", "{{.Names}}").split():
            raise RuntimeError("existing_lab_refused")
        report["inventory"] = inventory(ROOT)
        report["checksum"] = verify_checksums(backup)
        check()
        scratch = Path(tempfile.mkdtemp(prefix="restore-", dir=STAGE))
        report["artifacts"] = restore_tar(backup / "artifacts.tar.gz", scratch / "artifacts")
        report["openclaw"] = restore_tar(backup / "openclaw-state.tar.gz", scratch / "openclaw")
        state = scratch / "openclaw/state/openclaw.sqlite"
        if not state.is_file() or not (scratch / "openclaw/openclaw.json").is_file():
            raise RuntimeError("missing_openclaw_state")
        with sqlite3.connect(f"file:{state}?mode=ro", uri=True) as connection:
            if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                raise RuntimeError("sqlite_integrity_failed")
        report["sqlite_integrity"] = True
        check()
        # Resolve the already installed image. No pull, external port, credentials or live volume.
        image = command("docker", "image", "inspect", "postgres:16-alpine", "--format", "{{.Id}}")
        report["postgres_image_id"] = image
        cid = command(
            "docker",
            "create",
            "--name",
            NAME,
            "--network=none",
            "--read-only",
            "--user=70:70",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--memory=192m",
            "--memory-swap=192m",
            "--cpus=0.25",
            "--pids-limit=40",
            "--log-driver=none",
            "--tmpfs",
            "/var/lib/postgresql/data:rw,nosuid,nodev,size=128m,uid=70,gid=70",
            "--tmpfs",
            "/var/run/postgresql:rw,nosuid,nodev,size=4m,uid=70,gid=70",
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,size=8m,uid=70,gid=70",  # noqa: S108
            "-e",
            "POSTGRES_HOST_AUTH_METHOD=trust",
            "-e",
            "POSTGRES_DB=restore_test",
            image,
            "postgres",
            "-c",
            "shared_buffers=16MB",
            "-c",
            "max_connections=10",
            "-c",
            "listen_addresses=",
        )
        command("docker", "start", cid)
        for _ in range(40):
            check()
            try:
                command("docker", "exec", cid, "pg_isready", "-U", "postgres", "-d", "restore_test")
                # The entrypoint briefly runs a temporary server; wait for final PID1 postgres.
                comm = command("docker", "exec", cid, "cat", "/proc/1/comm")
                if comm == "postgres":
                    break
            except RuntimeError:
                pass
            time.sleep(1)
        else:
            raise RuntimeError("postgres_not_ready")
        with (backup / "database.dump").open("rb") as stream:
            command(
                "docker",
                "exec",
                "-i",
                cid,
                "pg_restore",
                "-U",
                "postgres",
                "-d",
                "restore_test",
                "--no-owner",
                "--no-privileges",
                "--exit-on-error",
                input_file=stream,
            )
        check()

        def sql(query):
            return command(
                "docker",
                "exec",
                cid,
                "psql",
                "-U",
                "postgres",
                "-d",
                "restore_test",
                "-v",
                "ON_ERROR_STOP=1",
                "-Atc",
                query,
            )

        count = int(
            sql("select count(*) from information_schema.tables where table_schema='public'")
        )
        if count < 10:
            raise RuntimeError("restored_schema_incomplete")
        report["public_tables"] = count
        # Query only the isolated restored database; never emit artifact identifiers/content.
        rows = json.loads(
            sql(
                "select coalesce(json_agg(row_to_json(a)), '[]') from "
                "(select storage_key, sha256, size_bytes from artifacts) a"
            )
        )
        import hashlib

        verified = 0
        for row in rows:
            key = row["storage_key"]
            if not re.fullmatch(r"[0-9a-f-]{36}/[0-9a-f]{2}/[0-9a-f]{64}", key):
                raise RuntimeError("invalid_restored_key")
            path = scratch / "artifacts" / key
            if not path.is_file() or path.stat().st_size != row["size_bytes"]:
                raise RuntimeError("restored_artifact_missing_or_size")
            with path.open("rb") as stream:
                digest = hashlib.sha256()
                while chunk := stream.read(1024 * 1024):
                    digest.update(chunk)
            if digest.hexdigest() != row["sha256"]:
                raise RuntimeError("restored_artifact_hash")
            verified += 1
        report["registered_artifacts_hash_verified"] = verified
        state = json.loads(command("docker", "inspect", "--format", "{{json .State}}", cid))
        if state["OOMKilled"] or not state["Running"]:
            raise RuntimeError("restore_container_failed")
        report["oom_killed"] = False
        report["approved"] = True
    except Exception as exc:
        report["error_type"] = type(exc).__name__
        # No arbitrary exception messages, SQL, file names or credentials in the public report.
    finally:
        try:
            if cid:
                command("docker", "rm", "-f", cid)
            if scratch:
                if scratch.is_symlink() or scratch.resolve().parent != STAGE.resolve():
                    raise RuntimeError("unsafe_cleanup")
                shutil.rmtree(scratch)
            report["cleanup_complete"] = True
        except Exception:
            report["cleanup_complete"] = False
            report["approved"] = False
        final_services = containers()
        report["existing_services_unchanged"] = all(
            final_services.get(k) == v for k, v in baseline.items()
        )
        report["samples"] = len(samples)
        report["min_memory_available_bytes"] = min(s["memory_available_bytes"] for s in samples)
        report["max_ready_ms"] = max(s["ready_ms"] for s in samples)
        report["approved"] &= report["existing_services_unchanged"]
        report["live_database_modified"] = False
        report["restored_agents_started"] = False
        report["release_ready"] = False
        print(json.dumps(report, sort_keys=True))
    return 0 if report["approved"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
