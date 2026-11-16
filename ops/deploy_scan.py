"""Deploy verified upload scanning and figure binding receipts on the development VPS."""

import argparse
import json
import os
from pathlib import Path

from ops import deploy_vh09 as d
from ops import deploy_vh1_structural as rollout
from ops import deploy_worker_evidence as previous

NAME = "vh10-scan-20261031-v1"
LAB = Path("/var/lib/idml-vh1-qualification/scan-lab-20261031")


def configure():
    previous.configure()
    d.NAME = rollout.NAME = NAME
    rollout.PREVIOUS = "idml-foundation:" + previous.NAME
    d.STAGE = d.ROOT / "releases" / NAME
    d.IMAGE = "idml-foundation:" + NAME
    d.TEST_IMAGE = d.IMAGE + "-qualification"
    d.EXTRA_TESTS += tuple(
        "tests/test_" + n + ".py"
        for n in (
            "artifact_rescan",
            "scanner_and_health",
            "artifacts",
            "phase7_v12_storage_budget",
        )
    )


def native():
    log = d.run(
        "docker",
        "run",
        "--rm",
        "--read-only",
        "--network=none",
        "--user=10001:10001",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--memory=480m",
        "--cpus=0.6",
        "--pids-limit=96",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,size=512m,mode=1777",  # noqa: S108
        "-v",
        f"{LAB}/inputs:/inputs:ro",
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
        "ops.qualify_scan_inputs",
        log="native-scan.log",
        timeout=1500,
    )
    result = json.loads(log.splitlines()[-1])
    assert result["eicar_rejected"] and sorted(c["figures"] for c in result["cases"]) == [5, 7]
    assert all(c["offline_valid"] for c in result["cases"])
    d.write("native-scan.json", result)


def activate():
    assert json.loads((d.STAGE / "native-scan.json").read_bytes())["historical_rescan_audited"]
    relative = Path("deploy/docker-compose.validators.yml")
    path = d.ROOT / relative
    old = path.read_bytes()
    assert old == (d.ROOT / "releases" / previous.NAME / relative).read_bytes()
    assert d.run("systemctl", "is-active", "idml-clamav-vh1.socket") == "active"
    path.write_bytes((d.STAGE / relative).read_bytes())
    try:
        rollout.activate()
    except Exception:
        path.write_bytes(old)
        d.run(
            *d.COMPOSE,
            "up",
            "-d",
            "--no-deps",
            "api",
            "worker",
            environment=os.environ | {"IDML_IMAGE_TAG": previous.NAME},
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
