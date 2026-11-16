"""Deploy the VH-17 regression candidate."""

import argparse
import os

from ops import deploy_named_inputs as previous
from ops import deploy_vh09 as d
from ops import deploy_vh1_structural as rollout
from ops.deploy_catalog_runtime import activate

NAME = "vh17-regression-20261109-v1"


def configure():
    previous.configure()
    d.NAME = rollout.NAME = NAME
    rollout.PREVIOUS = "idml-foundation:" + previous.NAME
    d.STAGE = d.ROOT / "releases" / NAME
    d.IMAGE = "idml-foundation:" + NAME
    d.TEST_IMAGE = d.IMAGE + "-qualification"
    d.EXTRA_TESTS += (
        "tests/test_vh17_evidence.py",
        "tests/test_vh17_regression.py",
        "tests/test_xpm_compatibility.py",
        "tests/test_xpm_sps_compatibility.py",
    )


if __name__ == "__main__":
    os.umask(0o077)
    configure()
    actions = dict(prepare=d.prepare, build=d.build, qualify=rollout.qualify, activate=activate)
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=actions)
    actions[p.parse_args().action]()
