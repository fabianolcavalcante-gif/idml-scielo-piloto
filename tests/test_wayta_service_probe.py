import hashlib
import socket
import ssl
from unittest.mock import Mock

import pytest

from ops import probe_wayta_https as module


def dns(address="200.136.72.163"):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))]


@pytest.mark.parametrize("address", ["127.0.0.1", "10.1.1.1", "169.254.169.254", "::1"])
def test_private_addresses_never_connected(monkeypatch, address):
    monkeypatch.setattr(module.socket, "getaddrinfo", lambda *a, **k: dns(address))
    connection = Mock()
    monkeypatch.setattr(module.socket, "create_connection", connection)
    assert module.probe()["outcome"] == "blocked_address"
    connection.assert_not_called()


def test_mixed_public_and_private_dns_fails_closed(monkeypatch):
    monkeypatch.setattr(module.socket, "getaddrinfo", lambda *a, **k: dns() + dns("127.0.0.1"))
    assert module.probe()["outcome"] == "blocked_address"


@pytest.mark.parametrize(
    "error,outcome",
    [
        (socket.gaierror(), "dns_error"),
        (TimeoutError(), "timeout"),
        (ssl.SSLError(), "tls_error"),
        (ConnectionRefusedError(), "connection_error"),
    ],
)
def test_transport_failures_are_not_success(monkeypatch, error, outcome):
    resolve = Mock(return_value=dns())
    connect = Mock(side_effect=error)
    if outcome == "dns_error":
        resolve.side_effect = error
    monkeypatch.setattr(module.socket, "getaddrinfo", resolve)
    monkeypatch.setattr(module.socket, "create_connection", connect)
    result = module.probe()
    assert result["outcome"] == outcome and result["http_status"] is None
    assert result["response_sha256"] is None and not result["article_query_performed"]


@pytest.mark.parametrize(
    "status,size", [(200, 0), (302, 10), (429, 100), (500, 65536), (200, 65537)]
)
def test_single_tls_request_without_article_query_redirect_or_unbounded_body(
    monkeypatch, status, size
):
    monkeypatch.setattr(module.socket, "getaddrinfo", lambda *a, **k: dns())
    sock = Mock()
    connect = Mock(return_value=sock)
    monkeypatch.setattr(module.socket, "create_connection", connect)
    context = Mock()
    monkeypatch.setattr(module.ssl, "create_default_context", lambda: context)
    response = Mock(status=status)
    raw = b"a" * size
    response.read.return_value = raw
    connection = Mock()
    connection.getresponse.return_value = response
    monkeypatch.setattr(module.http.client, "HTTPSConnection", Mock(return_value=connection))
    result = module.probe()
    connect.assert_called_once_with(("200.136.72.163", 443), timeout=8)
    context.wrap_socket.assert_called_once_with(sock, server_hostname="wayta.scielo.org")
    connection.request.assert_called_once_with(
        "GET",
        "/api/v1/institution",
        headers={"User-Agent": "IDML-service-probe/1.0"},
    )
    response.read.assert_called_once_with(65537)
    connection.close.assert_called_once()
    sock.close.assert_called_once()
    assert not result["semantic_result_validated"] and not result["article_query_performed"]
    assert result["outcome"] == ("http_response" if size <= 65536 else "response_too_large")
    assert result["response_sha256"] == (hashlib.sha256(raw).hexdigest() if size <= 65536 else None)
    assert "body" not in result
