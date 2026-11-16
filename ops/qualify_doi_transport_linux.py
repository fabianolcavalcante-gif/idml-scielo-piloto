"""Synthetic-only native DOI qualification; no article corpus or network access."""

import hashlib
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from doi_authority_transport import mount_arguments, stage_authority
from validator_broker import command, create_arguments, reserve

work = Path("/root/idml-doi-qualification")
work.mkdir(mode=0o700, exist_ok=True)
if work.is_symlink() or work.stat().st_mode & 0o077:
    raise ValueError("private qualification directory required")
reserve(work, starting=True)
image = sys.argv[1]
assert command("docker", "image", "inspect", image, "--format", "{{.Id}}") == image
results = []
for mismatch in (False, True):
    with tempfile.TemporaryDirectory(prefix="doi-synthetic-", dir=work) as temporary:
        folder = Path(temporary)
        xml = (
            b'<article xml:lang="en" article-type="research-article"><front><journal-meta>'
            b"<issn>1809-4457</issn></journal-meta><article-meta>"
            b'<article-id pub-id-type="doi">10.1234/test</article-id>'
            b"<title-group><article-title>Synthetic transport test</article-title></title-group>"
            b'<contrib-group><contrib contrib-type="author"><name><surname>Tester</surname>'
            b"<given-names>Alice</given-names></name></contrib></contrib-group>"
            b"</article-meta></front></article>"
        )
        candidate = folder / "candidate.xml"
        candidate.write_bytes(xml)
        candidate.chmod(0o644)
        snapshot = json.dumps(
            {
                "status": "ok",
                "message": {
                    "DOI": "10.1234/test",
                    "ISSN": ["1809-4457"],
                    "title": ["Unrelated data" if mismatch else "Synthetic transport test"],
                    "author": [
                        {
                            "given": "Bob" if mismatch else "Alice",
                            "family": "Wrong" if mismatch else "Tester",
                        }
                    ],
                },
            }
        ).encode()
        manifest = json.dumps(
            {
                "candidate_sha256": hashlib.sha256(xml).hexdigest(),
                "snapshot_sha256": hashlib.sha256(snapshot).hexdigest(),
                "retrieved_at": datetime.now(timezone.utc).isoformat(),  # noqa: UP017 - host 3.10
                "authority": "https://api.crossref.org/works/",
            }
        ).encode()
        (folder / "manifest.json").write_bytes(manifest)
        (folder / "crossref.json").write_bytes(snapshot)
        spec = {
            "name": "packtools",
            "input_suffix": ".xml",
            "image_id": image,
            "doi_authority": {
                "manifest_path": str(folder / "manifest.json"),
                "snapshot_path": str(folder / "crossref.json"),
                "manifest_sha256": hashlib.sha256(manifest).hexdigest(),
            },
        }
        authority = stage_authority(spec, candidate)
        args = mount_arguments(create_arguments(spec, candidate), authority)
        args[-2] = "/validator/probe_doi_authority.py"
        cid = command(*args)
        try:
            result = subprocess.run(  # noqa: S603 - fixed Docker command and returned container ID
                ["docker", "start", "-a", cid],  # noqa: S607 - fixed Docker client
                capture_output=True,
                timeout=45,
                check=True,
            )
            row = json.loads(result.stdout)
            assert row["rows"] == 1 and row["native_doi_passed"] is (not mismatch)
            results.append({"metadata_mismatch": mismatch, **row})
        finally:
            command("docker", "rm", "-f", cid)
print(
    json.dumps(
        {
            "image": image,
            "synthetic_only": True,
            "network": "none",
            "cases": results,
            "temporary_files_cleaned": True,
            "formal_xml_approved": False,
        }
    )
)
