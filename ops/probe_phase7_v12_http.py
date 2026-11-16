"""Real loopback HTTP probe of bounded multipart only; no database/provider."""

import hashlib
import http.client
import json
import resource
import socket
import subprocess
import sys
import time
from typing import Annotated

from fastapi import Depends, FastAPI
from starlette import formparsers
from starlette.datastructures import UploadFile

from idml_foundation.ingest.http_upload import bounded_upload

app = FastAPI()
OPENED = []
ORIGINAL = formparsers.SpooledTemporaryFile


def tracked(*args, **kwargs):
    file = ORIGINAL(*args, **kwargs)
    OPENED.append(file)
    return file


formparsers.SpooledTemporaryFile = tracked


@app.post("/probe")
async def probe(upload: Annotated[UploadFile, Depends(bounded_upload)]):
    digest = hashlib.sha256()
    count = 0
    while block := await upload.read(65536):
        digest.update(block)
        count += len(block)
    return {"bytes": count, "sha256": digest.hexdigest()}


@app.get("/stats")
def stats():
    return {
        "open_files": sum(not f.closed for f in OPENED),
        "rolled_files": sum(bool(f._rolled) for f in OPENED),
        "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
    }


PREFIX = (
    b'--v12boundary\r\nContent-Disposition: form-data; name="upload"; '
    b'filename="synthetic.bin"\r\nContent-Type: application/octet-stream\r\n\r\n'
)
SUFFIX = b"\r\n--v12boundary--\r\n"


def parts(size):
    yield PREFIX
    remaining = size
    while remaining:
        count = min(remaining, 65536)
        yield b"x" * count
        remaining -= count
    yield SUFFIX


def send(size, chunked=False):
    connection = http.client.HTTPConnection("127.0.0.1", 8000, timeout=30)
    headers = {"Content-Type": "multipart/form-data; boundary=v12boundary"}
    if not chunked:
        headers["Content-Length"] = str(len(PREFIX) + size + len(SUFFIX))
    started = time.monotonic()
    try:
        connection.request(
            "POST", "/probe", body=parts(size), headers=headers, encode_chunked=chunked
        )
        response = connection.getresponse()
        return response.status, json.loads(response.read()), round(time.monotonic() - started, 3)
    finally:
        connection.close()


def get_stats():
    connection = http.client.HTTPConnection("127.0.0.1", 8000, timeout=5)
    try:
        connection.request("GET", "/stats")
        response = connection.getresponse()
        return json.loads(response.read())
    finally:
        connection.close()


def main():
    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "ops.probe_phase7_v12_http:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
            "--no-access-log",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    results = []
    try:
        for _ in range(80):
            try:
                get_stats()
                break
            except OSError:
                time.sleep(0.25)
        else:
            raise RuntimeError("probe server unavailable")
        for size, chunked in ((2 * 1024**2, False), (100 * 1024**2, False), (100 * 1024**2, True)):
            status, body, elapsed = send(size, chunked)
            digest = hashlib.sha256()
            for _ in range(size // 65536):
                digest.update(b"x" * 65536)
            state = get_stats()
            results.append(
                {
                    "case": f"{size}-{'chunked' if chunked else 'declared'}",
                    "approved": status == 200
                    and body.get("bytes") == size
                    and body.get("sha256") == digest.hexdigest()
                    and state["open_files"] == 0,
                    "status": status,
                    "elapsed_seconds": elapsed,
                    "stats": state,
                }
            )
        # Disconnect after the parser has rolled its file to disk.
        with socket.create_connection(("127.0.0.1", 8000), timeout=10) as client:
            client.sendall(
                b"POST /probe HTTP/1.1\r\nHost: localhost\r\nContent-Length: 104857600\r\n"
                b"Content-Type: multipart/form-data; boundary=v12boundary\r\n\r\n"
            )
            client.sendall(PREFIX)
            for _ in range(32):
                client.sendall(b"x" * 65536)
        for _ in range(40):
            state = get_stats()
            if state["open_files"] == 0 and state["rolled_files"] >= 4:
                break
            time.sleep(0.1)
        results.append(
            {
                "case": "disconnect",
                "approved": state["open_files"] == 0 and state["rolled_files"] >= 4,
                "stats": state,
            }
        )
        # Header-only rejection must not read or spool the advertised body.
        connection = http.client.HTTPConnection("127.0.0.1", 8000, timeout=5)
        connection.request(
            "POST",
            "/probe",
            body=None,
            headers={
                "Content-Length": str(101 * 1024**2),
                "Content-Type": "multipart/form-data; boundary=v12boundary",
            },
        )
        response = connection.getresponse()
        response.read()
        results.append(
            {
                "case": "oversized_declared",
                "approved": response.status == 413,
                "status": response.status,
            }
        )
        connection.close()
        # Keep one upload open, prove rejection of the second, then wait for
        # idle timeout and prove that the slot and temporary file are released.
        with socket.create_connection(("127.0.0.1", 8000), timeout=10) as slow:
            slow.sendall(
                b"POST /probe HTTP/1.1\r\nHost: localhost\r\nContent-Length: 104857600\r\n"
                b"Content-Type: multipart/form-data; boundary=v12boundary\r\n\r\n" + PREFIX
            )
            for _ in range(32):
                slow.sendall(b"x" * 65536)
            for _ in range(20):
                if get_stats()["open_files"] == 1:
                    break
                time.sleep(0.05)
            busy, _, _ = send(1)
            reply = http.client.HTTPResponse(slow)
            reply.begin()
            reply.read()
            idle = reply.status
        state = get_stats()
        recovered, _, _ = send(65536)
        admission_cases = {
            "busy_status": busy,
            "idle_status": idle,
            "recovery_status": recovered,
            "open_files_after_timeout": state["open_files"],
            "approved": busy == 503
            and idle == 408
            and recovered == 200
            and state["open_files"] == 0,
        }
        result = {
            "version": "phase7-v12-http-probe-1.0",
            "approved": all(r["approved"] for r in results) and admission_cases["approved"],
            "admission": admission_cases,
            "cases": results,
            "provider_calls": 0,
            "restricted_content_emitted": False,
            "scope": "multipart reception only, not artifact persistence or XML conversion",
            "release_ready": False,
        }
        print(json.dumps(result), flush=True)
        return 0 if result["approved"] else 2
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(
            json.dumps(
                {
                    "approved": False,
                    "error": type(exc).__name__,
                    "restricted_content_emitted": False,
                }
            ),
            flush=True,
        )
        raise SystemExit(2) from None
