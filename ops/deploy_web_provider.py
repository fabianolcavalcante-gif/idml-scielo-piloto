"""Deploy operator-authorized OpenClaw evaluations."""

import argparse
import os

from ops import deploy_vh09 as d
from ops import deploy_vh1_structural as rollout
from ops import deploy_web_access as previous
from ops.deploy_catalog_runtime import activate as activate_candidate

NAME = "vh19-web-provider-20261114-v1"


def configure():
    previous.configure()
    d.NAME = rollout.NAME = NAME
    rollout.PREVIOUS = "idml-foundation:" + previous.NAME
    d.STAGE = d.ROOT / "releases" / NAME
    d.IMAGE = "idml-foundation:" + NAME
    d.TEST_IMAGE = d.IMAGE + "-qualification"
    d.EXTRA_TESTS += ("tests/test_web_operator_edit.py",)


if __name__ == "__main__":
    os.umask(0o077)
    configure()
    actions = dict(
        prepare=d.prepare, build=d.build, qualify=rollout.qualify, activate=activate_candidate
    )
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=actions)
    actions[p.parse_args().action]()
