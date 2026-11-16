"""Root supervisor collection of fixed public APIs; no secrets, proxies or redirects."""

import hashlib
import http.client
import ipaddress
import json
import os
import socket
import ssl
import subprocess
import sys
import time
from datetime import datetime, timezone

from idml_foundation.services.xpm_query_targets import endpoint, query_targets

MAX_RESPONSE = 1024**2


def fetch(kind, identifier):
    host, path = endpoint(kind, identifier)
    addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise ValueError("authority_address_denied")
    address = addresses[0][4][0]
    connection = http.client.HTTPSConnection(host, timeout=8)
    try:
        raw = socket.create_connection((address, 443), timeout=8)
        try:
            connection.sock = ssl.create_default_context().wrap_socket(raw, server_hostname=host)
        except BaseException:
            raw.close()
            raise
        connection.request(
            "GET",
            path,
            headers={"Accept": "application/json", "User-Agent": "IDML-semantic-validation/1.0"},
        )
        response = connection.getresponse()
        if response.status != 200 or response.getheader("Content-Type", "").split(";")[0] not in {
            "application/json",
            "application/vnd.orcid+json",
        }:
            raise ValueError("authority_response_unavailable")
        payload = response.read(MAX_RESPONSE + 1)
        if not 0 < len(payload) <= MAX_RESPONSE:
            raise ValueError("authority_response_budget")
        json.loads(payload.decode("utf-8"))
        return payload
    finally:
        connection.close()


def collect(xml, scope, report_sha256, case):
    targets = query_targets(xml)
    receipts = []
    deadline = time.monotonic() + 70
    total = 0
    for target in targets:
        item = {k: target[k] for k in ("kind", "identifier")}
        host, path = endpoint(**item)
        receipt = dict(
            **item,
            url="https://" + host + path,
            status="unavailable",
            retrieved_at=datetime.now(timezone.utc).isoformat(),  # noqa: UP017
            response_sha256=None,
            payload=None,
        )
        remaining = deadline - time.monotonic()
        if remaining > 0:
            try:
                # Parent kills a stalled child, including DNS/TLS or slow body reads.
                result = subprocess.run(
                    [sys.executable, "-m", "ops.xpm_authority_collect", "--fetch"],
                    input=json.dumps(item).encode(),
                    capture_output=True,
                    timeout=min(15, remaining),
                    check=False,
                )
                if result.returncode or not 0 < len(result.stdout) <= MAX_RESPONSE:
                    raise ValueError("authority_unavailable")
                payload = result.stdout.decode("utf-8")
                json.loads(payload)
                total += len(result.stdout)
                if total > 2 * 1024**2:
                    raise ValueError("authority_total_budget")
                receipt.update(
                    status="available",
                    payload=payload,
                    response_sha256=hashlib.sha256(result.stdout).hexdigest(),
                )
            except (ValueError, OSError, subprocess.TimeoutExpired):
                pass  # Fixed unavailable outcome, never exception text or a fabricated response.
        receipts.append(receipt)
    evidence = dict(
        version="xpm-query-evidence-1.0",
        scope=scope,
        report_sha256=report_sha256,
        receipts=receipts,
    )
    with (case / "query-evidence.json").open("xb") as stream:
        os.chmod(case / "query-evidence.json", 0o600)
        stream.write(json.dumps(evidence).encode())
    return evidence


if __name__ == "__main__":
    try:
        if sys.argv[1:] != ["--fetch"]:
            raise ValueError("unsupported_operation")
        request = json.loads(sys.stdin.buffer.read(1025))
        if set(request) != {"kind", "identifier"}:
            raise ValueError("invalid_request")
        sys.stdout.buffer.write(fetch(**request))
    except Exception:
        raise SystemExit(
            1
        ) from None  # No identifiers, article contents or network details in logs.
