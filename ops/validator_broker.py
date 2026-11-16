"""Linux host broker: fixed registry/images, peer UID authorization, sequential isolated runs."""

import argparse
import hashlib
import json
import os
import re
import selectors
import shutil
import signal
import socket
import struct
import subprocess
import tempfile
import time
from pathlib import Path

MAX_INPUT = 100 * 1024**2
NAMES = {"packtools": ".xml", "spsvalidator": ".zip"}


def command(*args):
    result = subprocess.run(args, capture_output=True, timeout=15, check=False)  # noqa: S603
    if result.returncode:
        raise RuntimeError("container_command_failed")
    return result.stdout.decode().strip()


def receive(sock, size, deadline=None):
    if deadline is None:
        deadline = time.monotonic() + 30
    data = bytearray()
    while len(data) < size:
        left = deadline - time.monotonic()
        if left <= 0:
            raise TimeoutError("receive_deadline")
        sock.settimeout(min(30, left))
        block = sock.recv(min(65536, size - len(data)))
        if not block:
            raise ValueError("truncated_request")
        data.extend(block)
    return bytes(data)


def select_spec(registry, request):
    if set(request) != {
        "version",
        "name",
        "candidate_sha256",
        "size",
        "tool_sha256",
        "validator_version",
        "profile_id",
    }:
        raise ValueError("invalid_request")
    if request["version"] != "local-validator-1.0" or request["name"] not in NAMES:
        raise ValueError("invalid_validator")
    if type(request["size"]) is not int or not 0 < request["size"] <= MAX_INPUT:
        raise ValueError("input_budget")
    if not isinstance(request["candidate_sha256"], str) or not re.fullmatch(
        "[0-9a-f]{64}", request["candidate_sha256"]
    ):
        raise ValueError("invalid_digest")
    matches = [
        s
        for s in registry["validators"]
        if s["name"] == request["name"] and s["channel"] == "active"
    ]
    if len(matches) != 1:
        raise ValueError("invalid_registry")
    spec = matches[0]
    if (
        not re.fullmatch(r"sha256:[0-9a-f]{64}", spec["image_id"])
        or spec["image_id"] != "sha256:" + request["tool_sha256"]
        or spec["version"] != request["validator_version"]
        or spec["profile_id"] != request["profile_id"]
        or spec["input_suffix"] != NAMES[request["name"]]
        or not 1 <= spec["timeout_seconds"] <= 600
        or not 1024 <= spec["max_output_bytes"] <= 16 * 1024**2
    ):
        raise ValueError("registry_mismatch")
    return spec


def create_arguments(spec, candidate):
    return [
        "docker",
        "create",
        "--pull=never",
        "--network=none",
        "--read-only",
        "--user=10001:10001",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--memory=192m",
        "--memory-swap=192m",
        "--cpus=0.25",
        "--pids-limit=64",
        "--log-driver=none",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,size=64m,uid=10001,gid=10001",  # noqa: S108
        "--mount",
        f"type=bind,src={candidate},dst=/input/candidate{spec['input_suffix']},readonly",
        "--entrypoint=python",
        spec["image_id"],
        f"/validator/{spec['name']}_validate.py",
        f"/input/candidate{spec['input_suffix']}",
    ]


def reserve(work, *, starting=False):
    memory = dict(
        (line.split(":")[0], int(line.split()[1]) * 1024)
        for line in Path("/proc/meminfo").read_text().splitlines()
    )
    if memory["MemAvailable"] < (768 if starting else 512) * 1024**2:
        raise RuntimeError("memory_reserve")
    if shutil.disk_usage(work).free < 5 * 1024**3 + MAX_INPUT:
        raise RuntimeError("disk_reserve")


def execute(spec, candidate, work):
    # Optional server-owned authority config; request headers cannot select it.
    try:
        from ops.doi_authority_transport import mount_arguments, stage_authority
    except ModuleNotFoundError:
        from doi_authority_transport import mount_arguments, stage_authority

    reserve(work, starting=True)
    # Image is already installed; never resolve a mutable tag or pull over the network.
    if (
        command("docker", "image", "inspect", spec["image_id"], "--format", "{{.Id}}")
        != spec["image_id"]
    ):
        raise RuntimeError("image_mismatch")
    authority = stage_authority(spec, candidate)
    cid = command(*mount_arguments(create_arguments(spec, candidate), authority))
    process = None
    try:
        process = subprocess.Popen(  # noqa: S603 - fixed Docker command, no shell
            ["docker", "start", "-a", cid],  # noqa: S607
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        output = bytearray()
        deadline = time.monotonic() + spec["timeout_seconds"]
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while selector.get_map():
                reserve(work)
                if time.monotonic() >= deadline:
                    raise RuntimeError("validator_timeout")
                for key, _ in selector.select(timeout=1):
                    block = os.read(key.fileobj.fileno(), 65536)
                    if not block:
                        selector.unregister(key.fileobj)
                        continue
                    output.extend(block)
                    if len(output) > spec["max_output_bytes"]:
                        raise RuntimeError("output_budget")
        process.wait(timeout=5)
        state = json.loads(command("docker", "inspect", "--format", "{{json .State}}", cid))
        if process.returncode or state["ExitCode"] or state["OOMKilled"] or state["Running"]:
            raise RuntimeError("validator_execution_failed")
        return bytes(output)
    finally:
        try:
            command("docker", "rm", "-f", cid)
        finally:
            if process is not None:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=5)
                process.stdout.close()


def handle(connection, registry, work, allowed_uid):
    credentials = connection.getsockopt(
        socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")
    )
    _, uid, _ = struct.unpack("3i", credentials)
    if uid != allowed_uid:
        raise ValueError("unauthorized_peer")
    connection.settimeout(30)
    deadline = time.monotonic() + 120
    length = struct.unpack("!I", receive(connection, 4))[0]
    if not 0 < length <= 2048:
        raise ValueError("header_budget")
    request = json.loads(receive(connection, length))
    spec = select_spec(registry, request)
    reserve(work, starting=True)
    with tempfile.TemporaryDirectory(prefix="validator-", dir=work) as temporary:
        path = Path(temporary) / ("candidate" + spec["input_suffix"])
        digest = hashlib.sha256()
        remaining = request["size"]
        with path.open("xb") as stream:
            while remaining:
                left = deadline - time.monotonic()
                if left <= 0:
                    raise TimeoutError("request_deadline")
                connection.settimeout(min(30, left))
                block = receive(connection, min(65536, remaining), deadline)
                stream.write(block)
                digest.update(block)
                remaining -= len(block)
        if digest.hexdigest() != request["candidate_sha256"]:
            raise ValueError("candidate_mismatch")
        path.chmod(0o644)  # Only this file is bind-mounted; private parent remains mode 0700.
        response = execute(spec, path, work)
        connection.sendall(struct.pack("!I", len(response)))
        connection.sendall(response)


def main():
    def stop(_signal, _frame):
        raise SystemExit(1)

    signal.signal(signal.SIGTERM, stop)
    parser = argparse.ArgumentParser()
    parser.add_argument("--socket", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--uid", type=int, default=10001)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if args.socket.exists() or args.socket.is_symlink():
        parser.error("existing socket refused")
    if not args.work.is_dir() or args.work.is_symlink():
        parser.error("private work directory required")
    work_stat = args.work.stat()
    if work_stat.st_uid != 0 or work_stat.st_mode & 0o077:
        parser.error("work directory must be root-owned and private")
    parent = args.socket.parent.stat()
    if parent.st_uid != 0 or parent.st_mode & 0o022:
        parser.error("socket parent must be root-owned and not writable by group/others")
    registry = json.loads(args.registry.read_text())
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        server.bind(str(args.socket))
        identity = args.socket.stat().st_ino
        try:
            os.chown(args.socket, 0, args.uid)
            args.socket.chmod(0o660)
            server.listen(1)
            while True:
                connection, _ = server.accept()
                with connection:
                    try:
                        handle(connection, registry, args.work, args.uid)
                        print('{"status":"completed"}', flush=True)
                    except Exception as exc:
                        known = {
                            "unauthorized_peer",
                            "invalid_request",
                            "invalid_validator",
                            "invalid_registry",
                            "registry_mismatch",
                            "memory_reserve",
                            "disk_reserve",
                            "authority_untrusted_path",
                            "authority_candidate_mismatch",
                            "authority_expired",
                            "authority_manifest_invalid",
                            "authority_manifest_mismatch",
                            "authority_snapshot_mismatch",
                            "validator_execution_failed",
                        }
                        code = str(exc) if str(exc) in known else "execution_failed"
                        print(json.dumps({"status": "failed", "failure_code": code}), flush=True)
                if args.once:
                    break
        finally:
            if args.socket.exists() and args.socket.stat().st_ino == identity:
                args.socket.unlink()


if __name__ == "__main__":
    main()
