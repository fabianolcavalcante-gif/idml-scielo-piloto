"""Root-only, sequential offline XPM broker. No publication or external queries."""

import base64
import hashlib
import json
import os
import stat
from contextlib import nullcontext
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile

from idml_foundation.services.validation_scope import validate_scope
from ops import validator_broker as legacy
from ops.qualify_vh1_xpm_linux import checked_members, docker_arguments

IMAGE = "sha256:43ca49864959e4106d7cbb571f6f64a1222f9865068fee1ce61953aa19886d63"
TOOL = "1b22157b9e816255db8d8910acc46a13b78c0f286cbb68155a39a95ed0f0bdec"
RUN = legacy.execute


def select_spec(registry, request):
    runtime_authorization = registry == {
        "version": "xpm-online-composed-1.0",
        "image": IMAGE,
        "runtime_article_authorization": True,
    }
    if runtime_authorization:
        registry = {k: v for k, v in registry.items() if k != "runtime_article_authorization"}
    if registry not in (
        {"version": "xpm-offline-1.0", "image": IMAGE},
        {"version": "xpm-online-1.0", "image": IMAGE},
        {"version": "xpm-online-semantic-1.0", "image": IMAGE},
        {"version": "xpm-online-composed-1.0", "image": IMAGE},
    ):
        raise ValueError("invalid_registry")
    if not isinstance(request, dict) or set(request) != {
        "version",
        "size",
        "candidate_sha256",
        "scope",
    }:
        raise ValueError("invalid_request")
    scope = validate_scope(request["scope"])
    if (
        request["version"] != "xpm-local-1.0"
        or type(request["size"]) is not int
        or not 0 < request["size"] <= legacy.MAX_INPUT
        or request["candidate_sha256"] != scope["package_sha256"]
    ):
        raise ValueError("invalid_request")
    return dict(
        input_suffix=".zip",
        image_id=IMAGE,
        timeout_seconds=190,
        max_output_bytes=2 * 1024**2,
        scope=scope,
        online=registry["version"] != "xpm-offline-1.0",
        collect_queries=registry["version"]
        in {"xpm-online-semantic-1.0", "xpm-online-composed-1.0"},
        collect_wayta=registry["version"] == "xpm-online-composed-1.0",
        runtime_authorization=runtime_authorization,
    )


def read_regular(path, root, limit):
    path.relative_to(root)
    for part in (path, *path.parents):
        if part == root:
            break
        if part.is_symlink():
            raise ValueError("unsafe_execution_file")
    descriptor = os.open(
        path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    )
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= limit:
            raise ValueError("execution_file_budget")
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("execution_file_budget")
    return data


def envelope_from_execution(case, scope, *, online=False, query_xml=None, collect_wayta=False):
    runtime = case / "work"
    record = json.loads(read_regular(runtime / "execution.json", runtime, 2 * 1024**2))
    if (
        record.get("version") != ("vh1-xpm-online-case-1.0" if online else "vh1-xpm-linux-case-1.0")
        or record.get("archive_sha256") != TOOL
        or record.get("returncode") != 0
        or record.get("timed_out") is not False
        or record.get("network") != ("internal_bridge_via_allowlisted_proxy" if online else "none")
        or (not online and record.get("external_queries_completed") is not False)
        or record.get("input_unchanged") is not True
        or record.get("vendor_files_unchanged") is not True
        or len(record.get("reports", {})) != 1
    ):
        raise ValueError("xpm_execution_mismatch")
    if online:
        proof = json.loads(read_regular(case / "network-evidence.json", case, 8192))
        events = read_regular(case / "proxy-events.jsonl", case, 1024**2)
        if (
            proof.get("version") != "xpm-supervised-network-1.0"
            or proof.get("image") != IMAGE
            or proof.get("boundary_denials") != [True, True, True]
            or proof.get("events_sha256") != hashlib.sha256(events).hexdigest()
            or proof.get("semantic_queries_complete") is not False
            or proof.get("ephemeral_resources_removed") is not True
        ):
            raise ValueError("xpm_network_evidence_mismatch")
    name, inventory = next(iter(record["reports"].items()))
    relative = Path(name)
    if relative.is_absolute() or ".." in relative.parts or relative.name != "xpm.html":
        raise ValueError("unsafe_report_path")
    report = read_regular(runtime / relative, runtime, 8 * 1024**2)
    digest = hashlib.sha256(report).hexdigest()
    if inventory.get("sha256") != digest:
        raise ValueError("xpm_report_mismatch")
    envelope = dict(
        scope=scope,
        image=IMAGE,
        required_queries_complete=False,
        report_base64=base64.b64encode(report).decode(),
        attestation=dict(
            contract_version="1.0.0",
            candidate_package_sha256=scope["package_sha256"],
            report_sha256=digest,
            tool_sha256=TOOL,
            xpm_version="4.0.096",
            command_id=case.name,
            environment="isolated-linux-supervised-online" if online else "isolated-linux-offline",
        ),
    )
    if query_xml is not None:
        from ops.xpm_authority_collect import collect

        try:
            envelope["query_evidence"] = collect(query_xml, scope, digest, case)
        except (ValueError, OSError):
            # Malformed/unqualified XML must not suppress the original XPM findings.
            envelope["query_evidence"] = None
    if collect_wayta and envelope.get("query_evidence") is not None:
        import subprocess

        from ops.xpm_wayta_collect import collect as collect_service

        try:
            envelope["wayta_evidence"] = collect_service(scope, digest, case)
        except (ValueError, OSError, subprocess.TimeoutExpired, KeyError):
            envelope["wayta_evidence"] = None
    # Seal root-owned copies outside the container's writable mount. Raw HTML is private.
    for name, data in (("report.html", report), ("evidence.json", json.dumps(envelope).encode())):
        with (case / name).open("xb") as stream:
            os.chmod(case / name, 0o600)
            stream.write(data)
    return json.dumps(envelope).encode()


def execute(spec, candidate, work):
    import fcntl  # Linux host only; validators/tests remain importable on Windows.

    with (work / "xpm.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        legacy.reserve(work, starting=True)
        if len(list(work.glob("xpm-run-*"))) >= 32:
            raise ValueError("private_retention_budget")
        scope = validate_scope(spec["scope"])
        approved = None
        if spec.get("runtime_authorization"):
            from ops.runtime_source_authority import decision

            approved = decision(scope)
        if hashlib.sha256(candidate.read_bytes()).hexdigest() != scope["package_sha256"]:
            raise ValueError("candidate_mismatch")
        with ZipFile(candidate) as archive:
            members = checked_members(archive)
        xml = next(value for name, value in members.items() if name.endswith(".xml"))
        if len(xml) > 8 * 1024**2 or hashlib.sha256(xml).hexdigest() != scope["xml_sha256"]:
            raise ValueError("candidate_mismatch")
        case = work / ("xpm-run-" + uuid4().hex)
        case.mkdir(mode=0o700)
        source, runtime = case / "input", case / "work"
        for folder in (source, runtime):
            folder.mkdir(mode=0o700)
            os.chown(folder, 65534, 65534)
        for name, value in members.items():
            path = source / name
            path.write_bytes(value)
            os.chown(path, 65534, 65534)
            path.chmod(0o400)

        connection = None

        def arguments(_spec, _candidate):
            args = docker_arguments(IMAGE, "idml-xpm-" + uuid4().hex, source, runtime)
            args[1] = "create"
            if connection:
                network, endpoint = connection
                args[args.index("--network=none")] = "--network=" + network
                args[-1:-1] = [
                    "--env",
                    "http_proxy=" + endpoint,
                    "--env",
                    "https_proxy=" + endpoint,
                    "--env",
                    "no_proxy=",
                ]
            return [
                *args[:-1],
                "--pull=never",
                "--log-driver=none",
                "--entrypoint=python",
                IMAGE,
                "/opt/run_xpm_online_qualification.py"
                if connection
                else "/opt/run_xpm_qualification.py",
            ]

        previous_arguments, previous_reserve = legacy.create_arguments, legacy.reserve

        def reserve(folder, *, starting=False):
            previous_reserve(folder, starting=starting)
            if sum(p.lstat().st_size for p in case.rglob("*") if not p.is_symlink()) > (
                512 * 1024**2
            ):
                raise ValueError("private_execution_budget")

        legacy.create_arguments, legacy.reserve = arguments, reserve
        try:
            from ops.xpm_online_transport import online_network

            context = online_network(case, IMAGE) if spec["online"] else nullcontext(None)
            with context as connection:
                RUN(spec, candidate, work)
        finally:
            legacy.create_arguments, legacy.reserve = previous_arguments, previous_reserve
        result = envelope_from_execution(
            case,
            scope,
            online=spec["online"],
            query_xml=xml if spec["collect_queries"] else None,
            collect_wayta=spec.get("collect_wayta", False),
        )
        if approved is not None and decision(scope) != approved:
            raise ValueError("article_source_consent_changed_during_execution")
        return result


def main():
    os.umask(0o077)
    legacy.select_spec, legacy.execute = select_spec, execute
    legacy.main()


if __name__ == "__main__":
    main()
