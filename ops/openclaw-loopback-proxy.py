#!/usr/bin/env python3
"""Expose one authenticated OpenClaw endpoint only through an SSH loopback tunnel."""

from __future__ import annotations

import argparse
import http.client
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MAX_REQUEST_BYTES = 16 * 1024 * 1024
MAX_RESPONSE_BYTES = 16 * 1024 * 1024


class _ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "IDMLOpenClawLoopback/1.0"

    def do_POST(self) -> None:
        if self.path != "/v1/responses":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            self.send_error(400)
            return
        if not 0 < length <= MAX_REQUEST_BYTES:
            self.send_error(413)
            return
        body = self.rfile.read(length)
        server = self.server
        assert isinstance(server, OpenClawLoopbackServer)
        headers = {
            name: value
            for name, value in self.headers.items()
            if name.casefold()
            not in {
                "authorization",
                "connection",
                "content-length",
                "host",
                "proxy-authorization",
                "transfer-encoding",
            }
        }
        headers["Authorization"] = f"Bearer {server.gateway_token}"
        headers["Content-Length"] = str(len(body))
        connection = http.client.HTTPConnection(
            server.upstream_host,
            server.upstream_port,
            timeout=server.timeout_seconds,
        )
        try:
            connection.request("POST", self.path, body=body, headers=headers)
            response = connection.getresponse()
            response_body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(response_body) > MAX_RESPONSE_BYTES:
                self.send_error(502)
                return
            self.send_response(response.status)
            content_type = response.getheader("Content-Type")
            if content_type:
                self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(response_body)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(response_body)
        except (OSError, http.client.HTTPException):
            self.send_error(502)
        finally:
            connection.close()

    def log_message(self, format: str, *args: object) -> None:
        del format, args


class OpenClawLoopbackServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(
        self,
        *,
        listen_port: int,
        upstream_host: str,
        upstream_port: int,
        gateway_token: str,
        timeout_seconds: int,
    ) -> None:
        self.upstream_host = upstream_host
        self.upstream_port = upstream_port
        self.gateway_token = gateway_token
        self.timeout_seconds = timeout_seconds
        super().__init__(("127.0.0.1", listen_port), _ProxyHandler)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--listen-port", type=int, required=True)
    parser.add_argument("--upstream-host", required=True)
    parser.add_argument("--upstream-port", type=int, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=60)
    args = parser.parse_args()
    token = os.environ.get("IDML_OPENCLAW_GATEWAY_TOKEN", "")
    if len(token) < 32:
        raise SystemExit("IDML_OPENCLAW_GATEWAY_TOKEN is unavailable")
    if not 1024 <= args.listen_port <= 65535 or not 1 <= args.upstream_port <= 65535:
        raise SystemExit("proxy port is outside the allowed range")
    if not 1 <= args.timeout_seconds <= 120:
        raise SystemExit("proxy timeout is outside the allowed range")
    server = OpenClawLoopbackServer(
        listen_port=args.listen_port,
        upstream_host=args.upstream_host,
        upstream_port=args.upstream_port,
        gateway_token=token,
        timeout_seconds=args.timeout_seconds,
    )
    try:
        server.serve_forever(poll_interval=0.2)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
