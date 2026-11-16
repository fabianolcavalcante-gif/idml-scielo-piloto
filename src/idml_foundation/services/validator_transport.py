"""Bounded local Unix-socket transport; Docker remains outside the application container."""

import hashlib
import json
import socket
import struct
from pathlib import Path

from idml_foundation.release.validation_engine import (
    ValidationEngine,
    ValidatorCommand,
    ValidatorRun,
)

MAX_INPUT = 100 * 1024**2


def receive(sock: socket.socket, size: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < size:
        chunk = sock.recv(min(65536, size - len(chunks)))
        if not chunk:
            raise ValueError("truncated validator response")
        chunks.extend(chunk)
    return bytes(chunks)


class LocalValidatorExecutor:
    def __init__(self, socket_path: Path) -> None:
        self.socket_path = socket_path

    def __call__(self, candidate: bytes, specification: ValidatorCommand) -> ValidatorRun:
        if not 0 < len(candidate) <= MAX_INPUT:
            raise ValueError("validator input budget")
        request = json.dumps(
            {
                "version": "local-validator-1.0",
                "name": specification.name,
                "candidate_sha256": hashlib.sha256(candidate).hexdigest(),
                "size": len(candidate),
                "tool_sha256": specification.tool_sha256,
                "validator_version": specification.version,
                "profile_id": specification.profile_id,
            },
            sort_keys=True,
        ).encode()
        family = getattr(socket, "AF_UNIX", None)
        peer_option = getattr(socket, "SO_PEERCRED", None)
        if family is None or peer_option is None:
            raise ValueError("validator transport requires Linux peer credentials")
        with socket.socket(family, socket.SOCK_STREAM) as connection:
            connection.settimeout(specification.timeout_seconds + 30)
            connection.connect(str(self.socket_path))
            credentials = connection.getsockopt(socket.SOL_SOCKET, peer_option, 12)
            if struct.unpack("3i", credentials)[1] != 0:
                raise ValueError("untrusted validator broker")
            connection.sendall(struct.pack("!I", len(request)))
            connection.sendall(request)
            connection.sendall(candidate)
            length = struct.unpack("!I", receive(connection, 4))[0]
            if not 0 < length <= specification.max_output_bytes:
                raise ValueError("validator output budget")
            envelope = receive(connection, length)
        return ValidationEngine().ingest(candidate, specification, envelope)
