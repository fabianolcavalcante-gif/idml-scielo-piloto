"""Deploy the catalog-aware conversion and portal downloads."""

import argparse
import json
import os
from pathlib import Path

from ops import deploy_scanner_queue as previous
from ops import deploy_vh09 as d
from ops import deploy_vh1_structural as rollout

NAME = "vh14-catalog-portal-20261105-v1"


def configure():
    previous.configure()
    d.NAME = rollout.NAME = NAME
    rollout.PREVIOUS = "idml-foundation:" + previous.NAME
    d.STAGE = d.ROOT / "releases" / NAME
    d.IMAGE = "idml-foundation:" + NAME
    d.TEST_IMAGE = d.IMAGE + "-qualification"
    d.EXTRA_TESTS += (
        "tests/test_enrichment_bundles.py",
        "tests/test_source_authorization.py",
        "tests/test_reference_types.py",
        "tests/test_institution_locations.py",
    )


def activate():
    transport = json.loads(
        (d.ROOT / "releases/vh14-catalog-20261105-v1/transport.json").read_bytes()
    )
    assert transport["worker_read_only"] and transport["restore_passed"]
    path = Path("deploy/docker-compose.validators.yml")
    assert (d.ROOT / path).read_bytes() == (d.STAGE / path).read_bytes()
    rollout.activate()


if __name__ == "__main__":
    os.umask(0o077)
    configure()
    actions = dict(prepare=d.prepare, build=d.build, qualify=rollout.qualify, activate=activate)
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=actions)
    actions[p.parse_args().action]()
