"""Handle one INSTREAM request on a private systemd Accept=yes socket."""

import os
import socket
import struct
import subprocess
import tempfile
import time
from contextlib import contextmanager

IMAGE = "clamav/clamav@sha256:bda39705e291105049c3936e2803ac90b955172af8030f94f05dce1252df6c6d"
VOLUME = "idml_vh1_clamav_signatures:/var/lib/clamav:ro"
MAX_BYTES = 100 * 1024**2
LOCK = "/run/lock/idml-clamav-vh1.lock"
QUEUE_WAIT_SECONDS = 130


@contextmanager
def scan_slot(path=LOCK, wait=QUEUE_WAIT_SECONDS):
    """Serialize engines and signature updates, releasing before replying to the client."""
    import fcntl

    with open(path, "a") as lock:
        deadline = time.monotonic() + wait
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("scanner queue deadline") from None
                time.sleep(min(0.1, max(0, deadline - time.monotonic())))
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def receive(client, count, deadline):
    buf = bytearray()
    while len(buf) < count:
        left = deadline - time.monotonic()
        if left <= 0:
            raise TimeoutError()
        client.settimeout(left)
        block = client.recv(count - len(buf))
        if not block:
            raise ValueError("truncated stream")
        buf.extend(block)
    return buf


def scan(client):
    if (
        struct.unpack("3i", client.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))[1]
        != 10001
    ):
        raise ValueError("invalid peer")
    deadline = time.monotonic() + 25
    if receive(client, 10, deadline) != b"zINSTREAM\0":
        raise ValueError("invalid command")
    total = 0
    with tempfile.TemporaryFile() as data:
        while True:
            size = int.from_bytes(receive(client, 4, deadline), "big")
            if not size:
                break
            total += size
            if size > 65536 or total > MAX_BYTES:
                raise ValueError("stream limit")
            data.write(receive(client, size, deadline))
        if not total:
            raise ValueError("empty stream")
        data.seek(0)
        args = [
            "/usr/bin/docker",
            "run",
            "--pull=never",
            "--rm",
            "-i",
            "--network=none",
            "--memory=850m",
            "--memory-swap=1400m",
            "--cpus=0.7",
            "--pids-limit=32",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--user=100:101",
            "--read-only",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,nodev,size=180m",  # noqa: S108
            "-v",
            VOLUME,
            "--entrypoint",
            "timeout",
            IMAGE,
            "-s",
            "KILL",
            "110",
            "clamscan",
            "--stdout",
            "--no-summary",
            "--fail-if-cvd-older-than=7",
            "--alert-exceeds-max=yes",
            "--alert-encrypted=yes",
            "--max-scansize=550M",
            "--max-filesize=100M",
            "-",
        ]
        with scan_slot():
            result = subprocess.run(args, stdin=data, capture_output=True, timeout=125, check=False)  # noqa: S603
    if (
        result.returncode == 0
        and result.stdout.strip() == b"stdin: OK"
        and not result.stderr.strip()
    ):
        return b"stream: OK\0"
    if result.returncode == 1 and result.stdout.strip().endswith(b" FOUND"):
        return b"stream: rejected FOUND\0"
    return b"stream: ERROR\0"


if __name__ == "__main__":
    with socket.socket(fileno=os.dup(0)) as client:
        try:
            reply = scan(client)
        except (ValueError, OSError, subprocess.SubprocessError):
            reply = b"stream: ERROR\0"
        client.sendall(reply)
