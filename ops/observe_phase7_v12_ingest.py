"""Bounded sequential ingestion probes with host watchdog and exact-ID cleanup."""

import argparse
import hashlib
import json
import shutil
import time
from pathlib import Path

from ops.observe_phase7_v12 import command, containers, laboratory_image, sample, violations

NAME = "idml-v12-ingest"
OVERLAYS = (
    "ingest/safe_zip.py",
    "services/artifacts.py",
    "ingest/xml_security.py",
    "pipeline/idml_parser.py",
    "services/storage_budget.py",
    "ingest/upload_admission.py",
    "settings.py",
)
CASES = (
    "nodes_100k",
    "nodes_500k",
    "nodes_2m",
    "xml_oversize",
    "mimetype_oversize",
    "expanded_oversize",
    "xml_total_near_limit",
    "xml_total_over_limit",
)


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
        raise RuntimeError("existing laboratory container; refusing replacement")
    baseline = containers()
    rows, samples, failures = [], [], []
    cid = None
    cleanup_errors = []
    began = time.monotonic()

    def check():
        if samples:
            # CPU deltas need a complete interval, including between short probes.
            time.sleep(max(0, 1 - (time.monotonic() - samples[-1]["monotonic"])))
        current = sample()
        disk = shutil.disk_usage("/opt/idml-platform")
        current["disk_used_percent"] = 100 * disk.used / (disk.used + disk.free)
        errors = violations(current, samples[-1] if samples else None, ready_limit_ms=500)
        samples.append(current)
        running = containers()
        if {key: running.get(key) for key in baseline} != baseline:
            errors.append("existing_service_changed")
        if time.monotonic() - began > 240:
            errors.append("deadline")
        if errors:
            failures.extend(errors)
            raise RuntimeError("watchdog stopped ingestion probe")

    try:
        for _ in range(5):
            check()
            time.sleep(2)
        if samples[-1]["memory_available_bytes"] < 768 * 1024**2:
            raise RuntimeError("insufficient_lab_headroom")
        for case in CASES:
            check()
            mounts = []
            for relative in OVERLAYS:
                mounts += [
                    "-v",
                    f"{source / 'src/idml_foundation' / relative}:"
                    f"/app/src/idml_foundation/{relative}:ro",
                ]
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
                "/tmp:rw,nosuid,nodev,size=8m",  # noqa: S108
                "-v",
                f"{source}:/qualification:ro",
                *mounts,
                "-e",
                "PYTHONPATH=/qualification:/app/src",
                image_ref,
                "python",
                "-m",
                "ops.probe_phase7_v12_ingest",
                "--case",
                case,
            ).strip()
            command("docker", "start", cid)
            while True:
                check()
                state = json.loads(command("docker", "inspect", cid))[0]["State"]
                if not state["Running"]:
                    break
                time.sleep(1)
            raw = command("docker", "logs", cid)
            try:
                result = json.loads(raw)
            except ValueError:
                result = None
            rows.append(
                {
                    "case": case,
                    "exit_code": state["ExitCode"],
                    "oom_killed": state["OOMKilled"],
                    "probe": result,
                }
            )
            command("docker", "rm", cid)
            cid = None
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
        "version": "phase7-v12-ingest-observation-1.0",
        "cases": rows,
        "observation_complete": len(rows) == len(CASES) and not failures,
        "all_probes_survived": bool(rows)
        and all(r["exit_code"] == 0 and not r["oom_killed"] for r in rows),
        "failures": failures,
        "samples": samples,
        "cleanup_errors": cleanup_errors,
        "existing_services_unchanged": unchanged,
        "existing_service_count": len(baseline),
        "limits": {"memory_mib": 256, "cpus": 0.25, "network": "none", "read_only": True},
        "source_sha256": {
            str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in source.rglob("*.py")
        },
        "provider_calls": 0,
        "restricted_content_emitted": False,
        "release_ready": False,
    }
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                k: report[k]
                for k in (
                    "observation_complete",
                    "all_probes_survived",
                    "failures",
                    "cleanup_errors",
                )
            }
        )
    )
    return 0 if report["observation_complete"] and unchanged and not cleanup_errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
