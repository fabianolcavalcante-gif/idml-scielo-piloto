"""One bounded service-only probe on the VPS: no article/institution query, no redirects."""

import argparse
import hashlib
import http.client
import ipaddress
import json
import socket
import ssl
import time
from datetime import datetime, timezone
from pathlib import Path

UTC = timezone.utc  # noqa: UP017 - host Python 3.10
ENDPOINT = "https://wayta.scielo.org/api/v1/institution"


def probe():
    start = time.monotonic()
    now = datetime.now(UTC).isoformat()
    result = {
        "contract_version": "wayta-service-observation-1.0",
        "endpoint": ENDPOINT,
        "observed_at": now,
        "outcome": "connection_error",
        "http_status": None,
        "response_sha256": None,
        "public_addresses": 0,
        "article_query_performed": False,
        "semantic_result_validated": False,
    }
    connection = None
    sock = None
    try:
        addresses = socket.getaddrinfo("wayta.scielo.org", 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
            result["outcome"] = "blocked_address"
        else:
            result["public_addresses"] = len({a[4][0] for a in addresses})
            sock = socket.create_connection((addresses[0][4][0], 443), timeout=8)
            connection = http.client.HTTPSConnection("wayta.scielo.org", timeout=8)
            connection.sock = ssl.create_default_context().wrap_socket(
                sock, server_hostname="wayta.scielo.org"
            )
            connection.request(
                "GET", "/api/v1/institution", headers={"User-Agent": "IDML-service-probe/1.0"}
            )
            response = connection.getresponse()
            raw = response.read(65537)
            if len(raw) > 65536:
                result["outcome"] = "response_too_large"
            else:
                result.update(
                    outcome="http_response",
                    http_status=response.status,
                    response_sha256=hashlib.sha256(raw).hexdigest(),
                )
    except socket.gaierror:
        result["outcome"] = "dns_error"
    except TimeoutError:
        result["outcome"] = "timeout"
    except ssl.SSLError:
        result["outcome"] = "tls_error"
    except (OSError, http.client.HTTPException):
        result["outcome"] = "connection_error"
    finally:
        if connection is not None:
            connection.close()
        if sock is not None:
            sock.close()
    result["elapsed_seconds"] = round(time.monotonic() - start, 3)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = {
        "probe_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "service_observation": probe(),
    }
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))
