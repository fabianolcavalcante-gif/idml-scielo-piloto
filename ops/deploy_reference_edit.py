"""Qualify the reference-bound edit and deploy only after both native validations pass."""

import argparse
import json
import os
from pathlib import Path

from ops import (
    deploy_edit_preflight as prior,
)
from ops import (
    deploy_vh09 as d,
)
from ops import (
    deploy_vh1_structural as rollout,
)
from ops import (
    run_vps_edit_cycle as cycle,
)

NAME = "vh10-reference-20261103-v2"
LAB = Path("/var/lib/idml-vh1-qualification") / NAME


def configure():
    prior.configure()
    d.NAME = rollout.NAME = NAME
    rollout.PREVIOUS = "idml-foundation:" + prior.NAME
    d.STAGE = d.ROOT / "releases" / NAME
    d.IMAGE = "idml-foundation:" + NAME
    d.TEST_IMAGE = d.IMAGE + "-qualification"
    d.EXTRA_TESTS += (
        "tests/test_affiliation_hierarchy.py",
        "tests/test_reference_edit_rules.py",
        "tests/test_edit_cycle_lab.py",
    )
    cycle.STAGE = d.STAGE
    cycle.ROOT = LAB
    cycle.DATA = LAB / "private"
    cycle.IMAGE = d.TEST_IMAGE


def native():
    cycle.main(reference=True)
    collect_recovery()


def collect_recovery():
    report = json.loads((LAB / "validate-result.json").read_bytes())
    assert (
        report["applied"]
        and report["offline_valid"]
        and report["restore_state"] == "blocked"
        and all(r["counts"]["critical"] > 0 for r in report["restore_modern"])
    )
    assert all(
        r["status"] == "completed"
        for r in [
            *report["formal_runs"],
            *report["restore_modern"],
            report["xpm"],
            report["restore_xpm"],
        ]
    )
    # The incomplete state is a negative control. Recover the last known valid
    # revision separately, with fresh formal reports and no new provider calls.
    folder = LAB / "recovery"
    folder.mkdir(mode=0o700)
    cycle.ROOT = folder
    (folder / "runner-ops").symlink_to(d.STAGE / "ops", target_is_directory=True)
    cycle.validate_saved(["recover"])
    recovery = json.loads((folder / "recover-result.json").read_bytes())
    assert (
        recovery["state"] == "revalidated-working-draft"
        and recovery["package_sha256"] == report["package_sha256"]
    )
    assert all(r["status"] == "completed" for r in [*recovery["modern"], recovery["xpm"]])
    report["recovered_valid_revision"] = recovery
    d.write("reference-result.json", report)


def activate():
    assert json.loads((d.STAGE / "reference-result.json").read_bytes())["applied"]
    assert json.loads((d.STAGE / "qualification.json").read_bytes())["postgresql_native"]
    assert (d.ROOT / "deploy/docker-compose.validators.yml").read_bytes() == (
        d.STAGE / "deploy/docker-compose.validators.yml"
    ).read_bytes()
    before = json.loads((d.STAGE / "before.json").read_bytes())
    gateway = "idml-development-openclaw-idml-1"
    if before[gateway] != d.snapshot()[gateway] and not (d.STAGE / "preactivation.json").exists():
        rollout.refresh_backup()
    rollout.activate()


if __name__ == "__main__":
    os.umask(0o077)
    configure()
    actions = dict(
        prepare=d.prepare,
        build=d.build,
        qualify=rollout.qualify,
        native=native,
        recover=collect_recovery,
        activate=activate,
    )
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=actions)
    actions[parser.parse_args().action]()
