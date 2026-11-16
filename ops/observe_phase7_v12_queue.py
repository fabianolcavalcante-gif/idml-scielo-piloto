"""Host-side watchdog for disposable real queue laboratory; never deploy services."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path

from ops.observe_phase7_v12 import command, containers, laboratory_image, sample, violations

PREFIX = "idml-v12-queue"
NETWORK = PREFIX + "-net"
OVERLAYS = tuple(
    "src/idml_foundation/" + path
    for path in (
        "worker.py",
        "routers/jobs.py",
        "settings.py",
        "main.py",
        "services/artifacts.py",
        "services/storage_budget.py",
        "ingest/upload_admission.py",
        "ingest/http_upload.py",
        "routers/artifacts.py",
        "ingest/safe_zip.py",
        "ingest/xml_security.py",
        "pipeline/idml_parser.py",
    )
)


def preflight(current, app_memory=224):
    errors = violations(current, None, ready_limit_ms=500)
    # Compact disposable lab; the host reserve remains unchanged.
    # Reserve memory for the application, PostgreSQL, Redis and the host.
    if current["memory_available_bytes"] < (512 + app_memory + 96 + 16) * 1024**2:
        errors.append("insufficient_lab_headroom")
    return errors


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--release")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = args.source.resolve(strict=True)
    image_ref = laboratory_image(
        source, "/opt/idml-platform/qualification/v12-storage-v1", args.release
    )
    app_memory = 320 if args.release else 224
    names = [PREFIX + suffix for suffix in ("-pg", "-redis", "-app")]
    existing = command("docker", "ps", "-a", "--format", "{{.Names}}").split()
    if (
        set(names) & set(existing)
        or NETWORK in command("docker", "network", "ls", "--format", "{{.Name}}").split()
    ):
        raise RuntimeError("laboratory names already exist; refusing replacement")
    baseline = containers()
    created = []
    net_created = False
    samples = []
    failures = []
    report = None
    states = {}
    images = {}
    cleanup_errors = []
    started = time.monotonic()

    def check():
        current = sample()
        # Match df's denominator, excluding filesystem-reserved space.
        import shutil

        disk = shutil.disk_usage("/opt/idml-platform")
        current["disk_used_percent"] = 100 * disk.used / (disk.used + disk.free)
        issues = violations(current, samples[-1] if samples else None, ready_limit_ms=500)
        samples.append(current)
        running = containers()
        if {k: running.get(k) for k in baseline} != baseline:
            issues.append("existing_service_changed")
        if time.monotonic() - started > 240:
            issues.append("deadline")
        if issues:
            failures.extend(issues)
            raise RuntimeError("host watchdog stopped laboratory")

    def create(name, image, memory, cpu, options, argv):
        cid = command(
            "docker",
            "create",
            "--name",
            name,
            "--network",
            NETWORK,
            "--label",
            "idml.qualification=V12-queue",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            f"--memory={memory}m",
            f"--memory-swap={memory}m",
            f"--cpus={cpu}",
            "--pids-limit=64",
            "--log-driver=json-file",
            "--log-opt=max-size=1m",
            "--log-opt=max-file=2",
            *options,
            image,
            *argv,
        ).strip()
        created.append(cid)
        command("docker", "start", cid)
        return cid

    try:
        for _ in range(5):
            check()
            time.sleep(2)
        failures.extend(preflight(samples[-1], app_memory))
        if failures:
            raise RuntimeError("not enough headroom")
        for image in (image_ref, "postgres:16-alpine", "redis:7-alpine"):
            images[image] = json.loads(command("docker", "image", "inspect", image))[0]["Id"]
        command(
            "docker",
            "network",
            "create",
            "--internal",
            "--label",
            "idml.qualification=V12-queue",
            NETWORK,
        )
        net_created = True
        pg = create(
            names[0],
            "postgres:16-alpine",
            96,
            0.15,
            [
                "--network-alias=pg",
                "--user=70:70",
                "--tmpfs",
                "/var/lib/postgresql/data:rw,nosuid,nodev,size=128m,uid=70,gid=70",
                "--tmpfs",
                "/var/run/postgresql:rw,nosuid,nodev,size=2m,uid=70,gid=70",
                "--tmpfs",
                "/tmp:rw,nosuid,nodev,size=8m",  # noqa: S108
                "-e",
                "POSTGRES_USER=v12lab",
                "-e",
                "POSTGRES_PASSWORD=v12lab",
                "-e",
                "POSTGRES_DB=v12lab",
            ],
            ["postgres", "-c", "shared_buffers=8MB", "-c", "max_connections=20"],
        )
        for _ in range(30):
            check()
            ready = subprocess.run(  # noqa: S603 - task-created container ID
                ["docker", "exec", pg, "pg_isready", "-U", "v12lab", "-d", "v12lab"],  # noqa: S607 - host Docker CLI
                capture_output=True,
                timeout=5,
                check=False,
            )
            if ready.returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError("laboratory PostgreSQL unavailable")
        create(
            names[1],
            "redis:7-alpine",
            16,
            0.10,
            [
                "--network-alias=redis",
                "--user=10001:10001",
                "--tmpfs",
                "/data:rw,nosuid,nodev,size=8m,uid=10001,gid=10001",
            ],
            [
                "redis-server",
                "--save",
                "",
                "--appendonly",
                "no",
                "--maxmemory",
                "4mb",
                "--maxmemory-policy",
                "noeviction",
            ],
        )
        options = [
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,size=32m,uid=10001,gid=10001",  # noqa: S108
            "-v",
            f"{source}:/qualification:ro",
            "-e",
            "PYTHONPATH=/qualification:/app/src",
            "-e",
            "IDML_ENVIRONMENT=test",
            "-e",
            "IDML_FEATURE_OPENCLAW=false",
            "-e",
            "IDML_FEATURE_AI_SWARM=false",
            "-e",
            "IDML_ARTIFACT_ROOT=/tmp/artifacts",
            "-e",
            "IDML_ARTIFACT_DISK_RESERVE_BYTES=1048576",
            "-e",
            "IDML_UPLOAD_MAX_BYTES=4194304",
            "-e",
            "IDML_UPLOAD_TEMP_RESERVE_BYTES=4194304",
            "-e",
            "IDML_DATABASE_URL=postgresql+psycopg://v12lab:v12lab@pg:5432/v12lab",
            "-e",
            "IDML_REDIS_URL=redis://redis:6379/0",
        ]
        for path in OVERLAYS:
            options += ["-v", f"{source / path}:/app/{path}:ro"]
        app = create(
            names[2],
            image_ref,
            app_memory,
            0.25,
            options,
            ["python", "-m", "ops.lab_phase7_v12_queue"],
        )
        while True:
            check()
            state = json.loads(command("docker", "inspect", app))[0]["State"]
            if not state["Running"]:
                logs = command("docker", "logs", app)
                report = json.loads(logs.strip().splitlines()[-1])
                if state["ExitCode"] != 0 or not report.get("approved"):
                    failures.append("queue_probe_failed")
                break
            time.sleep(2)
    except Exception as exc:
        failures.append(type(exc).__name__)
    finally:
        for cid in reversed(created):
            try:
                row = json.loads(command("docker", "inspect", cid))[0]
                states[row["Name"].lstrip("/")] = {
                    "exit_code": row["State"]["ExitCode"],
                    "oom_killed": row["State"]["OOMKilled"],
                    "running_before_cleanup": row["State"]["Running"],
                }
                command("docker", "rm", "-f", cid)
            except Exception:
                cleanup_errors.append(cid)
        if net_created:
            try:
                command("docker", "network", "rm", NETWORK)
            except Exception:
                cleanup_errors.append(NETWORK)
    unchanged = containers() == baseline
    output = {
        "version": "phase7-v12-real-queue-observation-1.1"
        if args.release
        else "phase7-v12-real-queue-observation-1.0",
        "release": args.release,
        "approved": bool(report and report.get("approved"))
        and not failures
        and not cleanup_errors
        and unchanged,
        "failures": failures,
        "cleanup_errors": cleanup_errors,
        "existing_services_unchanged": unchanged,
        "existing_service_count": len(baseline),
        "container_states": states,
        "samples": samples,
        "probe": report,
        "images": images,
        "source_sha256": {
            str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in source.rglob("*.py")
        },
        "limits": {
            "total_memory_mib": app_memory + 96 + 16,
            "application_memory_mib": app_memory,
            "internal_network": True,
            "published_ports": 0,
        },
        "restricted_content_emitted": False,
        "release_ready": False,
        "v12_complete": False,
    }
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "approved": output["approved"],
                "failures": failures,
                "samples": len(samples),
                "cleanup_errors": cleanup_errors,
            }
        )
    )
    return 0 if output["approved"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
