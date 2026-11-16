"""Install the validated worker-only catalog mount on the existing development image."""

import hashlib
import json
import os
from pathlib import Path

from ops import deploy_vh09 as deployment
from ops.deploy_scanner_queue import configure

STAGE = Path("/opt/idml-platform/releases/vh14-catalog-20261105-v1")
TARGET = Path("/var/lib/idml-vh1-enrichment/runtime")
PREVIOUS = "6fb510860cab34c33e42c854ebc9735821bb814316c20e427a5d0c832aef9f61"


def replace(path, data):
    temporary = path.with_suffix(".catalog-new")
    with temporary.open("xb") as stream:
        stream.write(data)
    temporary.chmod(0o644)
    temporary.replace(path)


def main():
    configure()
    d = deployment
    d.STAGE = STAGE
    path = d.ROOT / "deploy/docker-compose.validators.yml"
    old = path.read_bytes()
    new = (STAGE / "docker-compose.validators.yml").read_bytes()
    assert hashlib.sha256(old).hexdigest() == PREVIOUS
    assert not (STAGE / "previous-compose.yml").exists()
    before = d.snapshot()
    db = d.database_info()
    assert not any(db["jobs"].get(k, 0) for k in ("queued", "running", "failed_retryable"))
    assert before["idml-development-worker-1"]["image"] == d.IMAGE
    (STAGE / "previous-compose.yml").write_bytes(old)
    d.run("docker", "pause", *sorted(d.APPS))
    try:
        backup = d.run("sh", "ops/backup.sh", log="backup.log")
    finally:
        d.run("docker", "unpause", *sorted(d.APPS))
    assert Path(backup).resolve().parent == d.ROOT / "backups"
    d.run("sh", "ops/restore-test.sh", backup, log="restore-test.log")
    for directory in (TARGET.parent, TARGET, TARGET / "authorizations"):
        assert directory.resolve() == directory
        directory.mkdir(exist_ok=True)
        assert directory.stat().st_uid == 0
        os.chown(directory, 0, 10001 if directory != TARGET.parent else 0)
        directory.chmod(0o750 if directory != TARGET.parent else 0o700)
    try:
        replace(path, new)
        d.run(*d.COMPOSE, "config", "--quiet")
        d.run(*d.COMPOSE, "up", "-d", "--no-deps", "worker", log="apply.log")
        d.healthy()
        after = d.unaffected(before)
        assert after["idml-development-api-1"] == before["idml-development-api-1"]
        for name in d.APPS:
            mounts = json.loads(d.run("docker", "inspect", "--format", "{{json .Mounts}}", name))
            found = [m for m in mounts if m["Destination"] == "/run/idml-enrichment"]
            if name.endswith("worker-1"):
                assert len(found) == 1 and not found[0]["RW"] and found[0]["Source"] == str(TARGET)
            else:
                assert not found
        probe = (
            "from idml_foundation.settings import get_settings; import os; "
            "s=get_settings(); root=s.enrichment_root; assert str(root)=='/run/idml-enrichment'; "
            "assert s.enrichment_location=='vps' and os.access(root,os.R_OK|os.X_OK) "
            "and not os.access(root,os.W_OK)"
        )
        d.run("docker", "exec", "idml-development-worker-1", "python", "-c", probe)
        assert d.database_info() == db
        d.write(
            "transport.json",
            dict(
                image=d.IMAGE,
                backup=backup,
                restore_passed=True,
                worker_read_only=True,
                api_mount=False,
                api_preserved=True,
                db_counts_preserved=True,
                config_sha256=hashlib.sha256(new).hexdigest(),
            ),
        )
    except Exception:
        replace(path, old)
        d.run(*d.COMPOSE, "up", "-d", "--no-deps", "worker", log="recovery.log")
        d.healthy()
        raise


if __name__ == "__main__":
    os.umask(0o077)
    main()
