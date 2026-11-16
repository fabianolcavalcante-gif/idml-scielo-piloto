"""Qualify ingestion of exact field evidence and rebuilt-package validation on the VPS."""

import argparse
import json
import os
from pathlib import Path

from ops import deploy_article_sources as prior
from ops import deploy_vh09 as d
from ops import deploy_vh1_structural as rollout

NAME = "vh10-evidence-20261031-v1"
CASES = ("ESA_2024086_AOP.idml", "ESA_2024135_AOP.idml")
INPUTS = Path("/var/lib/idml-vh1-qualification") / NAME


def configure():
    prior.configure()
    d.NAME = rollout.NAME = NAME
    rollout.PREVIOUS = "idml-foundation:" + prior.NAME
    d.STAGE = d.ROOT / "releases" / NAME
    d.IMAGE = "idml-foundation:" + NAME
    d.TEST_IMAGE = d.IMAGE + "-qualification"
    d.EXTRA_TESTS += ("tests/test_worker_field_evidence.py",)


def qualify():
    rollout.qualify()
    result = json.loads(
        d.run(
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--memory=512m",
            "--cpus=0.5",
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,size=512m,mode=1777",  # noqa: S108
            "-v",
            f"{INPUTS}:/inputs:ro",
            "-v",
            f"{d.STAGE}:/qualification:ro",
            "-e",
            "PYTHONPATH=/app/src:/qualification",
            "-w",
            "/qualification",
            d.TEST_IMAGE,
            "python",
            "-m",
            "ops.qualify_idml_field_evidence",
            *["/inputs/" + name for name in CASES],
            log="real-inputs.log",
        )
    )
    baseline = json.loads((d.STAGE / "local-inputs.json").read_bytes())
    assert len(result) == 2 and result == baseline
    d.write("real-inputs.json", result)
    print("Both original IDMLs reproduced the local XML and evidence catalog", flush=True)


def activate():
    assert len(json.loads((d.STAGE / "real-inputs.json").read_bytes())) == 2
    assert (d.ROOT / "deploy/docker-compose.validators.yml").read_bytes() == (
        d.STAGE / "deploy/docker-compose.validators.yml"
    ).read_bytes()
    for kind in ("modern", "xpm"):
        assert d.run("systemctl", "is-active", f"idml-validation-{kind}-vh1.service") == "active"
    rollout.activate()  # Same schema. Verify both runtimes and exercise rollback.


if __name__ == "__main__":
    os.umask(0o077)
    configure()
    actions = dict(prepare=d.prepare, build=d.build, qualify=qualify, activate=activate)
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=actions)
    actions[parser.parse_args().action]()
