"""Full isolated Packtools socket qualification with synthetic input only."""

import hashlib
import json
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree

from validator_broker import command, receive, reserve


def client(folder, mode):
    header = json.loads((folder / "header.json").read_text())
    suffix = ".zip" if header["name"] == "spsvalidator" else ".xml"
    payload = (folder / ("candidate" + suffix)).read_bytes()
    raw = json.dumps(header).encode()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.connect(str(folder / "broker.sock"))
        connection.sendall(struct.pack("!I", len(raw)) + raw + payload)
        if mode == "disconnect":
            return
        connection.settimeout(600)
        prefix = connection.recv(4)
        if mode in {"expired", "package-mismatch", "xml-mismatch"}:
            assert prefix == b""
            print(json.dumps({"rejected": True}))
            return
        assert len(prefix) == 4
        length = struct.unpack("!I", prefix)[0]
        assert 0 < length <= 8 * 1024**2
        response = json.loads(receive(connection, length, time.monotonic() + 600))
        assert response["candidate_sha256"] == hashlib.sha256(payload).hexdigest()
        codes = [row["code"] for row in response["result"]["findings"]]
        doi_findings = [code for code in codes if "registered-doi" in code]
        assert "external-verification-unavailable-doi-registry" not in codes
        assert bool(doi_findings) == (mode == "mismatch"), (mode, doi_findings)
        print(
            json.dumps(
                {
                    "adapter_completed": True,
                    "doi_mismatch_detected": bool(doi_findings),
                    "summary": response["result"]["summary"],
                    "report_sha256": hashlib.sha256(
                        json.dumps(response, sort_keys=True).encode()
                    ).hexdigest(),
                }
            )
        )


def services():
    ids = command("docker", "ps", "-q").split()
    return {
        row["Id"]: (row["State"]["StartedAt"], row["RestartCount"])
        for row in json.loads(command("docker", "inspect", *ids))
    }


def main():
    source = Path(__file__).resolve().parent
    image = sys.argv[1]
    validator = sys.argv[2] if len(sys.argv) > 2 else "packtools"
    assert validator in {"packtools", "spsvalidator"}
    suffix = ".zip" if validator == "spsvalidator" else ".xml"
    assert command("docker", "image", "inspect", image, "--format", "{{.Id}}") == image
    xml = (source / "candidate.xml").read_bytes()
    if (
        hashlib.sha256(xml).hexdigest()
        != "02a405e124fa6ec2fbed6a5df5b78bd764427047a8c665fa2ec12bd8213a6769"
    ):
        raise ValueError("fixed_synthetic_fixture_required")
    tree = ElementTree.fromstring(xml)  # noqa: S314 - generated synthetic fixture only
    payload = (source / ("candidate" + suffix)).read_bytes()
    if validator == "spsvalidator":
        from doi_package_binding import bound_package_xml

        assert (
            bound_package_xml(
                payload,
                {
                    "package_sha256": hashlib.sha256(payload).hexdigest(),
                    "candidate_sha256": hashlib.sha256(xml).hexdigest(),
                },
            )
            == xml
        )
    meta = tree.find("front/article-meta")
    snapshot = {
        "status": "ok",
        "message": {
            "DOI": meta.findtext("article-id[@pub-id-type='doi']"),
            "ISSN": [e.text for e in tree.findall("front/journal-meta/issn")],
            "title": ["".join(meta.find("title-group/article-title").itertext())],
            "author": [
                {"given": e.findtext("given-names"), "family": e.findtext("surname")}
                for e in meta.findall("contrib-group/contrib/name")
            ],
        },
    }
    baseline = services()
    rows = []
    modes = ["match", "mismatch", "expired", "disconnect"]
    if validator == "spsvalidator":
        modes.extend(["package-mismatch", "xml-mismatch"])
    for mode in modes:
        reserve(source, starting=True)
        with (
            tempfile.TemporaryDirectory(prefix="idml-doi-socket-", dir="/run") as temp,
            tempfile.TemporaryDirectory(prefix="idml-doi-authority-", dir="/root") as private,
        ):
            folder, authority = Path(temp), Path(private)
            folder.chmod(0o755)
            work = authority / "work"
            work.mkdir(mode=0o700)
            for name in (
                "qualify_doi_socket_linux.py",
                "validator_broker.py",
                "doi_authority_transport.py",
                "doi_package_binding.py",
            ):
                shutil.copyfile(source / name, folder / name)
                (folder / name).chmod(0o644)
            (folder / ("candidate" + suffix)).write_bytes(payload)
            response = json.loads(json.dumps(snapshot))
            if mode == "mismatch":
                response["message"].update(
                    title=["Unrelated title"], author=[{"given": "Other", "family": "Person"}]
                )
            raw = json.dumps(response).encode()
            manifest = json.dumps(
                {
                    "authority": "https://api.crossref.org/works/",
                    "candidate_sha256": hashlib.sha256(xml).hexdigest(),
                    **(
                        {"package_sha256": hashlib.sha256(payload).hexdigest()}
                        if validator == "spsvalidator"
                        else {}
                    ),
                    "snapshot_sha256": hashlib.sha256(raw).hexdigest(),
                    "retrieved_at": (
                        datetime.now(timezone.utc) - timedelta(days=8 if mode == "expired" else 0)  # noqa: UP017
                    ).isoformat(),
                }
            ).encode()
            if mode in {"package-mismatch", "xml-mismatch"}:
                invalid = json.loads(manifest)
                field = "package_sha256" if mode == "package-mismatch" else "candidate_sha256"
                invalid[field] = "a" * 64
                manifest = json.dumps(invalid).encode()
            (authority / "manifest.json").write_bytes(manifest)
            (authority / "crossref.json").write_bytes(raw)
            spec = {
                "name": validator,
                "channel": "active",
                "image_id": image,
                "version": "0.3.0+d1aa774d4e33"
                if validator == "spsvalidator"
                else "4.17.2+ef0e6f874ea7",
                "profile_id": "sps-1.10/jats-1.3",
                "input_suffix": suffix,
                "timeout_seconds": 300,
                "max_output_bytes": 8388608,
                "doi_authority": {
                    "manifest_path": str(authority / "manifest.json"),
                    "snapshot_path": str(authority / "crossref.json"),
                    "manifest_sha256": hashlib.sha256(manifest).hexdigest(),
                },
            }
            (folder / "registry.json").write_text(json.dumps({"validators": [spec]}))
            (folder / "header.json").write_text(
                json.dumps(
                    {
                        "version": "local-validator-1.0",
                        "name": validator,
                        "candidate_sha256": hashlib.sha256(payload).hexdigest(),
                        "size": len(payload),
                        "tool_sha256": image.removeprefix("sha256:"),
                        "validator_version": spec["version"],
                        "profile_id": spec["profile_id"],
                    }
                )
            )
            broker = subprocess.Popen(  # noqa: S603 - fixed qualification script
                [
                    sys.executable,
                    str(folder / "validator_broker.py"),
                    "--socket",
                    str(folder / "broker.sock"),
                    "--work",
                    str(work),
                    "--registry",
                    str(folder / "registry.json"),
                    "--once",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            try:
                for _ in range(100):
                    if (folder / "broker.sock").exists():
                        break
                    if broker.poll() is not None:
                        raise RuntimeError("broker_start_failed")
                    time.sleep(0.05)
                result = subprocess.run(  # noqa: S603 - fixed synthetic client
                    [
                        sys.executable,
                        str(folder / "qualify_doi_socket_linux.py"),
                        "--client",
                        str(folder),
                        mode,
                    ],
                    user=10001,
                    group=10001,
                    capture_output=True,
                    timeout=620,
                    check=False,
                )
                if result.returncode:
                    broker.wait(timeout=10)
                    raise RuntimeError(
                        broker.stdout.read().decode() + result.stderr.decode()[-2000:]
                    )
                broker.wait(timeout=320)
                assert not (folder / "broker.sock").exists() and not list(work.iterdir())
                rows.append(
                    {
                        "mode": mode,
                        "cleaned": True,
                        **(
                            json.loads(result.stdout)
                            if result.stdout
                            else {"client_disconnected": True}
                        ),
                    }
                )
            finally:
                if broker.poll() is None:
                    broker.terminate()
                    broker.wait(timeout=15)
                broker.stdout.close()
    assert baseline == services()
    print(
        json.dumps(
            {
                "image": image,
                "validator": validator,
                "cases": rows,
                "existing_services_unchanged": True,
                "synthetic_only": True,
                "peer_uid": 10001,
                "formal_xml_approved": False,
            }
        )
    )


if __name__ == "__main__":
    if sys.argv[1] == "--client":
        client(Path(sys.argv[2]), sys.argv[3])
    else:
        main()
