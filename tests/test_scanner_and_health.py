import socket

import pytest
from fastapi.testclient import TestClient

from idml_foundation.ingest.scanner import (
    ClamAVScanner,
    PolicyOnlyScanner,
    ScannerUnavailableError,
    build_scanner,
)
from idml_foundation.main import create_app
from idml_foundation.settings import Settings


class FakeClamAVConnection:
    def __init__(self, response: bytes) -> None:
        self.response = response
        self.sent: list[bytes] = []

    def __enter__(self) -> "FakeClamAVConnection":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def sendall(self, data: bytes | memoryview) -> None:
        self.sent.append(bytes(data))

    def recv(self, size: int) -> bytes:
        assert size == 4096
        return self.response


def test_scanner_factory_defaults_to_policy(settings: Settings) -> None:
    assert isinstance(build_scanner(settings), PolicyOnlyScanner)
    result = build_scanner(settings).scan(b"safe")
    assert result.clean
    assert result.status == "policy_only"


def test_scanner_factory_supports_clamav(settings: Settings) -> None:
    configured = settings.model_copy(update={"feature_clamav": True})
    assert isinstance(build_scanner(configured), ClamAVScanner)


@pytest.mark.parametrize(
    ("response", "clean", "status"),
    [
        (b"stream: OK\0", True, "clamav_clean"),
        (b"stream: Eicar-Signature FOUND\0", False, "malware_detected"),
    ],
)
def test_clamav_protocol_is_chunked_and_classified(
    monkeypatch: pytest.MonkeyPatch, response: bytes, clean: bool, status: str
) -> None:
    connection = FakeClamAVConnection(response)
    monkeypatch.setattr(socket, "create_connection", lambda *_args, **_kwargs: connection)
    result = ClamAVScanner("scanner", 3310).scan(b"payload")
    assert result.clean is clean
    assert result.status == status
    assert connection.sent[0] == b"zINSTREAM\0"
    assert connection.sent[-1] == b"\0\0\0\0"


def test_clamav_timeout_and_unknown_response_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def timeout(*_args: object, **_kwargs: object) -> None:
        raise TimeoutError("private endpoint detail")

    monkeypatch.setattr(socket, "create_connection", timeout)
    with pytest.raises(ScannerUnavailableError, match="scanner unavailable") as timeout_error:
        ClamAVScanner("scanner", 3310).scan(b"payload")
    assert "private endpoint" not in str(timeout_error.value)

    connection = FakeClamAVConnection(b"stream: UNKNOWN\0")
    monkeypatch.setattr(socket, "create_connection", lambda *_args, **_kwargs: connection)
    with pytest.raises(ScannerUnavailableError, match="indeterminate"):
        ClamAVScanner("scanner", 3310).scan(b"payload")


@pytest.mark.parametrize("reply", [b"stream: NOT OK\0", b"stream: OK", b"stream: OK\0garbage"])
def test_partial_or_misleading_clamav_reply_is_never_clean(monkeypatch, reply):
    chunks = iter((reply, b""))
    connection = FakeClamAVConnection(reply)
    monkeypatch.setattr(connection, "recv", lambda size: next(chunks))
    monkeypatch.setattr(socket, "create_connection", lambda *_args, **_kwargs: connection)
    with pytest.raises(ScannerUnavailableError):
        ClamAVScanner("scanner", 3310).scan(b"payload")


def test_scanner_unavailable_response_is_sanitized() -> None:
    app = create_app()

    @app.get("/test/scanner-unavailable")
    def scanner_failure() -> None:
        raise ScannerUnavailableError("private endpoint detail")

    with TestClient(app) as isolated_client:
        response = isolated_client.get("/test/scanner-unavailable")
    assert response.status_code == 503
    assert response.json() == {
        "detail": "content scanner unavailable",
        "code": "scanner_unavailable",
    }
    assert "private endpoint" not in response.text


def test_readiness_reports_redis_failure_without_leaking_details(client: TestClient) -> None:
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["checks"]["database"] == "ok"
    assert response.json()["checks"]["redis"] == "failed"
    assert "127.0.0.1" not in response.text


def test_metrics_endpoint(client: TestClient) -> None:
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "idml_http_requests_total" in response.text
