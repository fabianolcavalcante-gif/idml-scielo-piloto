"""Disposable administrator-owned network for the pinned XPM online wrapper."""

import hashlib
import ipaddress
import json
import os
from contextlib import contextmanager
from uuid import uuid4

from ops import validator_broker as host


def proxy_arguments(image, network, address, evidence):
    return [
        "docker",
        "create",
        "--pull=never",
        "--network",
        network,
        "--ip",
        address,
        "--read-only",
        "--user=65534:65534",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--memory=96m",
        "--memory-swap=96m",
        "--cpus=0.25",
        "--pids-limit=32",
        "--log-driver=none",
        "--entrypoint=python",
        "--mount",
        f"type=bind,src={evidence},dst=/evidence",
        image,
        "/opt/xpm_egress_proxy.py",
        "--bind",
        address,
    ]


def probe_arguments(image, network, address):
    # Fixed negative controls; no article identifiers, arbitrary host or user script.
    code = (
        "import http.client,json,time\ntime.sleep(0.5)\nresults=[]\n"
        "for target in ['127.0.0.1','169.254.169.254','example.com']:\n"
        f" c=http.client.HTTPConnection('{address}',8888,timeout=3)\n"
        " c.set_tunnel(target,443)\n"
        " try: c.connect(); results.append(False)\n"
        " except OSError as e: results.append('403' in str(e))\n"
        " finally: c.close()\n"
        "print(json.dumps(results))\n"
    )
    return [
        "docker",
        "create",
        "--pull=never",
        "--network",
        network,
        "--read-only",
        "--user=65534:65534",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--memory=64m",
        "--memory-swap=64m",
        "--cpus=0.25",
        "--pids-limit=16",
        "--log-driver=none",
        "--entrypoint=python",
        image,
        "-c",
        code,
    ]


@contextmanager
def online_network(case, image):
    """Cleanup owns exact created IDs only; no existing application network is modified."""
    evidence = case / "proxy"
    evidence.mkdir(mode=0o700)
    os.chown(evidence, 65534, 65534)
    network = proxy = None
    try:
        network = host.command(
            "docker",
            "network",
            "create",
            "--internal",
            "--label",
            "idml.purpose=xpm-supervised",
            "idml-xpm-" + uuid4().hex,
        )
        info = json.loads(host.command("docker", "network", "inspect", network))[0]
        if info["Internal"] is not True or info["Id"] != network:
            raise ValueError("xpm_private_network_required")
        address = str(ipaddress.ip_network(info["IPAM"]["Config"][0]["Subnet"])[2])
        proxy = host.command(*proxy_arguments(image, network, address, evidence))
        host.command("docker", "network", "connect", "bridge", proxy)
        host.command("docker", "start", proxy)
        probe = host.command(*probe_arguments(image, network, address))
        try:
            boundary = json.loads(host.command("docker", "start", "-a", probe))
        finally:
            host.command("docker", "rm", "-f", probe)
        if (
            not isinstance(boundary, list)
            or len(boundary) != 3
            or any(value is not True for value in boundary)
        ):
            raise ValueError("xpm_egress_boundary_failed")
        yield network, "http://" + address + ":8888"
    finally:
        # Stop writer before sealing evidence. Cleanup failures cannot yield success.
        try:
            if proxy:
                host.command("docker", "rm", "-f", proxy)
        finally:
            if network:
                host.command("docker", "network", "rm", network)
    events = evidence / "events.jsonl"
    if events.is_symlink() or not events.is_file() or not 0 < events.stat().st_size <= 1024**2:
        raise ValueError("xpm_proxy_evidence_invalid")
    payload = events.read_bytes()
    proof = dict(
        version="xpm-supervised-network-1.0",
        image=image,
        boundary_denials=boundary,
        events_sha256=hashlib.sha256(payload).hexdigest(),
        semantic_queries_complete=False,
        ephemeral_resources_removed=True,
    )
    for name, data in (
        ("proxy-events.jsonl", payload),
        ("network-evidence.json", json.dumps(proof).encode()),
    ):
        with (case / name).open("xb") as stream:
            os.chmod(case / name, 0o600)
            stream.write(data)
