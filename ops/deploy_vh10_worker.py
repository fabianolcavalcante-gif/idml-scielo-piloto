"""Deploy worker validation and additive restoration schema; keep AI disabled."""

import argparse
import json
import os

from ops import deploy_vh09 as deployment
from ops.deploy_vh1_structural import qualify, smoke

NAME = "vh10-worker-20261030-v1"
TESTS = (
    "worker_xpm_integration",
    "worker_and_cli",
    "phase7_v10_workflow",
    "xpm_execution",
    "xpm_socket",
    "xpm_composed",
    "scoped_validator_transport",
    "package_formal_validation",
    "restored_package_validation",
    "autocorrection_promotion",
    "validation_diagnosis",
    "auth_and_rbac",
    "canonical_heads",
    "jobs",
    "api",
)


def configure():
    deployment.NAME = NAME
    deployment.STAGE = deployment.ROOT / "releases" / NAME
    deployment.IMAGE = f"idml-foundation:{NAME}"
    deployment.TEST_IMAGE = f"{deployment.IMAGE}-qualification"
    deployment.POSTGRES_QUALIFIER = "ops.qualify_vh09_restored_postgres"
    deployment.EXPECTED_MIGRATION = "d1f203142536"
    deployment.EXTRA_TESTS = tuple(f"tests/test_{name}.py" for name in TESTS)


def activate():
    d = deployment
    for kind in ("modern", "xpm"):
        assert d.run("systemctl", "is-active", f"idml-validation-{kind}-vh1.service") == "active"
    d.COMPOSE.extend(["-f", str(d.ROOT / "deploy/docker-compose.validators.yml")])
    d.activate()
    checks = smoke()
    # Inspect selected settings/mounts only; never dump environment or credentials.
    for name in sorted(d.APPS):
        mounts = json.loads(d.run("docker", "inspect", "--format", "{{json .Mounts}}", name))
        assert not any("docker.sock" in m["Destination"] for m in mounts)
        if "worker" in name:
            for kind in ("modern", "xpm"):
                target = f"/run/idml-{kind}-vh1"
                assert any(m["Destination"] == target and not m["RW"] for m in mounts)
        probe = (
            "from idml_foundation.settings import get_settings; "
            "s=get_settings(); "
            "assert str(s.journal_profile_path)=='/app/profiles/esa-aop-1.1.json'; "
            "assert not s.feature_openclaw and not s.feature_ai_swarm; "
        )
        if "worker" in name:
            probe += (
                "import socket; assert s.validator_scoped_authorities; "
                "assert s.validator_socket and s.xpm_socket; "
                "clients=[socket.socket(socket.AF_UNIX) for _ in range(2)]; "
                "[(c.settimeout(3),c.connect(str(p)),c.sendall(b'{}\\n'),c.close()) "
                "for c,p in zip(clients,[s.validator_socket,s.xpm_socket])]; "
            )
        else:
            probe += "assert s.validator_socket is None and s.xpm_socket is None; "
        probe += "print('configured')"
        assert d.run("docker", "exec", name, "python", "-c", probe) == "configured"
    d.write(
        "worker-smoke.json",
        dict(
            http=checks,
            api_profile_matches_worker=True,
            worker_sockets_reachable=True,
            no_application_docker_socket=True,
            ai_enabled=False,
            real_article_authority_provisioning_pending=True,
            homologation_ready=False,
        ),
    )
    print("HTTP, profile and worker sockets verified; AI remains disabled", flush=True)


def main():
    os.umask(0o077)
    configure()
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "build", "qualify", "activate"))
    action = parser.parse_args().action
    {
        "prepare": deployment.prepare,
        "build": deployment.build,
        "qualify": qualify,
        "activate": activate,
    }[action]()


if __name__ == "__main__":
    main()
