"""Linux lab: real socket and immutable adapters; no active application modifications."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from provision_scoped_authorities import provision
from validator_broker import reserve

APP = "sha256:4fcf47666812a6b45dbafe5baecc44dcdb6393ac7b4893568b44e1683cf2ed86"
VAULT = Path(
    "/opt/idml-platform/private/source-vault/"
    "25ca4293d4e180ad32b7751b50fd30cd0f66ace056ff7226cddf01640b69b1e8"
)
CLIENT = {
    "services": (
        "scoped_validator_transport.py",
        "validator_transport.py",
        "validation_scope.py",
        "package_validation.py",
    ),
    "release": ("validator_registry.py", "validation_engine.py"),
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")


def main():
    source = Path(__file__).resolve().parent
    raw = (source / "plan.json").read_bytes()
    if len(sys.argv) != 2 or digest(raw) != sys.argv[1]:
        raise ValueError("plan_mismatch")
    plan = json.loads(raw)
    for name, sha in plan["code_sha256"].items():
        if Path(name).name != name or digest((source / name).read_bytes()) != sha:
            raise ValueError("source_mismatch")
    if digest((source / "registry.json").read_bytes()) != plan["registry_sha256"]:
        raise ValueError("registry_mismatch")
    report = {
        "version": "vh1-scoped-socket-1.0",
        "plan_sha256": digest(raw),
        "code_sha256": plan["code_sha256"],
        "registry_sha256": plan["registry_sha256"],
        "synthetic_scopes_only": True,
        "active_application_changed": False,
        "formal_xml_approved": False,
        "cases": [],
        "negative_controls": {},
    }
    work = Path("/var/lib/idml-vh1-qualification")
    work.mkdir(mode=0o700, exist_ok=True)
    reserve(work, starting=True)
    with tempfile.TemporaryDirectory(prefix="scoped-socket-", dir=work) as temporary:
        lab = Path(temporary)
        authority = lab / "authority"
        (authority / "authorizations").mkdir(parents=True, mode=0o700)
        socket_folder = lab / "connection"
        socket_folder.mkdir(mode=0o755)
        socket_folder.chmod(0o755)
        jobs = lab / "jobs"
        jobs.mkdir(mode=0o700)
        for case, details in plan["cases"].items():
            if case not in {"esa-e20240086", "esa-e20240135"}:
                raise ValueError("case_denied")
            for name, sha in details["files"].items():
                path = Path(name)
                if (
                    path.is_absolute()
                    or ".." in path.parts
                    or digest((source / case / path).read_bytes()) != sha
                ):
                    raise ValueError("input_mismatch")
            scope = json.loads((source / case / "scope.json").read_bytes())
            grant = json.loads((source / case / "grant.json").read_bytes())
            write(authority / "authorizations" / (grant["authorization_id"] + ".json"), grant)
            inputs = lab / case
            inputs.mkdir(mode=0o700)
            for kind in ("xml", "zip"):
                raw = (VAULT / case / ("candidate." + kind)).read_bytes()
                if digest(raw) != scope["xml_sha256" if kind == "xml" else "package_sha256"]:
                    raise ValueError("candidate_mismatch")
                (inputs / ("candidate." + kind)).write_bytes(raw)
                (inputs / ("candidate." + kind)).chmod(0o444)
            # Copy authority records to the root-owned ancestry required by trusted_read.
            shutil.copytree(source / case / "incoming", inputs / "incoming")
            provision(
                authority, inputs / "incoming", inputs / "candidate.xml", inputs / "candidate.zip"
            )
        registry = json.loads((source / "registry.json").read_bytes())
        write(lab / "broker.json", {**registry, "authority_root": str(authority)})
        broker = subprocess.Popen(  # noqa: S603 - fixed administrative Python script
            [
                sys.executable,
                str(source / "scoped_validator_broker.py"),
                "--socket",
                str(socket_folder / "broker.sock"),
                "--work",
                str(jobs),
                "--registry",
                str(lab / "broker.json"),
                "--uid",
                "10001",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            for _ in range(100):
                if (socket_folder / "broker.sock").exists():
                    break
                if broker.poll() is not None:
                    raise ValueError("broker_start_failed")
                time.sleep(0.1)

            def run(case, mode):
                reserve(work, starting=True)
                cmd = [
                    "docker",
                    "run",
                    "--rm",
                    "--network=none",
                    "--read-only",
                    "--user=10001:10001",
                    "--memory=192m",
                    "--memory-swap=192m",
                    "--cpus=0.25",
                    "--pids-limit=64",
                    "--cap-drop=ALL",
                    "--security-opt=no-new-privileges",
                    "--log-driver=none",
                    "--tmpfs",
                    "/tmp:rw,nosuid,nodev,size=32m,uid=10001,gid=10001",  # noqa: S108
                ]
                mounts = {
                    source / "probe_scoped_socket.py": "/qualification/probe.py",
                    source / "registry.json": "/qualification/registry.json",
                    source / case / "scope.json": "/qualification/scope.json",
                    socket_folder: "/connection",
                }
                for kind in ("xml", "zip"):
                    mounts[lab / case / ("candidate." + kind)] = "/qualification/candidate." + kind
                for section, files in CLIENT.items():
                    for name in files:
                        mounts[source / name] = "/app/src/idml_foundation/" + section + "/" + name
                for path, destination in mounts.items():
                    if path.is_file():
                        path.chmod(0o644)  # Exact files mounted; upload parent remains private.
                    cmd.extend(["--mount", f"type=bind,src={path},dst={destination},readonly"])
                cmd.extend(["--entrypoint=python", APP, "/qualification/probe.py", mode])
                result = subprocess.run(cmd, capture_output=True, timeout=1000, check=False)  # noqa: S603
                if result.returncode or len(result.stdout) > 2 * 1024**2:
                    raise ValueError("socket_probe_failed")
                return json.loads(result.stdout)

            for case in plan["cases"]:
                result = run(case, "positive")
                report["cases"].append({"case": case, "assessment": result})
                print(
                    json.dumps(
                        {
                            "case": case,
                            "runs": [
                                {
                                    "name": r["name"],
                                    "status": r["status"],
                                    "counts": r["counts"],
                                    "has_authority_evidence": "authority_verification" in r,
                                }
                                for r in result["external_runs"]
                            ],
                        }
                    ),
                    flush=True,
                )
            case = "esa-e20240135"
            for mode in ("foreign-tenant", "foreign-resource", "changed-xml"):
                result = run(case, mode)
                report["negative_controls"][mode] = {
                    "statuses": {r["name"]: r["status"] for r in result["external_runs"]},
                    "not_approved": result["ready_for_scielo"] is False,
                }
            for case, mode in (("esa-e20240086", "revoked"), ("esa-e20240135", "expired")):
                grant = json.loads((source / case / "grant.json").read_bytes())
                if mode == "revoked":
                    grant["status"] = "revoked"
                else:
                    grant["expires_at"] = (
                        datetime.now(timezone.utc) - timedelta(seconds=1)  # noqa: UP017 - Python 3.10
                    ).isoformat()
                write(authority / "authorizations" / (grant["authorization_id"] + ".json"), grant)
                result = run(case, mode)
                report["negative_controls"][mode] = {
                    "statuses": {r["name"]: r["status"] for r in result["external_runs"]},
                    "not_approved": result["ready_for_scielo"] is False,
                }
        finally:
            broker.terminate()
            try:
                broker.wait(timeout=15)
            except subprocess.TimeoutExpired:
                broker.kill()
                broker.wait(timeout=5)
    with (source / "report.json").open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
    print(json.dumps({"report_saved": True, "active_application_changed": False}))


if __name__ == "__main__":
    os.umask(0o077)
    try:
        main()
    except Exception as error:
        print(
            json.dumps(
                {
                    "failure_type": type(error).__name__,
                    "code": str(error)
                    if str(error).replace("_", "").isalnum()
                    else "qualification_failed",
                }
            )
        )
        raise SystemExit(1) from None
