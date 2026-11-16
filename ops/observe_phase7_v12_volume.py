"""Run volume probes sequentially with fixed resource caps and scoped scratch cleanup."""

import argparse
import hashlib
import json
import os
import shutil
import tempfile
import time
from pathlib import Path

from ops.observe_phase7_v12 import command, containers, laboratory_image, sample, violations

NAME = "idml-v12-volume"
CASES = ("stored_16m", "stored_100m", "expanded_500m", "text_14m", "files_10000", "disk_reserve")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--release")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = args.source.resolve(strict=True)
    image_ref = laboratory_image(
        source, "/opt/idml-platform/qualification/v12-volume-v1", args.release
    )
    if NAME in command("docker", "ps", "-a", "--format", "{{.Names}}").split():
        raise RuntimeError("existing lab; refusing replacement")
    baseline = containers()
    image_id = json.loads(command("docker", "image", "inspect", image_ref))[0]["Id"]
    samples, failures, rows, cleanup_errors = [], [], [], []
    cid = scratch = None
    began = time.monotonic()
    runs = source / "runs"
    runs.mkdir(exist_ok=True)
    if runs.is_symlink():
        raise RuntimeError("unsafe scratch parent")

    def check():
        if samples:
            time.sleep(max(0, 1 - (time.monotonic() - samples[-1]["monotonic"])))
        current = sample()
        disk = shutil.disk_usage(source)
        current["disk_used_percent"] = 100 * disk.used / (disk.used + disk.free)
        errors = violations(current, samples[-1] if samples else None, ready_limit_ms=500)
        samples.append(current)
        running = containers()
        if any(running.get(k) != v for k, v in baseline.items()):
            errors.append("existing_service_changed")
        if time.monotonic() - began > 600:
            errors.append("deadline")
        if errors:
            failures.extend(errors)
            raise RuntimeError("watchdog stopped volume laboratory")

    def cleanup():
        nonlocal cid, scratch
        if cid is not None:
            try:
                command("docker", "rm", "-f", cid)
                cid = None
            except Exception:
                cleanup_errors.append("container")
        if scratch is not None and cid is None:
            # Only the exact mkdtemp child created by this run can be removed.
            if scratch.is_symlink() or scratch.resolve().parent != runs.resolve():
                raise RuntimeError("unsafe scratch cleanup")
            try:
                shutil.rmtree(scratch)
                scratch = None
            except OSError:
                cleanup_errors.append("scratch")

    try:
        for _ in range(5):
            check()
        for case in CASES:
            check()
            if samples[-1]["memory_available_bytes"] < 768 * 1024**2:
                raise RuntimeError("insufficient_lab_headroom")
            if samples[-1]["disk_free_bytes"] < 5 * 1024**3 + 256 * 1024**2:
                raise RuntimeError("insufficient_scratch_headroom")
            scratch = Path(tempfile.mkdtemp(prefix=f"{case}-", dir=runs))
            os.chown(scratch, 10001, 10001)
            cid = command(
                "docker",
                "create",
                "--name",
                NAME,
                "--network=none",
                "--read-only",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges",
                "--memory=256m",
                "--memory-swap=256m",
                "--cpus=0.25",
                "--pids-limit=32",
                "--log-driver=json-file",
                "--log-opt=max-size=1m",
                "--log-opt=max-file=2",
                "--tmpfs",
                "/tmp:rw,nosuid,nodev,size=64m,uid=10001,gid=10001",  # noqa: S108
                "-v",
                f"{source}:/qualification:ro",
                "-v",
                f"{source / 'src/idml_foundation'}:/app/src/idml_foundation:ro",
                "-v",
                f"{source / 'profiles'}:/app/profiles:ro",
                "-v",
                f"{source / 'schemas'}:/app/schemas:ro",
                "-v",
                f"{scratch}:/work:rw",
                "-e",
                "PYTHONPATH=/qualification:/app/src",
                "-e",
                "IDML_ENVIRONMENT=test",
                image_ref,
                "python",
                "-m",
                "ops.probe_phase7_v12_volume",
                "--case",
                case,
            ).strip()
            command("docker", "start", cid)
            while True:
                check()
                state = json.loads(command("docker", "inspect", cid))[0]["State"]
                if not state["Running"]:
                    break
            logs = command("docker", "logs", cid).strip().splitlines()
            try:
                probe = json.loads(logs[-1])
            except (ValueError, IndexError):
                probe = None
            allocated = sum(p.stat().st_blocks * 512 for p in scratch.rglob("*") if p.is_file())
            rows.append(
                {
                    "case": case,
                    "exit_code": state["ExitCode"],
                    "oom_killed": state["OOMKilled"],
                    "scratch_allocated_bytes": allocated,
                    "probe": probe,
                }
            )
            print(
                json.dumps(
                    {"case": case, "exit_code": state["ExitCode"], "oom": state["OOMKilled"]}
                ),
                flush=True,
            )
            cleanup()
            if cleanup_errors:
                raise RuntimeError("cleanup failed")
    except Exception as exc:
        failures.append(type(exc).__name__)
    finally:
        cleanup()
    unchanged = containers() == baseline
    report = {
        "version": "phase7-v12-volume-observation-1.0",
        "approved": len(rows) == len(CASES)
        and all(
            r["exit_code"] == 0
            and not r["oom_killed"]
            and r["probe"]
            and r["probe"].get("approved")
            for r in rows
        )
        and not failures
        and not cleanup_errors
        and unchanged,
        "cases": rows,
        "samples": samples,
        "failures": failures,
        "cleanup_errors": cleanup_errors,
        "existing_services_unchanged": unchanged,
        "existing_service_count": len(baseline),
        "image_id": image_id,
        "source_sha256": {
            str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in source.rglob("*")
            if p.is_file() and p.suffix in {".py", ".json"}
        },
        "limits": {"memory_mib": 256, "cpus": 0.25, "tmpfs_mib": 64, "network": "none"},
        "restricted_content_emitted": False,
        "production_capacity_qualified": False,
        "release_ready": False,
    }
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {"approved": report["approved"], "failures": failures, "cleanup_errors": cleanup_errors}
        ),
        flush=True,
    )
    return 0 if report["approved"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
