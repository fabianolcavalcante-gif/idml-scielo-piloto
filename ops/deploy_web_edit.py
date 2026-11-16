"""Build and qualify the web evaluation RC without exposing a provider to ordinary users."""

import argparse
import json
import os
from pathlib import Path

from ops import deploy_reference_edit as prior
from ops import deploy_vh09 as d
from ops import deploy_vh1_structural as rollout
from ops import run_vps_edit_cycle as cycle

NAME = "vh11-web-20261103-v1"
LAB = Path("/var/lib/idml-vh1-qualification") / NAME
API = "idml-web-rc-20261103"
INPUT = Path("/var/lib/idml-vh1-qualification/vh10-reference-20261103-v1")


def configure():
    prior.configure()
    d.NAME = rollout.NAME = NAME
    rollout.PREVIOUS = "idml-foundation:" + prior.NAME
    d.STAGE = d.ROOT / "releases" / NAME
    d.IMAGE = "idml-foundation:" + NAME
    d.TEST_IMAGE = d.IMAGE + "-qualification"
    d.EXTRA_TESTS += ("tests/test_web_edit.py",)
    cycle.STAGE = d.STAGE
    cycle.ROOT = LAB
    cycle.DATA = LAB / "private"
    cycle.IMAGE = d.TEST_IMAGE


def seed():
    LAB.mkdir(mode=0o700)
    (LAB / "runner-ops").symlink_to(d.STAGE / "ops", target_is_directory=True)
    cycle.DATA.mkdir(mode=0o700)
    os.chown(cycle.DATA, 10001, 10001)
    cycle.execute(
        [
            *cycle.runner(),
            "-v",
            "/run/idml-clamav-vh1:/run/idml-clamav-vh1:ro",
            "-v",
            f"{INPUT}/inputs:/inputs:ro",
            "-v",
            f"{INPUT}/reference:/reference:ro",
            d.TEST_IMAGE,
            "python",
            "-m",
            "ops.qualify_reference_edit",
        ],
        "web-prepare.log",
    )


def portal():
    args = cycle.runner()
    # The disposable API needs HTTP via loopback only and never receives the gateway token.
    args[args.index("--network=none")] = "--network=bridge"
    cycle.execute(
        [
            *args,
            "-d",
            "--name",
            API,
            "-p",
            "127.0.0.1:18127:8080",
            "--tmpfs",
            "/case/decisions:ro,size=4k",
            "-e",
            "IDML_ENVIRONMENT=test",
            "-e",
            "IDML_ARTIFACT_ROOT=/case/artifacts",
            "-e",
            "IDML_JOURNAL_PROFILE_PATH=/app/profiles/esa-aop-1.1.json",
            d.TEST_IMAGE,
            "python",
            "-m",
            "uvicorn",
            "idml_foundation.main:app",
            "--host",
            "0.0.0.0",  # noqa: S104 - container port published only on host loopback
            "--port",
            "8080",
            "--no-access-log",
        ],
        "web-portal.log",
    )


def qualify_cycle():
    import time
    from contextlib import ExitStack

    with ExitStack() as stack:
        cycle.validators(stack)
        try:
            cycle.execute(["sh", str(d.ROOT / "ops/openclaw-provider-stage.sh")], "web-stage.log")
            shell = 'set -eu; set -a; . /opt/idml-platform/.env; set +a; exec "$@"'
            cycle.execute(
                [
                    "sh",
                    "-c",
                    shell,
                    "lab",
                    *cycle.runner(live=True),
                    "-d",
                    "--name",
                    cycle.NAME,
                    "-v",
                    f"{cycle.SOCKETS}:/socket:ro",
                    "-e",
                    "IDML_OPENCLAW_GATEWAY_TOKEN",
                    d.TEST_IMAGE,
                    "sleep",
                    "1800",
                ],
                "web-worker.log",
            )
            stack.callback(
                lambda: cycle.execute(["docker", "rm", "-f", cycle.NAME], "web-remove.log")
            )
            cycle.execute(
                ["docker", "exec", cycle.NAME, "python", "-m", "ops.qualify_web_portal", "process"],
                "web-process.log",
            )
        finally:
            cycle.execute(
                ["sh", str(d.ROOT / "ops/openclaw-provider-disable.sh")],
                "web-disable.log",
                env=os.environ | {"IDML_RESET_OPENCLAW_STATE": "true"},
            )
        # Let the disabled gateway finish starting before opening more native validators.
        for _ in range(36):
            if (
                int(
                    next(
                        line.split()[1]
                        for line in Path("/proc/meminfo").read_text().splitlines()
                        if line.startswith("MemAvailable:")
                    )
                )
                >= 1024 * 1024
            ):
                break
            time.sleep(5)
        cycle.execute(
            ["docker", "exec", cycle.NAME, "python", "-m", "ops.qualify_web_portal", "restore"],
            "web-restore.log",
        )
    assert (
        json.loads((cycle.DATA / "web-recovery.json").read_bytes())["state"]
        == "revalidated-working-draft"
    )


def activate():
    assert json.loads((LAB / "browser-receipt.json").read_bytes())["specialist_checked"]
    assert json.loads((cycle.DATA / "web-cycle.json").read_bytes())["state"] == "applied"
    assert (
        json.loads((cycle.DATA / "web-recovery.json").read_bytes())["state"]
        == "revalidated-working-draft"
    )
    if not (d.STAGE / "preactivation.json").exists():
        rollout.refresh_backup()
    rollout.activate()


if __name__ == "__main__":
    os.umask(0o077)
    configure()
    actions = dict(
        prepare=d.prepare,
        build=d.build,
        qualify=rollout.qualify,
        seed=seed,
        portal=portal,
        cycle=qualify_cycle,
        activate=activate,
    )
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=actions)
    actions[parser.parse_args().action]()
