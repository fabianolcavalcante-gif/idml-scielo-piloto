"""Ephemeral XPM lab proxy: three public authorities, no listening host port.

HTTPS stays end-to-end TLS: CONNECT bytes are not decrypted or called verification.
Only the legacy catalogue HTTP URL is upgraded to HTTPS, preserving response bytes.
This is qualification infrastructure, not a multi-tenant production proxy.
"""

import argparse
import hashlib
import http.client
import ipaddress
import json
import select
import socket
import ssl
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

CATALOGUE = "http://static.scielo.org/sps/titles-tab-v2-utf-8.csv"
TLS_HOSTS = frozenset({"api.crossref.org", "orcid.org"})
MAX_BYTES = 8 * 1024**2


def connect_host(authority):
    if authority not in {name + ":443" for name in TLS_HOSTS}:
        raise ValueError("destination_denied")
    return authority[:-4]


def public_address(host, resolver=socket.getaddrinfo):
    addresses = resolver(host, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError("non_public_address")
    return addresses[0][4][0]


class Proxy(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 4

    def __init__(self, bind, output, port=8888):
        self.output = output
        self.lock = threading.Lock()
        self.slots = threading.BoundedSemaphore(3)
        self.request_count = 0
        self.next_crossref = 0.0
        super().__init__((bind, port), Handler)

    def event(self, **data):
        with self.lock:
            with (self.output / "events.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({"at": time.time(), **data}) + "\n")

    def admit(self, host):
        with self.lock:
            self.request_count += 1
            if self.request_count > 64:
                return False
            delay = 0.0
            if host == "api.crossref.org":
                now = time.monotonic()
                delay = max(0.0, self.next_crossref - now)
                self.next_crossref = max(now, self.next_crossref) + 1.1
        if delay:
            time.sleep(delay)
        return True


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    timeout = 30

    def log_message(self, *_args):
        pass  # No URLs, headers, cookies or article metadata in access logs.

    def reject(self, reason, code=403, **labels):
        self.server.event(event="denied", reason=reason, **labels)
        self.send_error(code)

    def do_POST(self):
        self.reject("method_denied")

    def do_GET(self):
        if self.path != CATALOGUE or self.headers.get("Content-Length") not in (None, "0"):
            # Only a closed enum: never log arbitrary hostnames or institution query text.
            try:
                authority = (
                    "wayta" if urlsplit(self.path).hostname == "wayta.scielo.org" else "other"
                )
            except ValueError:
                authority = "other"
            self.reject("catalogue_url_denied", authority=authority)
            return
        if self.headers.get("Transfer-Encoding") or not self.server.admit("static.scielo.org"):
            self.reject("request_budget", 429)
            return
        connection = None
        try:
            host = "static.scielo.org"
            address = public_address(host)
            connection = http.client.HTTPSConnection(host, timeout=15)
            sock = socket.create_connection((address, 443), timeout=15)
            connection.sock = ssl.create_default_context().wrap_socket(sock, server_hostname=host)
            connection.request(
                "GET",
                "/sps/titles-tab-v2-utf-8.csv",
                headers={
                    "Accept": "text/plain",
                    "User-Agent": "IDML-XPM-qualification/1.0",
                },
            )
            response = connection.getresponse()
            body = response.read(MAX_BYTES + 1)
            if response.status != 200 or not 0 < len(body) <= MAX_BYTES:
                raise ValueError("catalogue_response_invalid")
            # Preserve the entire official catalogue, not a row assembled from the candidate.
            (self.server.output / "catalogue.csv").write_bytes(body)
            self.server.event(
                event="catalogue_https_response",
                status=200,
                bytes=len(body),
                sha256=hashlib.sha256(body).hexdigest(),
                last_modified=response.getheader("Last-Modified"),
            )
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (OSError, ValueError, http.client.HTTPException) as error:
            self.server.event(event="catalogue_failed", error_type=type(error).__name__)
            self.send_error(502)
        finally:
            if connection:
                connection.close()

    def do_CONNECT(self):
        try:
            host = connect_host(self.path)
            if self.headers.get("Transfer-Encoding") or self.headers.get("Content-Length") not in (
                None,
                "0",
            ):
                raise ValueError("request_body_denied")
            address = public_address(host)
        except (ValueError, OSError):
            self.reject("connect_destination_denied")
            return
        if not self.server.admit(host) or not self.server.slots.acquire(blocking=False):
            self.reject("connection_budget", 429)
            return
        sent = received = 0
        reason = "closed"
        upstream = None
        try:
            upstream = socket.create_connection((address, 443), timeout=15)
            self.send_response(200, "Connection Established")
            self.end_headers()
            self.wfile.flush()
            deadline = time.monotonic() + 35
            while time.monotonic() < deadline:
                readable, _, _ = select.select([upstream, self.connection], [], [], 1)
                if not readable:
                    continue
                for source in readable:
                    data = source.recv(65536)
                    if not data:
                        return
                    if source is upstream:
                        received += len(data)
                        destination = self.connection
                    else:
                        sent += len(data)
                        destination = upstream
                    if sent + received > MAX_BYTES:
                        reason = "byte_budget"
                        return
                    destination.sendall(data)
            reason = "time_budget"
        except OSError as error:
            reason = type(error).__name__
        finally:
            if upstream:
                upstream.close()
            self.server.slots.release()
            self.close_connection = True
            self.server.event(
                event="tls_tunnel", host=host, sent=sent, received=received, result=reason
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", required=True)
    parser.add_argument("--output", type=Path, default=Path("/evidence"))
    args = parser.parse_args()
    bind = ipaddress.ip_address(args.bind)
    if not bind.is_private or bind.is_loopback or bind.is_unspecified:
        raise ValueError("internal_bridge_binding_required")
    Proxy(str(bind), args.output).serve_forever(poll_interval=0.2)
