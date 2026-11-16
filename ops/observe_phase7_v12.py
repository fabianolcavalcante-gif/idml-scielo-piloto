"""Run one resource-limited synthetic container with host-side stop conditions."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

NAME = "idml-v12-benchmark"
IMAGE = "idml-foundation:phase7-7c08-v1"


def laboratory_image(source: Path, historical_source: str, release: str | None) -> str:
    if release is None:
        if source != Path(historical_source):
            raise ValueError("unexpected laboratory source")
        return IMAGE
    stage = Path("/opt/idml-platform/releases") / release
    if stage.parent != Path("/opt/idml-platform/releases") or stage.resolve() != stage:
        raise ValueError("unexpected release directory")
    if source not in {stage / "vh17/source", stage / "regression/source"}:
        raise ValueError("unexpected release laboratory")
    manifest = json.loads((stage / "release-source-manifest.json").read_bytes())
    if manifest["release"] != release:
        raise ValueError("unexpected release identity")
    for name, digest in manifest["files"].items():
        if (
            name.startswith("src/")
            and hashlib.sha256((source / name).read_bytes()).hexdigest() != digest
        ):
            raise ValueError("runtime source differs from deployed release")
    image = json.loads(command("docker", "image", "inspect", f"idml-foundation:{release}"))[0]["Id"]
    if (stage / "deployment.json").exists():
        record = json.loads((stage / "deployment.json").read_bytes())
        if record["release"] != release or record["image_id"] != image:
            raise ValueError("image differs from deployed release")
    else:
        record = json.loads((stage / "qualification.json").read_bytes())
        if record.get("linux_tests") is not True or record.get("postgresql_native") is not True:
            raise ValueError("candidate has not passed isolated qualification")
    return image


def command(*args: str) -> str:
    return subprocess.check_output(args, text=True, timeout=15)  # noqa: S603 - scoped ops commands


def containers() -> dict:
    ids = command("docker", "ps", "-q").split()
    return {
        r["Name"].lstrip("/"): {
            "id": r["Id"],
            "started": r["State"]["StartedAt"],
            "restarts": r["RestartCount"],
            "health": r["State"].get("Health", {}).get("Status"),
        }
        for r in json.loads(command("docker", "inspect", *ids))
        if r["Name"].lstrip("/") != NAME
    }


def sample() -> dict:
    memory = {
        line.split(":")[0]: int(line.split()[1]) * 1024
        for line in Path("/proc/meminfo").read_text().splitlines()
    }
    cpu = [int(value) for value in Path("/proc/stat").read_text().splitlines()[0].split()[1:9]]
    vm = {
        line.split()[0]: int(line.split()[1])
        for line in Path("/proc/vmstat").read_text().splitlines()
    }
    disk = shutil.disk_usage("/opt/idml-platform")
    before = time.perf_counter()
    ready = False
    try:
        with urllib.request.urlopen("http://127.0.0.1:18080/health/ready", timeout=3) as response:
            ready = response.status == 200
    except OSError:
        pass
    return {
        "monotonic": round(time.monotonic(), 3),
        "memory_available_bytes": memory["MemAvailable"],
        "swap_used_bytes": memory["SwapTotal"] - memory["SwapFree"],
        "disk_used_percent": 100 * disk.used / disk.total,
        "disk_free_bytes": disk.free,
        "cpu_total": sum(cpu),
        "cpu_idle": cpu[3],
        "cpu_iowait": cpu[4],
        "page_in_kib": vm["pgpgin"],
        "page_out_kib": vm["pgpgout"],
        "swap_in_pages": vm["pswpin"],
        "swap_out_pages": vm["pswpout"],
        "ready": ready,
        "ready_ms": round((time.perf_counter() - before) * 1000, 3),
    }


def violations(current: dict, previous: dict | None, *, ready_limit_ms: float) -> list[str]:
    errors = []
    if current["memory_available_bytes"] < 512 * 1024 * 1024:
        errors.append("memory_reserve")
    if current["disk_used_percent"] >= 90 or current["disk_free_bytes"] < 5 * 1024**3:
        errors.append("disk_reserve")
    if not current["ready"] or current["ready_ms"] > ready_limit_ms:
        errors.append("readiness_degradation")
    if previous is not None:
        total = current["cpu_total"] - previous["cpu_total"]
        idle = current["cpu_idle"] - previous["cpu_idle"]
        if total <= 0:
            errors.append("invalid_cpu_sample")
        elif 100 * (total - idle) / total > 85:
            errors.append("host_cpu_pressure")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--soak-seconds", type=int, default=300)
    args = parser.parse_args()
    if not 30 <= args.soak_seconds <= 600:
        parser.error("soak must be between 30 and 600 seconds")
    source = args.source.resolve(strict=True)
    if not source.is_relative_to(Path("/opt/idml-platform")):
        parser.error("source outside approved workspace")
    if NAME in command("docker", "ps", "-a", "--format", "{{.Names}}").split():
        raise RuntimeError("benchmark container already exists; refusing to replace it")
    baseline = containers()
    samples = []
    failures = []
    output = None
    final_container_state = None
    created = False
    began = time.monotonic()
    try:
        for _ in range(10):
            current = sample()
            failures = violations(current, samples[-1] if samples else None, ready_limit_ms=500)
            samples.append(current)
            if failures:
                raise RuntimeError("baseline violates reserve")
            time.sleep(2)
        ready_limit = 500
        command(
            "docker",
            "run",
            "-d",
            "--name",
            NAME,
            "--label",
            "idml.qualification=V12",
            "--read-only",
            "--network",
            "none",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--memory=256m",
            "--memory-swap=256m",
            "--cpus=0.25",
            "--pids-limit=64",
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,size=32m",  # noqa: S108 - isolated container tmpfs
            "-v",
            f"{source}:/qualification:ro",
            "-w",
            "/qualification",
            IMAGE,
            "python",
            "ops/benchmark_phase7_v12.py",
            "--repeats",
            "3",
            "--soak-seconds",
            str(args.soak_seconds),
        )
        created = True
        while True:
            current = sample()
            failures = violations(current, samples[-1], ready_limit_ms=ready_limit)
            samples.append(current)
            if failures:
                raise RuntimeError("load violates reserve")
            if len(samples) % 5 == 0 and containers() != baseline:
                failures = ["existing_service_changed"]
                raise RuntimeError("service health or identity changed")
            state = json.loads(command("docker", "inspect", NAME))[0]["State"]
            if not state["Running"]:
                final_container_state = {key: state[key] for key in ("ExitCode", "OOMKilled")}
                try:
                    output = json.loads(command("docker", "logs", NAME))
                except (ValueError, subprocess.SubprocessError):
                    failures = ["invalid_benchmark_output"]
                    raise RuntimeError("no structured benchmark report") from None
                if state["OOMKilled"] or state["ExitCode"] != 0:
                    failures = ["benchmark_container_failed"]
                    raise RuntimeError("benchmark unsuccessful")
                if not output.get("approved"):
                    raise RuntimeError("benchmark gate failed")
                break
            if time.monotonic() - began > args.soak_seconds + 180:
                failures = ["wall_time_budget"]
                raise RuntimeError("benchmark exceeded wall time")
            time.sleep(2)
        if containers() != baseline:
            failures = ["existing_service_changed"]
    except Exception as exc:
        failures = failures or [type(exc).__name__]
    finally:
        if created:
            # Exact task-owned name, created by this invocation only.
            command("docker", "rm", "-f", NAME)
    report = {
        "version": "phase7-v12-vps-observation-1.0",
        "approved": not failures and output is not None,
        "failures": failures,
        "image": IMAGE,
        "baseline_samples": min(10, len(samples)),
        "samples": samples,
        "benchmark": output,
        "container_exit": final_container_state,
        "existing_services": len(baseline),
        "existing_services_unchanged": containers() == baseline,
        "container_removed": created,
        "limits": {
            "memory_mib": 256,
            "cpus": 0.25,
            "network": "none",
            "read_only": True,
            "host_memory_reserve_mib": 512,
            "host_disk_max_percent": 90,
            "readiness_limit_ms": 500,
        },
        "restricted_content_emitted": False,
        "release_ready": False,
    }
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps({"approved": report["approved"], "failures": failures, "samples": len(samples)})
    )
    return 0 if report["approved"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
