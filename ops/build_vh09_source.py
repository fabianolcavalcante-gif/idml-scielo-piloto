"""Allowlisted VH-09 source bundle with per-file hashes, never private inputs."""

import hashlib
import json
import shutil
import subprocess
import tarfile
from io import BytesIO
from pathlib import Path

from ops.build_phase7_7c08_source import DIRECTORIES, FILES, ROOT

RELEASE = "vh09-20261020-v1"


def main():
    git = shutil.which("git")
    if not git:
        raise RuntimeError("git inventory required")
    inventory = subprocess.check_output(  # noqa: S603 - fixed git inventory command
        [
            git,
            "-c",
            "core.fsmonitor=false",
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "-z",
        ],
        cwd=ROOT,
    )
    hashes = {}
    for name in sorted(set(inventory.decode().split("\0")) - {""}):
        path = Path(name)
        if not (
            path.parts[0] in DIRECTORIES
            or name in FILES
            or name.startswith(
                ("benchmarks/agents/", "benchmarks/qualification/", "benchmarks/security/")
            )
        ):
            continue
        if name == "corpus/private/.gitignore":
            continue
        if (
            any(p.casefold() in {"private", "tmp", "__pycache__", ".env"} for p in path.parts)
            or path.suffix.lower() in {".idml", ".pdf", ".xlsx", ".zip", ".pem", ".key"}
            or (ROOT / path).is_symlink()
            or not (ROOT / path).is_file()
        ):
            raise ValueError("restricted_source_archive_member")
        hashes[name] = hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
    manifest = {"release": RELEASE, "files": hashes, "private_inputs_included": False}
    payload = json.dumps(manifest, sort_keys=True, indent=2).encode()
    output = ROOT / "tmp" / f"{RELEASE}-source.tar.gz"
    output.parent.mkdir(exist_ok=True)

    def permissions(item: tarfile.TarInfo) -> tarfile.TarInfo:
        # Windows stat() commonly supplies 0666: never ship world-writable code.
        item.mode = 0o755 if item.name.endswith(".sh") else 0o644
        item.uid = item.gid = 0
        item.uname = item.gname = "root"
        return item

    with tarfile.open(output, "w:gz") as archive:
        for name in hashes:
            archive.add(ROOT / name, arcname=name, recursive=False, filter=permissions)
        item = tarfile.TarInfo("release-source-manifest.json")
        item.size, item.mode = len(payload), 0o644
        archive.addfile(item, BytesIO(payload))
    print(
        json.dumps(
            {
                "release": RELEASE,
                "files": len(hashes),
                "bytes": output.stat().st_size,
                "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                "private_inputs_included": False,
            }
        )
    )


if __name__ == "__main__":
    main()
