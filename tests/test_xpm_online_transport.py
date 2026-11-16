"""Failure injection for disposable resources; never contacts external authorities."""

import hashlib
import json

import pytest

from ops import xpm_online_transport as network
from ops import xpm_validator_broker as broker
from tests import test_xpm_execution as bridge_tests
from tests.test_xpm_socket import request

inputs = bridge_tests.inputs


def test_mode_is_only_administrator_selected(inputs):
    spec = broker.select_spec(dict(version="xpm-online-1.0", image=broker.IMAGE), request(inputs))
    assert spec["online"] is True
    for field in ("online", "proxy", "network", "endpoint"):
        with pytest.raises(ValueError):
            broker.select_spec(
                dict(version="xpm-online-1.0", image=broker.IMAGE),
                request(inputs) | {field: "untrusted"},
            )


@pytest.mark.parametrize(
    "failure",
    [
        "none",
        "create_network",
        "inspect",
        "not_internal",
        "create_proxy",
        "connect",
        "start",
        "create_probe",
        "probe",
        "denial",
        "integer_denial",
        "body",
        "remove_proxy",
        "remove_network",
        "missing_events",
    ],
)
def test_resources_cleaned_and_failures_never_sealed(tmp_path, monkeypatch, failure):
    calls = []
    monkeypatch.setattr(network.os, "chown", lambda *_args: None, raising=False)

    def command(*args):
        calls.append(args)
        action = ""
        result = ""
        if args[1:3] == ("network", "create"):
            action, result = "create_network", "net-id"
        elif args[1:3] == ("network", "inspect"):
            action, result = (
                "inspect",
                json.dumps(
                    [
                        dict(
                            Id="net-id",
                            Internal=failure != "not_internal",
                            IPAM=dict(Config=[dict(Subnet="172.30.0.0/24")]),
                        )
                    ]
                ),
            )
        elif args[1] == "create" and "/opt/xpm_egress_proxy.py" in args:
            action, result = "create_proxy", "proxy-id"
        elif args[1] == "create":
            action, result = "create_probe", "probe-id"
        elif args[1:3] == ("network", "connect"):
            action = "connect"
        elif args[1:3] == ("start", "proxy-id"):
            action = "start"
        elif args[1:3] == ("start", "-a"):
            action = "probe"
            result = json.dumps(
                [False] * 3
                if failure == "denial"
                else [1] * 3
                if failure == "integer_denial"
                else [True] * 3
            )
        elif args[1:3] == ("rm", "-f") and args[-1] == "proxy-id":
            action = "remove_proxy"
        elif args[1:3] == ("network", "rm"):
            action = "remove_network"
        if action == failure:
            raise RuntimeError("injected")
        return result

    monkeypatch.setattr(network.host, "command", command)

    def run():
        with network.online_network(tmp_path, broker.IMAGE) as (net, endpoint):
            assert net == "net-id" and endpoint == "http://172.30.0.2:8888"
            if failure != "missing_events":
                (tmp_path / "proxy/events.jsonl").write_bytes(b'{"event":"synthetic"}\n')
            if failure == "body":
                raise RuntimeError("validator failed")

    if failure == "none":
        run()
        proof = json.loads((tmp_path / "network-evidence.json").read_bytes())
        assert proof["ephemeral_resources_removed"] is True
        assert proof["semantic_queries_complete"] is False
    else:
        with pytest.raises((ValueError, RuntimeError)):
            run()
        assert not (tmp_path / "network-evidence.json").exists()
    if failure != "create_network":
        assert ("docker", "network", "rm", "net-id") in calls
    if failure not in {"create_network", "inspect", "not_internal", "create_proxy"}:
        assert ("docker", "rm", "-f", "proxy-id") in calls
    if failure not in {
        "create_network",
        "inspect",
        "not_internal",
        "create_proxy",
        "connect",
        "start",
        "create_probe",
    }:
        assert ("docker", "rm", "-f", "probe-id") in calls
    assert not any("--publish" in c or "-p" in c or "/var/run/docker.sock" in c for c in calls)


@pytest.mark.parametrize(
    "mutation", ["none", "network", "proof", "events", "image", "boundary", "semantic", "cleanup"]
)
def test_online_envelope_requires_sealed_network_proof(inputs, tmp_path, mutation):
    runtime = tmp_path / "work"
    runtime.mkdir()
    report = b"private HTML"
    (runtime / "xpm.html").write_bytes(report)
    record = dict(
        version="vh1-xpm-online-case-1.0",
        archive_sha256=broker.TOOL,
        returncode=0,
        timed_out=False,
        network="internal_bridge_via_allowlisted_proxy",
        input_unchanged=True,
        vendor_files_unchanged=True,
        reports={"xpm.html": dict(sha256=hashlib.sha256(report).hexdigest())},
    )
    events = b'{"event":"synthetic"}\n'
    proof = dict(
        version="xpm-supervised-network-1.0",
        image=broker.IMAGE,
        boundary_denials=[True] * 3,
        events_sha256=hashlib.sha256(events).hexdigest(),
        semantic_queries_complete=False,
        ephemeral_resources_removed=True,
    )
    if mutation == "network":
        record["network"] = "bridge"
    if mutation == "proof":
        proof["version"] = "unknown"
    if mutation == "events":
        events += b"tampered"
    if mutation == "image":
        proof["image"] = "unknown"
    if mutation == "boundary":
        proof["boundary_denials"] = [False] * 3
    if mutation == "semantic":
        proof["semantic_queries_complete"] = True
    if mutation == "cleanup":
        proof["ephemeral_resources_removed"] = False
    (runtime / "execution.json").write_text(json.dumps(record))
    (tmp_path / "network-evidence.json").write_text(json.dumps(proof))
    (tmp_path / "proxy-events.jsonl").write_bytes(events)
    if mutation == "none":
        result = json.loads(
            broker.envelope_from_execution(tmp_path, inputs["expected_scope"], online=True)
        )
        assert not result["required_queries_complete"]
        assert result["attestation"]["environment"] == "isolated-linux-supervised-online"
    else:
        with pytest.raises(ValueError):
            broker.envelope_from_execution(tmp_path, inputs["expected_scope"], online=True)
        assert not (tmp_path / "report.html").exists()
