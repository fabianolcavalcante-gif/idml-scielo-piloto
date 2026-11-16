"""Deploy the web source permissions and revision recovery."""

import argparse
import hashlib
import os

from ops import deploy_regression as previous
from ops import deploy_vh09 as d
from ops import deploy_vh1_structural as rollout
from ops.deploy_catalog_runtime import activate as activate_candidate

NAME = "vh18-web-access-20261111-v1"


def configure():
    previous.configure()
    d.NAME = rollout.NAME = NAME
    rollout.PREVIOUS = "idml-foundation:" + previous.NAME
    d.STAGE = d.ROOT / "releases" / NAME
    d.IMAGE = "idml-foundation:" + NAME
    d.TEST_IMAGE = d.IMAGE + "-qualification"
    d.EXTRA_TESTS += (
        "tests/test_web_operational_access.py",
        "tests/test_article_source_access.py",
    )


def activate():
    """Install the reviewed mount change with an exact predecessor guard."""
    path = "deploy/docker-compose.validators.yml"
    previous_path = d.ROOT / "releases" / previous.NAME / path
    destination = d.ROOT / path
    original = destination.read_bytes()
    assert original == previous_path.read_bytes(), "validator_overlay_changed"
    candidate = (d.STAGE / path).read_bytes()
    manifest = d.verify_sources()
    assert hashlib.sha256(candidate).hexdigest() == manifest["files"][path]
    assert (d.Path("/var/lib/idml-web-sources")).is_dir()
    backup = d.STAGE / "rollback-validators.yml"
    assert not backup.exists()
    backup.write_bytes(original)
    backup.chmod(0o600)
    temporary = destination.with_suffix(".pending")
    temporary.write_bytes(candidate)
    temporary.chmod(0o644)
    temporary.replace(destination)
    try:
        activate_candidate()
    except Exception:
        temporary.write_bytes(original)
        temporary.chmod(0o644)
        temporary.replace(destination)
        d.run(*d.COMPOSE, "up", "-d", "--no-deps", "api", "worker", log="overlay-recovery.log")
        d.healthy()
        raise


if __name__ == "__main__":
    os.umask(0o077)
    configure()
    actions = dict(prepare=d.prepare, build=d.build, qualify=rollout.qualify, activate=activate)
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=actions)
    actions[p.parse_args().action]()
