"""Deploy the named article and revision inputs."""

import argparse
import os

from ops import deploy_catalog_runtime as previous
from ops import deploy_vh09 as d
from ops import deploy_vh1_structural as rollout

NAME = "vh11-named-inputs-20261106-v1"


def configure():
    previous.configure()
    d.NAME = rollout.NAME = NAME
    rollout.PREVIOUS = "idml-foundation:" + previous.NAME
    d.STAGE = d.ROOT / "releases" / NAME
    d.IMAGE = "idml-foundation:" + NAME
    d.TEST_IMAGE = d.IMAGE + "-qualification"
    d.EXTRA_TESTS += ("tests/test_named_inputs.py",)


if __name__ == "__main__":
    os.umask(0o077)
    configure()
    actions = dict(
        prepare=d.prepare, build=d.build, qualify=rollout.qualify, activate=previous.activate
    )
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=actions)
    actions[p.parse_args().action]()
