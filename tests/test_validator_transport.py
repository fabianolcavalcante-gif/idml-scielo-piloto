import copy
import hashlib
import json
import socket
import struct
from pathlib import Path

import pytest

from idml_foundation.release.validation_engine import ValidatorStatus
from idml_foundation.release.validator_registry import ValidatorChannel, load_validator_registry
from idml_foundation.services.validator_transport import LocalValidatorExecutor, receive
from ops.validator_broker import create_arguments, select_spec

REGISTRY_PATH = Path(__file__).parents[1] / "config/validator-registry-v1.json"


def request():
    registry = json.loads(REGISTRY_PATH.read_text())
    spec = next(
        s for s in registry["validators"] if s["name"] == "packtools" and s["channel"] == "active"
    )
    return registry, {
        "version": "local-validator-1.0",
        "name": "packtools",
        "size": 3,
        "candidate_sha256": hashlib.sha256(b"xml").hexdigest(),
        "tool_sha256": spec["image_id"].removeprefix("sha256:"),
        "validator_version": spec["version"],
        "profile_id": spec["profile_id"],
    }


def test_broker_uses_pinned_image_and_isolation():
    registry, req = request()
    spec = select_spec(registry, req)
    args = create_arguments(spec, Path("/private/input.xml"))
    assert spec["image_id"] in args
    for flag in (
        "--pull=never",
        "--network=none",
        "--read-only",
        "--cap-drop=ALL",
        "--memory=192m",
        "--memory-swap=192m",
        "--user=10001:10001",
    ):
        assert flag in args
    assert "/var/run/docker.sock" not in str(args)
    assert args[-1] == "/input/candidate.xml"


@pytest.mark.parametrize(
    "field,value",
    [
        ("name", "shell"),
        ("size", True),
        ("size", 0),
        ("size", 104857601),
        ("tool_sha256", "a" * 64),
        ("profile_id", "wrong"),
        ("validator_version", "wrong"),
        ("candidate_sha256", "../escape"),
        ("version", "other"),
    ],
)
def test_broker_rejects_untrusted_selection(field, value):
    registry, req = request()
    req[field] = value
    with pytest.raises(ValueError):
        select_spec(registry, req)


def test_broker_rejects_commands_and_duplicate_registration():
    registry, req = request()
    req["command"] = "anything"
    with pytest.raises(ValueError):
        select_spec(registry, req)
    del req["command"]
    registry["validators"].append(copy.deepcopy(select_spec(registry, req)))
    with pytest.raises(ValueError):
        select_spec(registry, req)


class FakeSocket:
    def __init__(self, data=b"", uid=0):
        self.data = data
        self.sent = bytearray()
        self.uid = uid

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def settimeout(self, value):
        pass

    def connect(self, value):
        pass

    def getsockopt(self, *args):
        return struct.pack("3i", 1, self.uid, self.uid)

    def sendall(self, data):
        self.sent.extend(data)

    def recv(self, size):
        block, self.data = self.data[: min(size, 3)], self.data[min(size, 3) :]
        return block


def spec():
    return (
        load_validator_registry(REGISTRY_PATH)
        .select("packtools", ValidatorChannel.ACTIVE)
        .command_specification()
    )


def test_transport_checks_bound_adapter_response(monkeypatch):
    specification = spec()
    envelope = json.dumps(
        {
            "adapter_contract": "1.1.0",
            "validator_name": "packtools",
            "validator_version": specification.version,
            "profile_id": specification.profile_id,
            "candidate_sha256": hashlib.sha256(b"xml").hexdigest(),
            "result": [],
        }
    ).encode()
    fake = FakeSocket(struct.pack("!I", len(envelope)) + envelope)
    monkeypatch.setattr(socket, "SO_PEERCRED", 17, raising=False)
    monkeypatch.setattr(socket, "AF_UNIX", 1, raising=False)
    monkeypatch.setattr(socket, "socket", lambda *args: fake)
    result = LocalValidatorExecutor(Path("/private/broker.sock"))(b"xml", specification)
    assert result.status == ValidatorStatus.COMPLETED
    assert fake.sent.endswith(b"xml")


@pytest.mark.parametrize("kind", ["truncated", "oversize", "untrusted"])
def test_transport_fails_closed(monkeypatch, kind):
    fake = FakeSocket(
        struct.pack("!I", 99999999) if kind == "oversize" else b"",
        uid=123 if kind == "untrusted" else 0,
    )
    monkeypatch.setattr(socket, "SO_PEERCRED", 17, raising=False)
    monkeypatch.setattr(socket, "AF_UNIX", 1, raising=False)
    monkeypatch.setattr(socket, "socket", lambda *args: fake)
    with pytest.raises(ValueError):
        LocalValidatorExecutor(Path("/private/broker.sock"))(b"xml", spec())


def test_receive_handles_fragmentation_and_eof():
    assert receive(FakeSocket(b"abcdef"), 6) == b"abcdef"
    with pytest.raises(ValueError):
        receive(FakeSocket(b"a"), 2)
