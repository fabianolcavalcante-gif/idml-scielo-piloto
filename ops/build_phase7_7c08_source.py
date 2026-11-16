"""Build an allowlisted deployment archive; never include the private corpus."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tarfile
from pathlib import Path

ROOT = Path(__file__).parents[1]
DIRECTORIES = {
    ".github",
    "config",
    "corpus",
    "deploy",
    "docs",
    "migrations",
    "openclaw",
    "ops",
    "profiles",
    "prompts",
    "schemas",
    "src",
    "tests",
    "vendor",
}
FILES = {
    ".dockerignore",
    "README.md",
    "PLANO_DESENVOLVIMENTO_POR_FASES.md",
    "alembic.ini",
    "pyproject.toml",
    "requirements.lock",
    "requirements-dev.lock",
    ".gitignore",
    ".env.example",
}


def main() -> None:
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("git inventory required")
    result = subprocess.run(  # noqa: S603 - absolute executable, fixed inventory arguments
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
        check=True,
        capture_output=True,
    )
    paths = []
    for name in sorted(set(result.stdout.decode().split("\0")) - {""}):
        path = Path(name)
        allowed = (
            path.parts[0] in DIRECTORIES
            or name in FILES
            or name.startswith(
                ("benchmarks/agents/", "benchmarks/qualification/", "benchmarks/security/")
            )
        )
        if not allowed:
            continue
        if name == "corpus/private/.gitignore":
            continue
        if any(part.casefold() in {"private", "tmp", "__pycache__", ".env"} for part in path.parts):
            raise ValueError("restricted source archive member")
        if path.suffix.lower() in {".idml", ".pdf", ".xlsx", ".zip", ".pem", ".key"}:
            raise ValueError("binary corpus/credential cannot enter source archive")
        full = ROOT / path
        if full.is_symlink() or not full.is_file():
            raise ValueError("source member is not a regular file")
        paths.append(name)
    output = ROOT / "tmp/phase7-7c08-source.tar.gz"
    output.parent.mkdir(exist_ok=True)
    with tarfile.open(output, "w:gz") as archive:
        for name in paths:
            archive.add(ROOT / name, arcname=name, recursive=False)
    print(
        json.dumps(
            {
                "files": len(paths),
                "bytes": output.stat().st_size,
                "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                "private_corpus_included": False,
            }
        )
    )


if __name__ == "__main__":
    main()
