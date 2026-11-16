"""Run bounded real XPM queries through a disposable private bridge/proxy on the VPS."""

import argparse
import ipaddress
import json
import os
import re
import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile

from qualify_vh1_xpm_linux import (
    BASELINE,
    PACKAGES,
    ROOT,
    checked_members,
    command,
    digest,
    docker_arguments,
    health,
    mutate,
)

UTC = timezone.utc  # noqa: UP017 - VPS host Python 3.10
MATRIX = [(name, "baseline") for name in PACKAGES] + [("esa-e20240086", "missing_graphic")]


def prepare_case(destination, article, mutation):
    candidate = BASELINE / article / "candidate.zip"
    if candidate.is_symlink() or digest(candidate) != PACKAGES[article]:
        raise ValueError("pinned_candidate_required")
    with ZipFile(candidate) as archive:
        members = mutate(checked_members(archive), mutation)
    case = destination / (article + "-" + mutation)
    case.mkdir()
    for name in ("input", "work"):
        (case / name).mkdir(mode=0o700)
        os.chown(case / name, 65534, 65534)
    for name, data in members.items():
        target = case / "input" / name
        target.write_bytes(data)
        os.chown(target, 65534, 65534)
        os.chmod(target, 0o400)
    return case


def export_evidence(destination):
    paths = [destination / "report.json", destination / "proxy/events.jsonl"]
    if (destination / "proxy/catalogue.csv").is_file():
        paths.append(destination / "proxy/catalogue.csv")
    for case in destination.glob("esa-*"):
        for name in ("execution.json", "stdout.log", "stderr.log"):
            path = case / "work" / name
            if path.is_file():
                paths.append(path)
        paths.extend((case / "work").rglob("xpm.html"))
        # Keep exact input/output XML for private delta analysis, never public reports.
        paths.extend((case / "input").glob("*.xml"))
        paths.extend((case / "work/input_xpm/scielo_package").glob("*.xml"))
    with (destination / "evidence.tar.gz").open("xb") as output:
        with tarfile.open(fileobj=output, mode="w:gz") as archive:
            for path in paths:
                if path.is_symlink() or path.resolve().parent != path.parent.resolve():
                    raise ValueError("evidence_symlink_denied")
                archive.add(path, arcname=path.relative_to(destination).as_posix(), recursive=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", args.image):
        raise ValueError("immutable_image_required")
    os.umask(0o077)
    if ROOT.resolve() != ROOT or not ROOT.is_dir():
        raise ValueError("unexpected_root")
    before = health()
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    destination = ROOT / ("vh1-xpm-online-" + run_id)
    destination.mkdir(mode=0o700)
    evidence = destination / "proxy"
    evidence.mkdir(mode=0o700)
    os.chown(evidence, 65534, 65534)
    network, proxy_name = "idml-xpm-net-" + run_id.lower(), "idml-xpm-proxy-" + run_id.lower()
    cases, boundary = [], None
    network_created = proxy_created = False
    try:
        command(["docker", "network", "create", "--internal", "--label", "idml.lab=xpm", network])
        network_created = True
        net = json.loads(command(["docker", "network", "inspect", network]))[0]
        if not net["Internal"]:
            raise ValueError("internal_network_required")
        proxy_ip = str(ipaddress.ip_network(net["IPAM"]["Config"][0]["Subnet"])[2])
        command(
            [
                "docker",
                "create",
                "--name",
                proxy_name,
                "--network",
                network,
                "--ip",
                proxy_ip,
                "--read-only",
                "--user=65534:65534",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges",
                "--memory=96m",
                "--memory-swap=96m",
                "--cpus=0.25",
                "--pids-limit=32",
                "--entrypoint",
                "python",
                "--mount",
                "type=bind,src=" + str(evidence) + ",dst=/evidence",
                args.image,
                "/opt/xpm_egress_proxy.py",
                "--bind",
                proxy_ip,
            ]
        )
        proxy_created = True
        command(["docker", "network", "connect", "bridge", proxy_name])
        command(["docker", "start", proxy_name])
        # Give the private proxy a TCP readiness check from a disposable peer, then test denials.
        probe = (
            "import http.client,json,time; time.sleep(0.5); results=[]; "
            "exec(\"for target in ['127.0.0.1:443','169.254.169.254:443','example.com:443']:\\n"
            " c=http.client.HTTPConnection('" + proxy_ip + "',8888,timeout=5); "
            "c.set_tunnel(target.split(':')[0],443)\\n"
            " try: c.connect(); results.append(False)\\n"
            " except OSError as e: results.append('403' in str(e))\\n"
            ' finally: c.close()"); print(json.dumps(results)); assert all(results)'
        )
        boundary = json.loads(
            command(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--network",
                    network,
                    "--read-only",
                    "--cap-drop=ALL",
                    "--security-opt=no-new-privileges",
                    "--memory=64m",
                    "--pids-limit=16",
                    "--entrypoint",
                    "python",
                    args.image,
                    "-c",
                    probe,
                ]
            )
        )
        for index, (article, mutation) in enumerate(MATRIX):
            case = prepare_case(destination, article, mutation)
            name = "idml-xpm-online-" + run_id.lower() + "-" + str(index)
            cmd = docker_arguments(args.image, name, case / "input", case / "work")
            cmd[cmd.index("--network=none")] = "--network=" + network
            endpoint = "http://" + proxy_ip + ":8888"
            cmd[-1:-1] = [
                "--env",
                "http_proxy=" + endpoint,
                "--env",
                "https_proxy=" + endpoint,
                "--env",
                "no_proxy=",
            ]
            try:
                with (case / "container.log").open("wb") as output:
                    try:
                        result = subprocess.run(  # noqa: S603 - fixed bounded container args
                            cmd, stdout=output, stderr=subprocess.STDOUT, timeout=195, check=False
                        )
                        exit_code = result.returncode
                    except subprocess.TimeoutExpired:
                        exit_code = None
                        command(["docker", "stop", "-t", "3", name])
                state = json.loads(command(["docker", "inspect", name]))[0]
                record_path = case / "work/execution.json"
                execution = json.loads(record_path.read_text()) if record_path.is_file() else None
                item = {
                    "article": article,
                    "mutation": mutation,
                    "original_package_sha256": PACKAGES[article],
                    "docker_exit_code": exit_code,
                    "oom_killed": state["State"]["OOMKilled"],
                    "actual_image": state["Image"],
                    "actual_network": state["HostConfig"]["NetworkMode"],
                    "execution": execution,
                    "execution_sha256": digest(record_path) if execution else None,
                }
                cases.append(item)
                print(
                    json.dumps(
                        {
                            "case": case.name,
                            "exit_code": exit_code,
                            "reports": execution["reports"] if execution else None,
                        }
                    ),
                    flush=True,
                )
            finally:
                command(["docker", "rm", "-f", name])
            if digest(BASELINE / article / "candidate.zip") != PACKAGES[article]:
                raise ValueError("source_changed")
    finally:
        if proxy_created:
            command(["docker", "rm", "-f", proxy_name])
        if network_created:
            command(["docker", "network", "rm", network])
        after = health()
        events = evidence / "events.jsonl"
        report = {
            "version": "vh1-xpm-online-qualification-1.0",
            "run_id": run_id,
            "image": args.image,
            "host_sources_sha256": {
                name: digest(Path(__file__).parent / name)
                for name in ("qualify_vh1_xpm_online.py", "qualify_vh1_xpm_linux.py")
            },
            "cases": cases,
            "boundary_denials": boundary,
            "proxy_events_sha256": digest(events) if events.exists() else None,
            "before": before,
            "after": after,
            "services_unchanged": before == after,
            "release_approved": False,
            "production_deployed": False,
            "sps_1_10_compatibility_proven": False,
        }
        (destination / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        if events.is_file():
            export_evidence(destination)
        print(
            json.dumps(
                {"report": str(destination / "report.json"), "services_unchanged": before == after}
            )
        )


if __name__ == "__main__":
    main()
