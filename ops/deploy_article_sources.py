"""Deploy administrative source consent and supervised automatic public collection."""

import argparse
import hashlib
import json
import os
from pathlib import Path

from ops import deploy_vh09 as d
from ops.deploy_vh1_structural import qualify, smoke
from ops.deploy_vh10_worker import TESTS
from ops.install_worker_validators import unit

NAME = "vh10-sources-20261030-v1"


def configure():
    d.NAME = NAME
    d.STAGE = d.ROOT / "releases" / NAME
    d.IMAGE = "idml-foundation:" + NAME
    d.TEST_IMAGE = d.IMAGE + "-qualification"
    d.EXPECTED_MIGRATION = "e2f314253647"
    d.POSTGRES_QUALIFIER = "ops.qualify_article_sources_postgres"
    d.EXTRA_TESTS = tuple(
        f"tests/test_{n}.py"
        for n in (
            *TESTS,
            "article_source_access",
            "runtime_source_authority",
            "scoped_authority_provision",
            "scoped_authority_transport",
        )
    )
    d.COMPOSE.extend(["-f", str(d.ROOT / "deploy/docker-compose.validators.yml")])


def activate():
    evidence = json.loads((d.STAGE / "native-source-summary.json").read_bytes())
    assert evidence["passed"] and evidence["articles"] == 2
    assert (
        evidence["manifest_sha256"]
        == hashlib.sha256((d.STAGE / "release-source-manifest.json").read_bytes()).hexdigest()
    )
    paths = [
        Path("/etc/systemd/system") / f"idml-validation-{kind}-vh1.service"
        for kind in ("modern", "xpm")
    ]
    registries = [
        Path("/var/lib/idml-validation-vh1") / (kind + ".json") for kind in ("modern", "xpm")
    ]
    originals = {p: p.read_bytes() for p in [*paths, *registries]}
    for i, (_p, raw) in enumerate(originals.items()):
        backup = d.STAGE / f"previous-broker-{i}.bin"
        backup.write_bytes(raw)
        backup.chmod(0o600)
    d.activate()  # Additive schema, old-image rollback and reapplication before changing brokers.
    paused = False
    try:
        info = d.database_info()
        assert not any(info["jobs"].get(s, 0) for s in ("queued", "running", "failed_retryable"))
        d.run("docker", "pause", *sorted(d.APPS))
        paused = True
        d.run("systemctl", "stop", *[p.name for p in paths])
        for kind, path, registry in zip(("modern", "xpm"), paths, registries, strict=True):
            path.write_text(unit(kind, d.STAGE))
            path.chmod(0o644)
            value = json.loads(originals[registry])
            value["runtime_article_authorization"] = True
            registry.write_text(json.dumps(value, indent=2))
            registry.chmod(0o600)
        d.run("systemd-analyze", "verify", *[str(p) for p in paths], log="broker-unit-verify.log")
        d.run("systemctl", "daemon-reload")
        d.run("systemctl", "start", *[p.name for p in paths])
    except Exception:
        for p, raw in originals.items():
            p.write_bytes(raw)
        d.run("systemctl", "daemon-reload")
        d.run("systemctl", "restart", *[p.name for p in paths])
        raise
    finally:
        if paused:
            d.run("docker", "unpause", *sorted(d.APPS))
    for path in paths:
        assert d.run("systemctl", "is-active", path.name) == "active"
    d.healthy()
    d.unaffected(json.loads((d.STAGE / "before.json").read_bytes()))
    d.write(
        "source-activation.json",
        dict(
            http=smoke(),
            runtime_article_authorization=True,
            active_article_decisions_created=0,
            ai_invoked=False,
            homologation_ready=False,
        ),
    )
    print("source authorization and supervised collection active; no implicit grants", flush=True)


def main():
    os.umask(0o077)
    configure()
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "build", "qualify", "activate"))
    action = parser.parse_args().action
    dict(prepare=d.prepare, build=d.build, qualify=qualify, activate=activate)[action]()


if __name__ == "__main__":
    main()
