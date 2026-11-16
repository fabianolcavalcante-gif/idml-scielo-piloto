"""Prepare exactly the authorized VH1 files; transfer only by explicit --upload."""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from idml_foundation.release.doi_snapshot import bind_doi_snapshot
from idml_foundation.services.enrichment import KINDS
from ops.doi_package_binding import bound_package_xml

ROOT = Path(__file__).resolve().parents[1]
DECISION = "docs/authorizations/VH1_VPS_DATA_20261001.md"
SNAPSHOTS = "benchmarks/private/output/h1-real-doi-local/20261001T113558Z"


def checked_read(path):
    if any(p.is_symlink() or p.is_junction() for p in (path, *path.parents)):
        raise ValueError("unsafe_source_path")
    if not path.resolve().is_relative_to(ROOT) or not 0 < path.stat().st_size <= 100 * 1024**2:
        raise ValueError("source_file_budget")
    return path.read_bytes()


def prepare():
    baseline = json.loads(
        (ROOT / "benchmarks/qualification/reports/vh1-lot1-baseline-v1.json").read_text()
    )
    decision = checked_read(ROOT / DECISION)
    data = {"authorization.md": decision}
    for item in baseline["conversion_evidence"]:
        case = item["case"]
        if case not in {"esa-e20240086", "esa-e20240135"}:
            raise ValueError("unauthorized_case")
        source = ROOT / "benchmarks/private/output/h1-country-codes-v1" / case
        for kind, digest in item["catalog_sha256"].items():
            content = checked_read(source / f"{kind}.json")
            if hashlib.sha256(content).hexdigest() != digest:
                raise ValueError("qualified_catalog_changed")
            catalog = KINDS[kind].model_validate_json(content)
            if (
                catalog.source_idml_sha256 != item["source_sha256"]
                or catalog.journal_profile_id != "esa-aop-1.1.0"
            ):
                raise ValueError("catalog_scope_mismatch")
            data[f"{case}/catalogs/{kind}.json"] = content
        xml = checked_read(source / "candidate.xml")
        package = checked_read(source / "candidate.zip")
        if (
            hashlib.sha256(xml).hexdigest() != item["xml_sha256"]
            or hashlib.sha256(package).hexdigest() != item["package_sha256"]
        ):
            raise ValueError("qualified_candidate_changed")
        authority = ROOT / SNAPSHOTS / case
        raw_manifest = checked_read(authority / "manifest.json")
        manifest = json.loads(raw_manifest)
        snapshot = checked_read(authority / "crossref.json")
        if bound_package_xml(package, manifest) != xml:
            raise ValueError("authority_package_mismatch")
        bind_doi_snapshot(
            candidate=xml,
            snapshot=snapshot,
            expected_candidate_sha256=manifest["candidate_sha256"],
            expected_snapshot_sha256=manifest["snapshot_sha256"],
            retrieved_at=datetime.fromisoformat(manifest["retrieved_at"]),
            now=datetime.now(UTC),
        )
        data[f"{case}/authority/manifest.json"] = raw_manifest
        data[f"{case}/authority/crossref.json"] = snapshot
        data[f"{case}/candidate.xml"] = xml
        data[f"{case}/candidate.zip"] = package
    manifest = {
        "version": "vh1-source-vault-1.0",
        "decision_record": "VH1-VPS-DATA-20261001",
        "decision_sha256": hashlib.sha256(decision).hexdigest(),
        "scope": ["esa-e20240086", "esa-e20240135"],
        "destination": "vps",
        "runtime_activated": False,
        "collection_timestamps_preserved": True,
        "gold_included": False,
        "holdout_included": False,
        "idml_included": False,
        "files": {
            name: {"sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)}
            for name, content in sorted(data.items())
        },
    }
    raw = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    identity = hashlib.sha256(raw).hexdigest()
    folder = ROOT / "benchmarks/private/output" / ("incoming-" + identity)
    if folder.exists():
        raise ValueError("staging_already_exists")
    folder.mkdir(mode=0o700)
    for name, content in {**data, "manifest.json": raw}.items():
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with path.open("xb") as stream:
            stream.write(content)
    return folder, identity, manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upload", action="store_true")
    parser.add_argument("--ssh-key", type=Path)
    parser.add_argument("--host")
    parser.add_argument("--port", type=int, default=22022)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.upload and (
            not args.ssh_key
            or not args.host
            or not re.fullmatch(r"[A-Za-z0-9_.@-]+", args.host)
            or args.host.startswith("-")
        ):
            raise ValueError("explicit_destination_required")
        folder, identity, manifest = prepare()
        result = {
            "version": "vh1-vps-source-staging-1.0",
            "uploaded": False,
            "manifest_sha256": identity,
            "scope": manifest["scope"],
            "catalogs": 6,
            "authority_snapshots": 2,
            "candidates": 2,
            "runtime_activated": False,
            "gold_included": False,
            "holdout_included": False,
        }
        if args.upload:
            scp_executable = shutil.which("scp")
            if scp_executable is None:
                raise ValueError("scp_unavailable")
            ssh = [
                "ssh",
                "-i",
                str(args.ssh_key),
                "-p",
                str(args.port),
                "-o",
                "BatchMode=yes",
                args.host,
            ]
            subprocess.run(  # noqa: S603 - explicit authorized host, fixed remote command
                [
                    *ssh,
                    "test -d /opt/idml-platform/private && test ! -L /opt/idml-platform/private "
                    "&& test ! -L /opt/idml-platform/private/source-vault "
                    "&& install -d -m 700 -o root -g root /opt/idml-platform/private/source-vault",
                ],
                capture_output=True,
                check=True,
                timeout=30,
            )
            subprocess.run(  # noqa: S603 - newly prepared allowlisted files only
                [
                    scp_executable,
                    "-i",
                    str(args.ssh_key),
                    "-P",
                    str(args.port),
                    "-o",
                    "BatchMode=yes",
                    "-r",
                    str(folder),
                    f"{args.host}:/opt/idml-platform/private/source-vault/",
                ],
                capture_output=True,
                check=True,
                timeout=180,
            )
            proof = subprocess.run(  # noqa: S603 - constant verifier, hash-only argument
                [*ssh, "python3 - " + identity],
                input=(ROOT / "ops/verify_vh1_private_vault.py").read_bytes(),
                capture_output=True,
                check=True,
                timeout=60,
            )
            result.update(json.loads(proof.stdout))
            result["uploaded"] = True
        with args.report.open("x", encoding="utf-8") as output:
            output.write(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result))
        return 0
    except Exception as error:
        print(json.dumps({"staging_completed": False, "failure_type": type(error).__name__}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
