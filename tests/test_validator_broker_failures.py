"""Deterministic fault injection; no Docker, host resource exhaustion or private inputs."""

import io
import json
import struct
from pathlib import Path
from types import SimpleNamespace

import pytest

from ops import validator_broker as broker
from tests.test_validator_transport import FakeSocket, request


@pytest.mark.parametrize(
    "kind", ["unauthorized", "header", "truncated", "digest", "executor", "send"]
)
def test_request_failure_cleans_private_input(monkeypatch, tmp_path, kind):
    registry, header = request()
    if kind == "digest":
        header["candidate_sha256"] = "0" * 64
    payload = json.dumps(header).encode()
    wire = struct.pack("!I", len(payload)) + payload + b"xml"
    if kind == "header":
        wire = struct.pack("!I", 2049)
    if kind == "truncated":
        wire = wire[:-1]
    connection = FakeSocket(wire, uid=7 if kind == "unauthorized" else 10001)
    monkeypatch.setattr(broker.socket, "SO_PEERCRED", 17, raising=False)
    monkeypatch.setattr(broker, "reserve", lambda *a, **k: None)
    calls = []

    def execute(spec, candidate, work):
        calls.append(candidate)
        assert candidate.read_bytes() == b"xml"
        if kind == "executor":
            raise RuntimeError("validator_timeout")
        return b"{}"

    def disconnected(data):
        raise BrokenPipeError("synthetic disconnect")

    monkeypatch.setattr(broker, "execute", execute)
    if kind == "send":
        connection.sendall = disconnected
    with pytest.raises((ValueError, RuntimeError, BrokenPipeError)):
        broker.handle(connection, registry, tmp_path, 10001)
    assert not list(tmp_path.iterdir())
    assert bool(calls) == (kind in {"executor", "send"})


@pytest.mark.parametrize(
    "starting,memory,free,error",
    [
        (True, 767, 10, "memory_reserve"),
        (False, 511, 10, "memory_reserve"),
        (True, 800, 5, "disk_reserve"),
        (True, 768, 6, None),
        (False, 512, 6, None),
    ],
)
def test_resource_admission(monkeypatch, tmp_path, starting, memory, free, error):
    monkeypatch.setattr(Path, "read_text", lambda *a, **k: f"MemAvailable: {memory * 1024} kB")
    monkeypatch.setattr(broker.shutil, "disk_usage", lambda p: SimpleNamespace(free=free * 1024**3))
    if error:
        with pytest.raises(RuntimeError, match=error):
            broker.reserve(tmp_path, starting=starting)
    else:
        broker.reserve(tmp_path, starting=starting)


def test_expired_receive_does_not_extend_deadline(monkeypatch):
    monkeypatch.setattr(broker.time, "monotonic", lambda: 1)
    with pytest.raises(TimeoutError, match="receive_deadline"):
        broker.receive(FakeSocket(b"a"), 1, deadline=0)


@pytest.mark.parametrize(
    "failure", ["timeout", "output", "oom", "exit", "reserve", "remove", "success"]
)
def test_execution_cleanup(monkeypatch, tmp_path, failure):
    registry, header = request()
    spec = broker.select_spec(registry, header)
    commands = []
    stream = io.BytesIO()
    process = SimpleNamespace(stdout=stream, returncode=0, killed=False)
    process.poll = lambda: None
    process.wait = lambda **k: 0
    process.kill = lambda: setattr(process, "killed", True)

    def command(*args):
        commands.append(args)
        if args[:3] == ("docker", "image", "inspect"):
            return spec["image_id"]
        if args[:2] == ("docker", "create"):
            return "synthetic-container-id"
        if args[:2] == ("docker", "rm"):
            if failure == "remove":
                raise RuntimeError("container_command_failed")
            return ""
        return json.dumps(
            {"ExitCode": int(failure == "exit"), "OOMKilled": failure == "oom", "Running": False}
        )

    class Selector:
        active = True

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def register(self, *args):
            pass

        def unregister(self, *args):
            self.active = False

        def get_map(self):
            return self.active

        def select(self, **kwargs):
            return [(SimpleNamespace(fileobj=SimpleNamespace(fileno=lambda: 9)), None)]

    def reserve(work, *, starting=False):
        if failure == "reserve" and not starting:
            raise RuntimeError("memory_reserve")

    clock = iter([0, spec["timeout_seconds"] + 1] if failure == "timeout" else [0, 0])
    monkeypatch.setattr(broker, "reserve", reserve)
    monkeypatch.setattr(broker, "command", command)
    monkeypatch.setattr(broker.subprocess, "Popen", lambda *a, **k: process)
    monkeypatch.setattr(broker.selectors, "DefaultSelector", Selector)
    monkeypatch.setattr(broker.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(
        broker.os,
        "read",
        lambda *a: b"x" * (spec["max_output_bytes"] + 1) if failure == "output" else b"",
    )
    if failure == "success":
        assert broker.execute(spec, tmp_path / "input.xml", tmp_path) == b""
    else:
        with pytest.raises(RuntimeError):
            broker.execute(spec, tmp_path / "input.xml", tmp_path)
    assert commands[-1] == ("docker", "rm", "-f", "synthetic-container-id")
    assert process.killed and stream.closed
