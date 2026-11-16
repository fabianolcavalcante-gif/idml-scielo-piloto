"""Qualify and activate exact-revision edit preflight on the existing VPS."""

import argparse
import json
import os
from pathlib import Path

from ops import deploy_scan
from ops import deploy_vh09 as d
from ops import deploy_vh1_structural as rollout

NAME = "vh10-edit-20261101-v2"
DECISIONS = Path("/var/lib/idml-vh1-edit-decisions")


def configure():
    deploy_scan.configure()
    d.NAME = rollout.NAME = NAME
    rollout.PREVIOUS = "idml-foundation:" + deploy_scan.NAME
    d.STAGE = d.ROOT / "releases" / NAME
    d.IMAGE = "idml-foundation:" + NAME
    d.TEST_IMAGE = d.IMAGE + "-qualification"
    d.EXTRA_TESTS += ("tests/test_edit_preflight.py",)


def native():
    inputs = deploy_scan.LAB / "inputs"
    out = d.run(
        "docker",
        "run",
        "--rm",
        "--network=none",
        "--read-only",
        "--user=10001:10001",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--cpus=0.6",
        "--pids-limit=96",
        "--memory=480m",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,size=512m,mode=1777",  # noqa: S108
        "-v",
        f"{inputs}:/inputs:ro",
        "-v",
        f"{d.STAGE}:/qualification:ro",
        "-v",
        "/run/idml-clamav-vh1:/run/idml-clamav-vh1:ro",
        "-w",
        "/qualification",
        "-e",
        "PYTHONPATH=/app/src:/qualification",
        d.TEST_IMAGE,
        "python",
        "-m",
        "ops.qualify_edit_preflight",
        "/inputs/e86/ESA_2024086_AOP.idml",
        "/inputs/e135/ESA_2024135_AOP.idml",
        log="edit-native.log",
    )
    result = json.loads(out.splitlines()[-1])
    assert [c["state"] for c in result["cases"]] == ["abstained", "abstained", "staged"]
    d.write("edit-native.json", result)


def activate():
    result = json.loads((d.STAGE / "edit-native.json").read_bytes())
    assert result["revocation_enforced"] and result["active_head_preserved"]
    for directory in [DECISIONS, DECISIONS / "autocorrection-authorizations"]:
        directory.mkdir(mode=0o750, exist_ok=True)
        assert not directory.is_symlink() and directory.stat().st_uid == 0
        os.chown(directory, 0, 10001)
        directory.chmod(0o750)
    relative = Path("deploy/docker-compose.validators.yml")
    active = d.ROOT / relative
    previous = active.read_bytes()
    assert previous == (d.ROOT / "releases" / deploy_scan.NAME / relative).read_bytes()
    active.write_bytes((d.STAGE / relative).read_bytes())
    try:
        rollout.activate()
    except Exception:
        active.write_bytes(previous)
        d.run(
            *d.COMPOSE,
            "up",
            "-d",
            "--no-deps",
            "api",
            "worker",
            environment=os.environ | {"IDML_IMAGE_TAG": deploy_scan.NAME},
        )
        raise


if __name__ == "__main__":
    os.umask(0o077)
    configure()
    actions = dict(
        prepare=d.prepare, build=d.build, qualify=rollout.qualify, native=native, activate=activate
    )
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=actions)
    actions[parser.parse_args().action]()
