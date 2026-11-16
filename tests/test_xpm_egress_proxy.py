import http.client
import json
import socket
import threading

import pytest

from ops.xpm_egress_proxy import Proxy, connect_host, public_address


@pytest.mark.parametrize("host", ["api.crossref.org", "orcid.org"])
def test_only_expected_tls_authorities(host):
    assert connect_host(host + ":443") == host


@pytest.mark.parametrize(
    "target",
    [
        "127.0.0.1:443",
        "169.254.169.254:443",
        "api.crossref.org:80",
        "example.com:443",
        "api.crossref.org.evil.test:443",
        "user@api.crossref.org:443",
        "orcid.org:443/path",
        "[::1]:443",
        "ORCID.ORG:443",
        "api.crossref.org:443\r\nX: y",
    ],
)
def test_other_destinations_denied(target):
    with pytest.raises(ValueError, match="destination_denied"):
        connect_host(target)


def answers(*addresses):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443)) for address in addresses]


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "172.18.0.1",
        "192.168.1.1",
        "169.254.169.254",
        "0.0.0.0",  # noqa: S104 - rejected DNS answer, never bound
        "::1",
        "fe80::1",
        "fc00::1",
        "::ffff:127.0.0.1",
    ],
)
def test_dns_private_results_denied(address):
    with pytest.raises(ValueError, match="non_public_address"):
        public_address("orcid.org", resolver=lambda *a, **k: answers(address))


def test_mixed_dns_results_do_not_allow_rebinding_to_internal_host():
    with pytest.raises(ValueError, match="non_public_address"):
        public_address("orcid.org", resolver=lambda *a, **k: answers("1.1.1.1", "10.0.0.1"))


def test_only_resolved_public_address_is_returned():
    assert public_address("orcid.org", resolver=lambda *a, **k: answers("1.1.1.1")) == "1.1.1.1"


def test_empty_dns_denied():
    with pytest.raises(ValueError, match="non_public_address"):
        public_address("orcid.org", resolver=lambda *a, **k: [])


@pytest.fixture
def proxy(tmp_path):
    server = Proxy("127.0.0.1", tmp_path, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


@pytest.mark.parametrize(
    "method,target",
    [
        ("CONNECT", "127.0.0.1:443"),
        ("CONNECT", "example.com:443"),
        ("GET", "http://static.scielo.org/sps/titles-tab-v2-utf-8.csv?secret=value"),
        ("GET", "http://localhost/"),
        ("GET", "http://wayta.scielo.org/api/v1/institution?q=secret=value"),
        ("POST", "http://api.crossref.org/works"),
    ],
)
def test_denials_are_real_http_responses_and_do_not_log_target(proxy, method, target):
    connection = http.client.HTTPConnection("127.0.0.1", proxy.server_port, timeout=2)
    try:
        connection.request(method, target)
        response = connection.getresponse()
        assert response.status == 403
        response.read()
    finally:
        connection.close()
    events = (proxy.output / "events.jsonl").read_text()
    assert target not in events and "secret=value" not in events
    assert json.loads(events)["event"] == "denied"
    if "wayta.scielo.org" in target:
        assert json.loads(events)["authority"] == "wayta"


def test_per_run_request_budget(proxy):
    assert all(proxy.admit("static.scielo.org") for _ in range(64))
    assert not proxy.admit("static.scielo.org")
