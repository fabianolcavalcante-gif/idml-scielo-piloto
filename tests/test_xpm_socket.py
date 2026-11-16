"""No vendor execution in unit tests; real qualification is recorded separately."""

import base64
import hashlib
import json
import socket
import struct
import time

import pytest

from idml_foundation.release.xpm_compatibility import IMAGE, TOOL_SHA256
from idml_foundation.services import xpm_socket as client
from ops import xpm_validator_broker as broker
from tests import test_xpm_execution as bridge_tests

inputs = bridge_tests.inputs
execution = bridge_tests.execution


def request(inputs):
    return dict(
        version="xpm-local-1.0",
        size=len(inputs["package"]),
        candidate_sha256=inputs["expected_scope"]["package_sha256"],
        scope=inputs["expected_scope"],
    )


def test_pins_and_valid_request(inputs):
    assert broker.IMAGE == IMAGE and broker.TOOL == TOOL_SHA256
    spec = broker.select_spec(dict(version="xpm-offline-1.0", image=IMAGE), request(inputs))
    assert spec["timeout_seconds"] == 190 and spec["scope"] == inputs["expected_scope"]


@pytest.mark.parametrize(
    "change",
    [
        dict(size=True),
        dict(size=0),
        dict(size=101 * 1024**2),
        dict(candidate_sha256="a" * 64),
        dict(version="evil"),
        dict(command="evil"),
        dict(scope={}),
        dict(image="evil"),
    ],
)
def test_request_rejects_untrusted_configuration(inputs, change):
    with pytest.raises(ValueError):
        broker.select_spec(dict(version="xpm-offline-1.0", image=IMAGE), request(inputs) | change)


def test_registry_cannot_select_another_image(inputs):
    with pytest.raises(ValueError):
        broker.select_spec(dict(version="xpm-offline-1.0", image="evil"), request(inputs))


class Connection:
    uid = 0

    def __init__(self, response):
        self.response = response
        self.sent = b""

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        pass

    def settimeout(self, value):
        assert value > 0

    def connect(self, _path):
        pass

    def getsockopt(self, *_args):
        return struct.pack("3i", 123, self.uid, 0)

    def sendall(self, value):
        self.sent += value

    def recv(self, size):
        result, self.response = self.response[:size], self.response[size:]
        return result


@pytest.mark.parametrize(
    "mutation",
    ["none", "peer", "scope", "hash", "base64", "budget", "truncated", "duplicate_report"],
)
def test_transport_boundaries(inputs, monkeypatch, tmp_path, mutation):
    evidence = execution(inputs["package"], inputs["expected_scope"])
    value = evidence.model_dump(mode="json", exclude={"report"})
    value["report_base64"] = base64.b64encode(evidence.report).decode()
    if mutation == "scope":
        value["scope"]["xml_sha256"] = "f" * 64
    if mutation == "hash":
        value["attestation"]["report_sha256"] = "f" * 64
    if mutation == "base64":
        value["report_base64"] = "***"
    if mutation == "duplicate_report":
        value["report"] = "private"
    raw = json.dumps(value).encode()
    wire = struct.pack("!I", client.MAX_RESPONSE + 1 if mutation == "budget" else len(raw))
    connection = Connection(wire + (raw[:10] if mutation == "truncated" else raw))
    connection.uid = 10001 if mutation == "peer" else 0
    monkeypatch.setattr(socket, "SO_PEERCRED", 17, raising=False)
    monkeypatch.setattr(socket, "AF_UNIX", 1, raising=False)
    monkeypatch.setattr(socket, "socket", lambda *_args: connection)
    executor = client.XpmSocketExecutor(tmp_path / "xpm.sock")
    if mutation == "none":
        assert executor(inputs["package"], inputs["expected_scope"]) == evidence
    else:
        with pytest.raises(ValueError):
            executor(inputs["package"], inputs["expected_scope"])
    if mutation == "peer":
        assert not connection.sent


def test_absolute_deadline():
    with pytest.raises(TimeoutError):
        client.receive(Connection(b"private"), 7, time.monotonic() - 1)


@pytest.mark.parametrize(
    "mutation",
    ["none", "hash", "traversal", "queries", "vendor", "input", "timeout", "multiple", "oversized"],
)
def test_report_sealing(inputs, tmp_path, mutation):
    runtime = tmp_path / "work"
    runtime.mkdir()
    report = b"private original HTML"
    (runtime / "xpm.html").write_bytes(report)
    record = dict(
        version="vh1-xpm-linux-case-1.0",
        archive_sha256=TOOL_SHA256,
        returncode=0,
        timed_out=False,
        network="none",
        external_queries_completed=False,
        input_unchanged=True,
        vendor_files_unchanged=True,
        reports={"xpm.html": dict(sha256=hashlib.sha256(report).hexdigest())},
    )
    if mutation == "hash":
        record["reports"]["xpm.html"]["sha256"] = "f" * 64
    if mutation == "traversal":
        record["reports"] = {"../xpm.html": {}}
    if mutation == "queries":
        record["external_queries_completed"] = True
    if mutation == "vendor":
        record["vendor_files_unchanged"] = False
    if mutation == "input":
        record["input_unchanged"] = False
    if mutation == "timeout":
        record["timed_out"] = True
    if mutation == "multiple":
        record["reports"]["other/xpm.html"] = {}
    if mutation == "oversized":
        (runtime / "xpm.html").write_bytes(b"x" * (8 * 1024**2 + 1))
    (runtime / "execution.json").write_text(json.dumps(record))
    if mutation == "none":
        result = json.loads(broker.envelope_from_execution(tmp_path, inputs["expected_scope"]))
        assert not result["required_queries_complete"]
        assert (tmp_path / "report.html").read_bytes() == report
        assert result["scope"] == inputs["expected_scope"]
    else:
        with pytest.raises(ValueError):
            broker.envelope_from_execution(tmp_path, inputs["expected_scope"])
        assert not (tmp_path / "report.html").exists()
