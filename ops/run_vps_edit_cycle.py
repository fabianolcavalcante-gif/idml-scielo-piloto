"""Run an edit-cycle qualification on the development VPS, isolated from active article data."""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from contextlib import ExitStack
from pathlib import Path
from uuid import uuid4

PLATFORM = Path("/opt/idml-platform")
STAGE = PLATFORM / "releases/vh10-edit-20261101-v2"
IMAGE = "idml-foundation:vh10-edit-20261101-v2-qualification"
ROOT = Path(__file__).resolve().parent
DATA = ROOT / "private"
SOCKETS = Path("/run") / ("idml-edit-" + uuid4().hex)
NAME = "idml-edit-lab-" + uuid4().hex[:12]
FILES = (
    "edit_cycle_lab.py",
    "qualify_edit_cycle.py",
    "qualify_edit_preflight.py",
    "qualify_real_edit_abstention.py",
)


def execute(argv, log, *, env=None, timeout=900):
    with (ROOT / log).open("wb") as f:
        result = subprocess.run(  # noqa: S603 - fixed supervisor argument vectors
            argv,
            stdout=f,
            stderr=subprocess.STDOUT,
            cwd=PLATFORM,
            env=env,
            timeout=timeout,
            check=False,
        )
    if result.returncode:
        raise RuntimeError("qualification_failed:" + log)


def runner(*, live=False):
    result = [
        "docker",
        "run",
        "--rm",
        "--read-only",
        "--user=10001:10001",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--cpus=0.6",
        "--memory=480m",
        "--pids-limit=128",
        "--network=" + ("idml_development_openclaw" if live else "none"),
        "--tmpfs",
        "/tmp:rw,size=512m,mode=1777",  # noqa: S108 - disposable container filesystem
        "-w",
        "/qualification",
        "-e",
        "PYTHONPATH=/app/src:/qualification",
        "-e",
        "IDML_DATABASE_URL=sqlite+pysqlite:////case/qualification.sqlite",
        "-v",
        f"{STAGE}:/qualification:ro",
        "-v",
        f"{DATA}:/case",
    ]
    result.extend(["-v", f"{ROOT / 'runner-ops'}:/qualification/ops:ro"])
    return result


def validators(stack):
    SOCKETS.mkdir(mode=0o755)
    SOCKETS.chmod(0o755)
    stack.callback(SOCKETS.rmdir)
    authority = ROOT / "authority"
    authority.mkdir()
    (authority / "authorizations").mkdir()
    (authority / "bundles").mkdir()
    env = os.environ | {"PYTHONPATH": f"{STAGE}/src:{STAGE}:{STAGE}/src/idml_foundation/services"}
    sys.path.insert(0, str(STAGE))
    sys.path.insert(0, str(STAGE / "src"))
    from ops.xpm_validator_broker import IMAGE as xpm_image

    modern = json.loads((STAGE / "config/validator-registry-vh1-composed.json").read_bytes())
    modern.update(authority_root=str(authority), runtime_article_authorization=True)
    for kind, module, config in [
        ("modern", "scoped_validator_broker", modern),
        (
            "xpm",
            "xpm_validator_broker",
            dict(
                version="xpm-online-composed-1.0",
                image=xpm_image,
                runtime_article_authorization=True,
            ),
        ),
    ]:
        path = ROOT / (kind + ".json")
        path.write_text(json.dumps(config))
        work = ROOT / kind
        work.mkdir()
        socket = SOCKETS / (kind + ".sock")
        shim = (
            f"from ops import runtime_source_authority as r; r.API_CONTAINER={NAME!r}; "
            f"from ops.{module} import main; main()"
        )
        log = stack.enter_context((ROOT / (kind + ".log")).open("wb"))
        proc = subprocess.Popen(  # noqa: S603 - two fixed broker modules
            [
                sys.executable,
                "-c",
                shim,
                "--socket",
                str(socket),
                "--work",
                str(work),
                "--registry",
                str(path),
            ],
            cwd=STAGE,
            env=env,
            stdout=log,
            stderr=log,
        )

        def stop(process=proc, path=socket):
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            path.unlink(missing_ok=True)

        stack.callback(stop)
        end = time.monotonic() + 20
        while not socket.exists():
            if proc.poll() is not None or time.monotonic() > end:
                raise RuntimeError("broker_unavailable")
            time.sleep(0.1)


def main(*, reference=False):
    os.umask(0o077)
    code = ROOT / "runner-ops"
    code.mkdir()
    code.chmod(0o755)
    overrides = [] if reference else [ROOT / name for name in FILES]
    for source in [*(STAGE / "ops").glob("*.py"), *overrides]:
        target = code / source.name
        shutil.copyfile(source, target)
        target.chmod(0o644)
    DATA.mkdir(mode=0o700)
    os.chown(DATA, 10001, 10001)
    command = [*runner(), "-v", "/run/idml-clamav-vh1:/run/idml-clamav-vh1:ro"]
    if reference:
        command.extend(
            [
                "-v",
                f"{ROOT}/inputs:/inputs:ro",
                "-v",
                f"{ROOT}/reference:/reference:ro",
                IMAGE,
                "python",
                "-m",
                "ops.qualify_reference_edit",
            ]
        )
    else:
        command.extend([IMAGE, "python", "-m", "ops.qualify_edit_cycle", "prepare", "/case"])
    execute(command, "prepare.log")
    print("Scanned inputs and prepared an offline candidate", flush=True)
    if subprocess.check_output(
        ["/usr/bin/docker", "ps", "-q", "--filter", "name=idml-development-openclaw-egress-proxy-1"]
    ).strip():
        raise RuntimeError("another_provider_window_active")
    try:
        execute(["sh", str(PLATFORM / "ops/openclaw-provider-stage.sh")], "stage.log")
        print("Dedicated provider ready", flush=True)
        # Only the gateway token goes to the runner; the provider key stays in the gateway.
        script = 'set -eu; set -a; . /opt/idml-platform/.env; set +a; exec "$@"'
        execute(
            [
                "sh",
                "-c",
                script,
                "lab",
                *runner(live=True),
                "-e",
                "IDML_OPENCLAW_GATEWAY_TOKEN",
                IMAGE,
                "python",
                "-m",
                "ops.qualify_edit_cycle",
                "review",
                "/case",
            ],
            "review.log",
        )
    finally:
        execute(
            ["sh", str(PLATFORM / "ops/openclaw-provider-disable.sh")],
            "disable.log",
            env=os.environ | {"IDML_RESET_OPENCLAW_STATE": "true"},
        )
    receipt = json.loads((DATA / "votes.json").read_bytes())
    print(
        "Provider detached; decision", receipt["state"], "calls", len(receipt["calls"]), flush=True
    )
    if receipt["state"] != "supported_for_revalidation":
        return
    validate_saved(["controlled", "validate"])


def validate_saved(actions):
    # Allow the shared VPS to finish background scans before creating validator containers.
    deadline = time.monotonic() + 240
    while time.monotonic() < deadline:
        available = int(
            next(
                line.split()[1]
                for line in Path("/proc/meminfo").read_text().splitlines()
                if line.startswith("MemAvailable:")
            )
        )
        if available >= 1024 * 1024:
            break
        time.sleep(5)
    else:
        raise RuntimeError("host_memory_reserve_unavailable")
    with ExitStack() as stack:
        validators(stack)
        execute(
            [
                *runner(),
                "-d",
                "--name",
                NAME,
                "-v",
                f"{SOCKETS}:/socket:ro",
                IMAGE,
                "sleep",
                "1800",
            ],
            "run.log",
        )
        stack.callback(lambda: execute(["docker", "rm", "-f", NAME], "remove.log"))
        for action in actions:
            execute(
                ["docker", "exec", NAME, "python", "-m", "ops.qualify_edit_cycle", action, "/case"],
                action + ".log",
            )
            row = json.loads((ROOT / (action + ".log")).read_text().splitlines()[-1])
            (ROOT / (action + "-result.json")).write_text(json.dumps(row, indent=2))
            print(action, "applied", row.get("applied"), "reasons", row.get("reasons"), flush=True)


if __name__ == "__main__":
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--revalidate", action="store_true")
    actions.add_argument("--real-abstention", action="store_true")
    args = parser.parse_args()
    if args.real_abstention:
        execute(
            [
                *runner(),
                "-v",
                "/run/idml-clamav-vh1:/run/idml-clamav-vh1:ro",
                "-v",
                "/var/lib/idml-vh1-qualification/scan-lab-20261031/inputs:/inputs:ro",
                IMAGE,
                "python",
                "-m",
                "ops.qualify_real_edit_abstention",
                "/inputs/e86/ESA_2024086_AOP.idml",
                "/inputs/e135/ESA_2024135_AOP.idml",
            ],
            "real-abstention.log",
        )
    elif args.revalidate:
        if json.loads((DATA / "votes.json").read_bytes())["state"] != "supported_for_revalidation":
            raise RuntimeError("candidate_not_supported")
        # Preserve every earlier report and run in separate broker directories.
        source = ROOT / "runner-ops"
        ROOT = ROOT / ("revalidation-" + uuid4().hex)
        ROOT.mkdir(mode=0o700)
        (ROOT / "runner-ops").symlink_to(source, target_is_directory=True)
        validate_saved(["validate"])
    else:
        main()
