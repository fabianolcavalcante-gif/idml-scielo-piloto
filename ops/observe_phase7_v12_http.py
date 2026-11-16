"""Watch one isolated multipart reception container; no production service changes."""

import argparse
import hashlib
import json
import shutil
import time
from pathlib import Path

from ops.observe_phase7_v12 import command, containers, laboratory_image, sample, violations

NAME = "idml-v12-http"


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
    if NAME in command("docker", "ps", "-a", "--format", "{{.Names}}").split():
        raise RuntimeError("laboratory name exists; refusing replacement")
    baseline = containers()
    cid = None
    samples, failures, cleanup_errors = [], [], []
    result = state = None
    began = time.monotonic()
    image_id = json.loads(command("docker", "image", "inspect", image_ref))[0]["Id"]

    def check():
        if samples:
            time.sleep(max(0, 1 - (time.monotonic() - samples[-1]["monotonic"])))
        current = sample()
        disk = shutil.disk_usage("/opt/idml-platform")
        current["disk_used_percent"] = 100 * disk.used / (disk.used + disk.free)
        errors = violations(current, samples[-1] if samples else None, ready_limit_ms=500)
        samples.append(current)
        running = containers()
        if {k: running.get(k) for k in baseline} != baseline:
            errors.append("existing_service_changed")
        if time.monotonic() - began > 240:
            errors.append("deadline")
        if errors:
            failures.extend(errors)
            raise RuntimeError("host watchdog stopped experiment")

    try:
        for _ in range(5):
            check()
        if samples[-1]["memory_available_bytes"] < 768 * 1024**2:
            raise RuntimeError("insufficient_lab_headroom")
        overlays = (
            "src/idml_foundation/ingest/http_upload.py",
            "src/idml_foundation/ingest/upload_admission.py",
            "src/idml_foundation/settings.py",
        )
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
            "--pids-limit=64",
            "--log-driver=json-file",
            "--log-opt=max-size=1m",
            "--log-opt=max-file=2",
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,size=128m,uid=10001,gid=10001",  # noqa: S108
            "-v",
            f"{source}:/qualification:ro",
            *(
                arg
                for overlay in overlays
                for arg in ("-v", f"{source / overlay}:/app/{overlay}:ro")
            ),
            "-e",
            "PYTHONPATH=/qualification:/app/src",
            "-e",
            "IDML_ENVIRONMENT=test",
            "-e",
            "IDML_ARTIFACT_ROOT=/tmp/artifacts",
            "-e",
            "IDML_UPLOAD_TEMP_RESERVE_BYTES=8388608",
            "-e",
            "IDML_UPLOAD_IDLE_TIMEOUT_SECONDS=2",
            image_ref,
            "python",
            "-m",
            "ops.probe_phase7_v12_http",
        ).strip()
        command("docker", "start", cid)
        while True:
            check()
            state = json.loads(command("docker", "inspect", cid))[0]["State"]
            if not state["Running"]:
                result = json.loads(command("docker", "logs", cid).strip().splitlines()[-1])
                if state["OOMKilled"] or state["ExitCode"] != 0 or not result.get("approved"):
                    failures.append("probe_failed")
                break
    except Exception as exc:
        failures.append(type(exc).__name__)
    finally:
        if cid is not None:
            try:
                command("docker", "rm", "-f", cid)
            except Exception:
                cleanup_errors.append(cid)
    unchanged = containers() == baseline
    report = {
        "version": "phase7-v12-http-observation-1.0",
        "approved": bool(result and result.get("approved"))
        and not failures
        and not cleanup_errors
        and unchanged,
        "failures": failures,
        "cleanup_errors": cleanup_errors,
        "probe": result,
        "samples": samples,
        "image_id": image_id,
        "existing_service_count": len(baseline),
        "existing_services_unchanged": unchanged,
        "container_exit": {k: state[k] for k in ("ExitCode", "OOMKilled")} if state else None,
        "source_sha256": {
            str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in source.rglob("*.py")
        },
        "limits": {"memory_mib": 256, "cpus": 0.25, "tmpfs_mib": 128, "network": "none"},
        "production_capacity_qualified": False,
        "release_ready": False,
        "restricted_content_emitted": False,
    }
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {"approved": report["approved"], "failures": failures, "cleanup_errors": cleanup_errors}
        )
    )
    return 0 if report["approved"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
