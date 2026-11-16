"""Manage the persistent OpenClaw route used by authorized portal corrections on the VPS."""

import argparse
import os
import subprocess
import tempfile
import time
from pathlib import Path

ROOT = Path("/opt/idml-platform")
ENV = ROOT / ".env"
BASE = ["docker", "compose", "--env-file", str(ENV), "-f", "deploy/docker-compose.dev.yml"]
APP = [*BASE, "-f", "deploy/docker-compose.validators.yml"]
GATEWAY = "idml-development-openclaw-idml-1"
WORKER = "idml-development-worker-1"
PROXY = "idml-development-openclaw-egress-proxy-1"
FLAG = "IDML_FEATURE_WEB_EDIT_PROVIDER"


def run(*args: str) -> str:
    result = subprocess.run(args, cwd=ROOT, capture_output=True, check=False, timeout=360)  # noqa: S603
    if result.returncode:
        raise RuntimeError(f"pilot operation failed: {args[0]} {args[1]}")
    return result.stdout.decode().strip()


def set_flag(enabled: bool) -> None:
    lines = [s for s in ENV.read_text().splitlines() if not s.startswith(FLAG + "=")]
    with tempfile.NamedTemporaryFile(dir=ROOT, mode="w", delete=False) as tmp:
        tmp.write("\n".join([*lines, FLAG + "=" + str(enabled).lower(), ""]))
    os.chmod(tmp.name, 0o600)
    os.replace(tmp.name, ENV)


def health(container: str) -> str:
    return run("docker", "inspect", "-f", "{{.State.Health.Status}}", container)


def worker_ready() -> None:
    for _ in range(60):
        if health(WORKER) == "healthy":
            return
        time.sleep(2)
    raise RuntimeError("worker health timeout")


def enabled() -> bool:
    return (
        run("docker", "exec", WORKER, "printenv", FLAG) == "true"
        and bool(run("docker", "ps", "--filter", "name=" + PROXY, "--format", "{{.Names}}"))
        and health(PROXY) == health(GATEWAY) == "healthy"
    )


def disable() -> None:
    set_flag(False)
    run(*APP, "up", "-d", "--no-deps", "worker")
    run(*BASE, "up", "-d", "--no-deps", "--force-recreate", "openclaw-idml")
    if run("docker", "ps", "-a", "--filter", "name=" + PROXY, "--format", "{{.Names}}"):
        run("docker", "rm", "-f", PROXY)
    worker_ready()


def enable() -> None:
    if enabled():
        return
    try:
        run("sh", "ops/openclaw-provider-stage.sh", "--web-pilot")
        set_flag(True)
        run(*APP, "up", "-d", "--no-deps", "worker")
        worker_ready()
        if not enabled():
            raise RuntimeError("portal provider unavailable")
    except Exception:
        disable()
        raise


if __name__ == "__main__":
    import fcntl

    p = argparse.ArgumentParser()
    p.add_argument("action", choices=["enable", "disable", "status"])
    action = p.parse_args().action
    with (ROOT / "releases" / ".web-provider.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if action == "enable":
            enable()
        elif action == "disable":
            disable()
        print("portal provider active" if enabled() else "portal provider inactive")
