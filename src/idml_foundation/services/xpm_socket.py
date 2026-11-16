"""Private Linux transport to the administrator-owned XPM executor."""

import base64
import hashlib
import json
import socket
import struct
import time
from pathlib import Path

from idml_foundation.services.validation_scope import validate_scope
from idml_foundation.services.xpm_execution import XpmExecutionEvidence

MAX_RESPONSE = 12 * 1024**2


def receive(connection: socket.socket, size: int, deadline: float) -> bytes:
    result = bytearray()
    while len(result) < size:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("xpm_response_deadline")
        connection.settimeout(remaining)
        block = connection.recv(min(65536, size - len(result)))
        if not block:
            raise ValueError("xpm_response_truncated")
        result.extend(block)
    return bytes(result)


class XpmSocketExecutor:
    def __init__(self, socket_path: Path) -> None:
        self.socket_path = socket_path

    def __call__(self, package: bytes, scope: dict[str, str]) -> XpmExecutionEvidence:
        scope = validate_scope(scope)
        if not 0 < len(package) <= 100 * 1024**2 or (
            hashlib.sha256(package).hexdigest() != scope["package_sha256"]
        ):
            raise ValueError("xpm_candidate_mismatch")
        peer = getattr(socket, "SO_PEERCRED", None)
        family = getattr(socket, "AF_UNIX", None)
        if peer is None or family is None:
            raise ValueError("xpm_requires_linux_peer_credentials")
        request = json.dumps(
            dict(
                version="xpm-local-1.0",
                size=len(package),
                candidate_sha256=scope["package_sha256"],
                scope=scope,
            )
        ).encode()
        deadline = time.monotonic() + 360
        with socket.socket(family, socket.SOCK_STREAM) as connection:
            connection.settimeout(30)
            connection.connect(str(self.socket_path))
            if struct.unpack("3i", connection.getsockopt(socket.SOL_SOCKET, peer, 12))[1]:
                raise ValueError("xpm_untrusted_peer")
            connection.sendall(struct.pack("!I", len(request)) + request)
            connection.sendall(package)
            length = struct.unpack("!I", receive(connection, 4, deadline))[0]
            if not 0 < length <= MAX_RESPONSE:
                raise ValueError("xpm_response_budget")
            envelope = json.loads(receive(connection, length, deadline))
        report = base64.b64decode(envelope.pop("report_base64"), validate=True)
        if not 0 < len(report) <= 8 * 1024**2 or "report" in envelope:
            raise ValueError("xpm_report_budget")
        evidence = XpmExecutionEvidence.model_validate(dict(envelope, report=report))
        if evidence.scope != scope or evidence.attestation.report_sha256 != (
            hashlib.sha256(report).hexdigest()
        ):
            raise ValueError("xpm_response_mismatch")
        return evidence
