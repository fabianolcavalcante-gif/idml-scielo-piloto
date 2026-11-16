"""Install fixed root-owned broker units; no app Docker access or implicit grants."""

import argparse
import json
import os
import re
import stat
import subprocess
from pathlib import Path

from ops.xpm_validator_broker import IMAGE

STATE = Path("/var/lib/idml-validation-vh1")


def unit(kind, source):
    if kind not in {"modern", "xpm"} or not re.fullmatch(
        r"/opt/idml-platform/releases/[a-z0-9-]+", source.as_posix()
    ):
        raise ValueError("invalid_service_parameters")
    module = "scoped_validator_broker" if kind == "modern" else "xpm_validator_broker"
    command = (
        f"/usr/bin/python3 -m ops.{module} --socket /run/idml-{kind}-vh1/validator.sock "
        f"--work {STATE}/{kind} --registry {STATE}/{kind}.json --uid 10001"
    )
    return f"""# Managed IDML VH1 validator broker; administrator only.
[Unit]
Description=IDML VH1 {kind} validator broker
Requires=docker.service
After=docker.service
StartLimitIntervalSec=60
StartLimitBurst=3

[Service]
Type=simple
User=root
Group=root
WorkingDirectory={source}
Environment=PYTHONDONTWRITEBYTECODE=1
Environment=PYTHONPATH={source}/src:{source}:{source}/src/idml_foundation/services
ExecStart={command}
ExecStartPre=/usr/bin/python3 -m ops.install_worker_validators --clean-socket {kind}
RuntimeDirectory=idml-{kind}-vh1
RuntimeDirectoryMode=0755
RuntimeDirectoryPreserve=yes
UMask=0077
Restart=on-failure
RestartSec=5
TimeoutStopSec=40
KillMode=control-group
NoNewPrivileges=true
ProtectHome=true
ProtectSystem=full
PrivateTmp=true
ReadOnlyPaths={source}
MemoryMax=512M
CPUQuota=50%
TasksMax=128
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"""


def clean_socket(kind):
    """Called only before systemd starts the service, after its old process exited."""
    if os.geteuid() != 0 or kind not in {"modern", "xpm"}:
        raise ValueError("root_and_known_service_required")
    parent = Path(f"/run/idml-{kind}-vh1")
    metadata = parent.lstat()
    if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid or metadata.st_mode & 0o022:
        raise ValueError("unsafe_socket_parent")
    path = parent / "validator.sock"
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return
    if not stat.S_ISSOCK(metadata.st_mode) or metadata.st_uid or metadata.st_gid != 10001:
        raise ValueError("unsafe_existing_socket")
    path.unlink()


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--source", type=Path)
    mode.add_argument("--clean-socket", choices=("modern", "xpm"))
    args = parser.parse_args()
    if args.clean_socket:
        clean_socket(args.clean_socket)
        return
    source = args.source.resolve(strict=True)
    if os.geteuid() != 0 or source.parent != Path("/opt/idml-platform/releases"):
        raise ValueError("root_and_frozen_release_required")
    import hashlib

    manifest = json.loads((source / "release-source-manifest.json").read_bytes())
    for name, digest in manifest["files"].items():
        path = source / name
        if not path.resolve().is_relative_to(source) or path.is_symlink():
            raise ValueError("source_path_invalid")
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError("source_changed")
        if path.stat().st_uid != 0 or path.stat().st_mode & 0o022:
            raise ValueError("source_permissions_invalid")
    if STATE.exists():
        raise ValueError("existing_installation_refused")
    units = {
        k: Path("/etc/systemd/system") / f"idml-validation-{k}-vh1.service"
        for k in ["modern", "xpm"]
    }
    if any(p.exists() for p in units.values()):
        raise ValueError("existing_service_refused")
    STATE.mkdir(mode=0o700)
    for name in ["modern", "xpm", "authority", "authority/authorizations", "authority/bundles"]:
        (STATE / name).mkdir(mode=0o700)
    modern = json.loads((source / "config/validator-registry-vh1-composed.json").read_bytes())
    modern["authority_root"] = str(STATE / "authority")
    for kind, registry in [
        ("modern", modern),
        ("xpm", dict(version="xpm-online-composed-1.0", image=IMAGE)),
    ]:
        path = STATE / (kind + ".json")
        path.write_text(json.dumps(registry, indent=2))
        path.chmod(0o600)
        units[kind].write_text(unit(kind, source))
        units[kind].chmod(0o644)
    subprocess.run(  # noqa: S603 - fixed administrator-owned unit paths
        ["/usr/bin/systemd-analyze", "verify", *[str(p) for p in units.values()]], check=True
    )
    subprocess.run(["/usr/bin/systemctl", "daemon-reload"], check=True)
    subprocess.run(  # noqa: S603 - fixed unit names, no shell
        ["/usr/bin/systemctl", "enable", "--now", *[p.name for p in units.values()]], check=True
    )
    print(
        json.dumps(
            dict(
                installed=True,
                services=[p.name for p in units.values()],
                authority_grants_created=0,
                application_configuration_changed=False,
            )
        )
    )


if __name__ == "__main__":
    main()
