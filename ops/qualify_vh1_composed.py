"""Current native modern receipts for composed XPM qualification, never active grants."""

import argparse
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile

BASE = Path("/opt/idml-platform/private/qualification/vh1-journal-metadata-20261016T165250Z")
MATRIX = [
    ("esa-e20240086", "baseline"),
    ("esa-e20240135", "baseline"),
    ("esa-e20240086", "missing_journal_title"),
    ("esa-e20240086", "malformed_xml"),
]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
    path.chmod(0o600)


def prepare(root):
    # Run in the qualified Python 3.12 image, narrow private bind mount, no Docker socket.
    from ops.qualify_vh1_formula_revisions import refresh_authorities
    from ops.qualify_vh1_xpm_linux import checked_members, mutate

    plan = json.loads((BASE / "plan.json").read_bytes())
    now = datetime.now(timezone.utc)  # noqa: UP017 - host-compatible module
    cache = {}
    for article, mutation in MATRIX:
        folder = root / (article + "-" + mutation)
        folder.mkdir(mode=0o700)
        original = BASE / article
        package = (original / "candidate.zip").read_bytes()
        assert sha(package) == plan["cases"][article]["package_sha256"]
        with ZipFile(BytesIO(package)) as archive:
            members = mutate(checked_members(archive), mutation)
        if mutation != "baseline":
            stream = BytesIO()
            with ZipFile(stream, "w") as archive:
                for name, raw in members.items():
                    archive.writestr(name, raw)
            package = stream.getvalue()
        xml = next(v for n, v in members.items() if n.endswith(".xml"))
        scope = json.loads((original / "scope.json").read_bytes())
        scope.update(xml_sha256=sha(xml), package_sha256=sha(package))
        for name, raw in [("candidate.xml", xml), ("candidate.zip", package)]:
            (folder / name).write_bytes(raw)
            (folder / name).chmod(0o444)
        write(folder / "scope.json", scope)
        if mutation == "malformed_xml":
            # The scoped broker cannot provision malformed XML; never invent a native pass.
            continue
        incoming = folder / "incoming"
        incoming.mkdir(mode=0o700)
        refresh_authorities(original / "incoming", incoming, xml, package, cache)
        grant_id = str(uuid4())
        write(
            incoming / "manifest.json",
            dict(
                version="validation-authority-bundle-1.0",
                authorization_id=grant_id,
                scope=scope,
                files={p.name: sha(p.read_bytes()) for p in incoming.iterdir()},
            ),
        )
        grant = json.loads((original / "grant.json").read_bytes())
        grant.update(
            authorization_id=grant_id,
            scope=scope,
            bundle_sha256=sha((incoming / "manifest.json").read_bytes()),
            issued_at=now.isoformat(),
            expires_at=(now + timedelta(days=1)).isoformat(),
        )
        write(folder / "grant.json", grant)
        print(json.dumps(dict(prepared=folder.name)), flush=True)


def modern(root, source, matrix=None, capture_failures=False):
    from ops.provision_scoped_authorities import provision
    from ops.scoped_validator_broker import execute

    registry = json.loads((source / "config/validator-registry-vh1-composed.json").read_bytes())
    authority = root / "authority"
    (authority / "authorizations").mkdir(parents=True, mode=0o700)
    work = root / "jobs"
    work.mkdir(mode=0o700)
    for article, mutation in MATRIX if matrix is None else matrix:
        folder = root / (article + "-" + mutation)
        scope = json.loads((folder / "scope.json").read_bytes())
        responses = {}
        failures = {}
        if mutation != "malformed_xml":
            grant = json.loads((folder / "grant.json").read_bytes())
            write(authority / "authorizations" / (grant["authorization_id"] + ".json"), grant)
            provision(
                authority, folder / "incoming", folder / "candidate.xml", folder / "candidate.zip"
            )
            for item in registry["validators"]:
                if item["channel"] != "active":
                    continue
                spec = {**item, "_scope": scope, "_authority_root": str(authority)}
                run_folder = folder / (spec["name"] + "-input")
                run_folder.mkdir(mode=0o700)
                candidate = run_folder / ("candidate" + spec["input_suffix"])
                candidate.write_bytes((folder / candidate.name).read_bytes())
                candidate.chmod(0o444)
                # Existing supervisor enforces limits, input hash and post-execution grant recheck.
                try:
                    raw = execute(spec, candidate, work)
                except RuntimeError:
                    if not capture_failures:
                        raise
                    failures[spec["name"]] = "validator-execution-failed"
                    print(
                        json.dumps(dict(case=folder.name, validator=spec["name"], failed=True)),
                        flush=True,
                    )
                    continue
                path = folder / (spec["name"] + "-response.json")
                with path.open("xb") as stream:
                    stream.write(raw)
                path.chmod(0o600)
                responses[spec["name"]] = sha(raw)
                print(
                    json.dumps(dict(case=folder.name, validator=spec["name"], receipt_sealed=True)),
                    flush=True,
                )
        write(
            folder / "modern-manifest.json",
            dict(
                version="composed-modern-native-1.0",
                scope=scope,
                responses=responses,
                **({"failures": failures} if capture_failures else {}),
                malformed_input_not_provisioned=mutation == "malformed_xml",
                active_application_changed=False,
            ),
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["prepare", "modern"])
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        prepare(args.root) if args.phase == "prepare" else modern(args.root, args.source)
    except Exception as error:
        print(json.dumps(dict(failed=True, error_type=type(error).__name__)), flush=True)
        raise SystemExit(1) from None
