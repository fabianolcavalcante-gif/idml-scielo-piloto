"""Qualify the bounded scanner queue before changing the active systemd units."""

import argparse
import json
import os
import time
from pathlib import Path
from threading import Event, Thread

from ops import deploy_vh09 as d
from ops import deploy_vh1_structural as rollout
from ops import deploy_web_edit as previous
from ops.clamav_stream import IMAGE as SCANNER_IMAGE

NAME = "vh11-scan-queue-20261104-v1"
TEMP = "idml-scan-queue-qualification"
INPUTS = "/var/lib/idml-vh1-qualification/scan-lab-20261031/inputs"


def configure():
    previous.configure()
    d.NAME = rollout.NAME = NAME
    rollout.PREVIOUS = "idml-foundation:" + previous.NAME
    d.STAGE = d.ROOT / "releases" / NAME
    d.IMAGE = "idml-foundation:" + NAME
    d.TEST_IMAGE = d.IMAGE + "-qualification"
    d.EXTRA_TESTS += ("tests/test_scanner_queue.py",)


def write_unit(path, content):
    temporary = path.with_suffix(path.suffix + ".new")
    temporary.write_bytes(content)
    temporary.chmod(0o644)
    temporary.replace(path)


def units(prefix):
    return [Path("/etc/systemd/system") / (prefix + suffix) for suffix in (".socket", "@.service")]


def idle(prefix):
    rows = d.run("systemctl", "list-units", prefix + "@*", "--state=running", "--no-legend")
    return not rows.strip()


def runner(socket):
    return [
        "docker",
        "run",
        "--rm",
        "--network=none",
        "--read-only",
        "--user=10001:10001",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--memory=480m",
        "--cpus=0.6",
        "--pids-limit=96",
        "--tmpfs",
        "/tmp:rw,size=512m,mode=1777",  # noqa: S108
        "-v",
        f"{socket}:/run/idml-clamav-vh1:ro",
        "-v",
        f"{INPUTS}:/inputs:ro",
        "-v",
        f"{d.STAGE}:/qualification:ro",
        "-w",
        "/qualification",
        "-e",
        "PYTHONPATH=/app/src:/qualification",
        d.TEST_IMAGE,
    ]


def native():
    paths = units(TEMP)
    assert not any(p.exists() for p in paths)
    for path, source in zip(paths, units("idml-clamav-vh1"), strict=True):
        data = (
            (d.STAGE / "deploy" / source.name)
            .read_text()
            .replace("idml-clamav-vh1/scan.sock", TEMP + "/scan.sock")
        )
        write_unit(path, data.encode())
    d.run("systemctl", "daemon-reload")
    d.run("systemctl", "start", TEMP + ".socket")
    try:
        stop = Event()
        observed = []

        def monitor():
            while not stop.is_set():
                observed.append(
                    len(
                        d.run(
                            "docker", "ps", "-q", "--filter", "ancestor=" + SCANNER_IMAGE
                        ).splitlines()
                    )
                )
                stop.wait(2)

        thread = Thread(target=monitor)
        thread.start()
        try:
            log = d.run(
                *runner("/run/" + TEMP),
                "python",
                "-m",
                "ops.qualify_scanner_queue",
                log="native-queue.log",
                timeout=900,
            )
        finally:
            stop.set()
            thread.join(timeout=15)
        assert not thread.is_alive() and observed and max(observed) == 1
        result = json.loads(log.splitlines()[-1])
        result.update(max_engines_observed=max(observed), engine_observation_count=len(observed))
        d.write("native-queue.json", result)
        # Repeat the authenticated HTTP entry/conversion comparison with both real packages.
        log = d.run(
            *runner("/run/" + TEMP),
            "python",
            "-m",
            "ops.qualify_scan_inputs",
            log="native-workflow.log",
            timeout=1500,
        )
        workflow = json.loads(log.splitlines()[-1])
        assert workflow["historical_rescan_audited"] and all(
            c["offline_valid"] for c in workflow["cases"]
        )
        d.write("native-workflow.json", workflow)
    finally:
        d.run("systemctl", "stop", TEMP + ".socket")
        for _ in range(150):
            if idle(TEMP):
                break
            time.sleep(2)
        assert idle(TEMP), "qualification_connections_still_running"
        for path in paths:
            path.unlink()
        d.run("systemctl", "daemon-reload")


def activate():
    assert (
        json.loads((d.STAGE / "native-queue.json").read_bytes())["concurrent"].count("clamav_clean")
        == 2
    )
    assert json.loads((d.STAGE / "native-workflow.json").read_bytes())["historical_rescan_audited"]
    rollout.activate()
    paths = units("idml-clamav-vh1")
    originals = {p: p.read_bytes() for p in paths}
    for path, value in originals.items():
        (d.STAGE / ("previous-" + path.name)).write_bytes(value)
    try:
        d.run("docker", "pause", "idml-development-api-1")
        try:
            assert idle("idml-clamav-vh1"), "active_scan_must_finish_before_unit_update"
            d.run("systemctl", "stop", "idml-clamav-vh1.socket")
            for path in paths:
                write_unit(path, (d.STAGE / "deploy" / path.name).read_bytes())
            d.run("systemctl", "daemon-reload")
            d.run("systemctl", "start", "idml-clamav-vh1.socket")
        finally:
            d.run("docker", "unpause", "idml-development-api-1")
        probe = (
            "from idml_foundation.ingest.scanner import build_scanner; "
            "from idml_foundation.settings import get_settings; s=build_scanner(get_settings()); "
            "assert s.timeout==300; assert s.scan(b'Active scanner check').clean; "
            "print('clamav_clean')"
        )
        assert (
            d.run("docker", "exec", "idml-development-api-1", "python", "-c", probe)
            == "clamav_clean"
        )
        d.healthy()
        d.write(
            "scanner-unit-deployment.json",
            dict(
                active_clean=True,
                single_engine=True,
                max_connections=4,
                queue_wait_seconds=130,
                client_timeout_seconds=300,
            ),
        )
    except Exception:
        d.run("systemctl", "stop", "idml-clamav-vh1.socket")
        for path, value in originals.items():
            write_unit(path, value)
        d.run("systemctl", "daemon-reload")
        d.run("systemctl", "start", "idml-clamav-vh1.socket")
        raise


if __name__ == "__main__":
    os.umask(0o077)
    configure()
    parser = argparse.ArgumentParser()
    actions = dict(
        prepare=d.prepare, build=d.build, qualify=rollout.qualify, native=native, activate=activate
    )
    parser.add_argument("action", choices=actions)
    actions[parser.parse_args().action]()
