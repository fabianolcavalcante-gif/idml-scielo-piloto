import socket
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from idml_foundation.settings import Settings


@dataclass(frozen=True)
class ScanResult:
    clean: bool
    status: str


class ScannerUnavailableError(RuntimeError):
    pass


class ContentScanner(Protocol):
    def scan(self, data: bytes) -> ScanResult: ...


class PolicyOnlyScanner:
    def scan(self, data: bytes) -> ScanResult:
        del data
        return ScanResult(clean=True, status="policy_only")


class ClamAVScanner:
    def __init__(
        self, host: str, port: int, timeout: float = 30.0, path: Path | None = None
    ) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.path = path

    def _connect(self) -> socket.socket:
        if self.path is None:
            return socket.create_connection((self.host, self.port), timeout=self.timeout)
        peer_option = getattr(socket, "SO_PEERCRED", None)
        if not hasattr(socket, "AF_UNIX") or peer_option is None:
            raise ScannerUnavailableError("scanner requires Unix peer credentials")
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            client.settimeout(self.timeout)
            client.connect(str(self.path))
            if struct.unpack("3i", client.getsockopt(socket.SOL_SOCKET, peer_option, 12))[1] != 0:
                raise ScannerUnavailableError("untrusted scanner")
            return client
        except BaseException:
            client.close()
            raise

    def scan(self, data: bytes) -> ScanResult:
        try:
            with self._connect() as connection:
                connection.sendall(b"zINSTREAM\0")
                view = memoryview(data)
                for offset in range(0, len(view), 64 * 1024):
                    chunk = view[offset : offset + 64 * 1024]
                    connection.sendall(len(chunk).to_bytes(4, "big"))
                    connection.sendall(chunk)
                connection.sendall((0).to_bytes(4, "big"))
                response = bytearray()
                while len(response) <= 4096 and b"\0" not in response:
                    part = connection.recv(4096)
                    if not part:
                        break
                    response.extend(part)
        except OSError as exc:
            raise ScannerUnavailableError("content scanner unavailable") from exc
        if response == b"stream: OK\0":
            return ScanResult(clean=True, status="clamav_clean")
        if (
            len(response) <= 4096
            and response.startswith(b"stream: ")
            and response.endswith(b" FOUND\0")
            and response.count(b"\0") == 1
        ):
            return ScanResult(clean=False, status="malware_detected")
        raise ScannerUnavailableError("content scanner returned an indeterminate response")


def build_scanner(settings: Settings) -> ContentScanner:
    if settings.feature_clamav:
        return ClamAVScanner(
            settings.clamav_host,
            settings.clamav_port,
            300 if settings.clamav_socket else 30,
            settings.clamav_socket,
        )
    return PolicyOnlyScanner()
