"""Bounded isolated negative control; never restarts existing services."""

import json
import subprocess
from pathlib import Path
from uuid import uuid4

from observe_validator_socket import snapshot
from validator_broker import command, reserve

STAGE = Path(__file__).resolve().parent
IMAGE = "sha256:3d3f136c650f4b83f9836b77a378b4fd3304fe30c9c2effa0aa1a06dd1f4de07"


def main():
    reserve(STAGE, starting=True)
    baseline = snapshot()
    name = "idml-pdf-negative-" + uuid4().hex
    try:
        process = subprocess.run(  # noqa: S603 - fixed constrained qualification command
            [  # noqa: S607 - Docker from administrator-controlled PATH
                "docker",
                "run",
                "--rm",
                "--name",
                name,
                "--pull=never",
                "--network=none",
                "--read-only",
                "--user=10001:10001",
                "--memory=192m",
                "--memory-swap=192m",
                "--cpus=0.25",
                "--pids-limit=64",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges",
                "--log-driver=none",
                "--tmpfs=/tmp:rw,noexec,nosuid,size=64m",
                "-e",
                "PYTHONPATH=/validator",
                "-v",
                f"{STAGE / 'candidate.zip'}:/input/candidate.zip:ro",
                "-v",
                f"{STAGE / 'probe_h1_missing_pdf.py'}:/probe.py:ro",
                "--entrypoint=python",
                IMAGE,
                "/probe.py",
                "/input/candidate.zip",
            ],
            capture_output=True,
            timeout=600,
            check=False,
        )
        result = json.loads(process.stdout)
        result["exit_code"] = process.returncode
    finally:
        command("docker", "rm", "-f", name)
    result["existing_services_unchanged"] = baseline == snapshot()
    result["image_id"] = IMAGE
    print(json.dumps(result))
    return (
        0
        if result["exit_code"] == 0
        and result["negative_control_passed"]
        and result["existing_services_unchanged"]
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
