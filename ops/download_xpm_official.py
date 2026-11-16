"""Download one previously identified official archive on the VPS; never install or execute it."""

import ftplib
import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.request import urlopen
from zipfile import ZipFile

ACCESS_DOC = (
    "https://raw.githubusercontent.com/scieloorg/PC-Programs/master/"
    "docs/source/en_installation_download.rst"
)
ARCHIVE = "SciELO_XPM_4.0.096-R20231215.zip"
EXPECTED = "1b22157b9e816255db8d8910acc46a13b78c0f286cbb68155a39a95ed0f0bdec"
MAX_ARCHIVE = 64 * 1024**2
ROOT = Path("/opt/idml-platform")
UTC = timezone.utc  # noqa: UP017 - this admin script also runs on the VPS host Python 3.10


def verify_archive(stream):
    stream.seek(0)
    with ZipFile(stream) as archive:
        infos = archive.infolist()
        if not 1 <= len(infos) <= 5000:
            raise ValueError("xpm_entry_budget")
        total = 0
        seen = set()
        relevant = []
        dependencies = set()
        for item in infos:
            name = item.orig_filename
            path = PurePosixPath(name)
            normalized = name.rstrip("/").casefold()
            mode = item.external_attr >> 16
            if (
                not normalized
                or name != item.filename
                or path.is_absolute()
                or ".." in path.parts
                or "\\" in name
                or ":" in name
                or len(name) > 1024
                or normalized in seen
                or item.flag_bits & 1
                or stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)
            ):
                raise ValueError("unsafe_xpm_archive")
            seen.add(normalized)
            total += item.file_size
            if (
                item.file_size > 50 * 1024**2
                or total > 200 * 1024**2
                or item.file_size > max(1024, item.compress_size * 200)
            ):
                raise ValueError("xpm_expansion_budget")
            if any(word in normalized for word in ("requirements", "release", "license", "readme")):
                relevant.append(name)
                if "requirements" in normalized and not item.is_dir() and item.file_size < 65536:
                    content = archive.read(item).decode("utf-8", errors="replace")
                    dependencies.update(re.findall(r"(?:packtools|pillow)==[0-9.]+", content, re.I))
        if archive.testzip() is not None:
            raise ValueError("corrupt_xpm_archive")
    return {
        "entries": len(infos),
        "uncompressed_bytes": total,
        "relevant_paths": sorted(relevant),
        "declared_dependencies": sorted(dependencies),
        "zip_safety_verified": True,
    }


def private_directory():
    if not ROOT.is_dir() or ROOT.resolve() != ROOT:
        raise ValueError("unexpected_workspace")
    path = ROOT
    for component in ("private", "vendor", "xpm", EXPECTED):
        path /= component
        if not path.exists():
            path.mkdir(mode=0o700)
        if path.is_symlink() or not path.is_dir() or path.resolve().parent != path.parent:
            raise ValueError("unsafe_private_directory")
        info = path.stat()
        if info.st_uid != 0 or info.st_mode & 0o077:
            raise ValueError("private_directory_permissions")
    return path


def main():
    stage = "private_directory"
    try:
        os.umask(0o077)
        directory = private_directory()
        target = directory / ARCHIVE
        stage = "public_access_instructions"
        with urlopen(ACCESS_DOC, timeout=20) as response:
            if response.url != ACCESS_DOC:
                raise ValueError("unexpected_access_document_redirect")
            data = response.read(1024**2).decode("utf-8")
        credentials = dict(
            re.findall(r"(?m)^\s*[-*]\s+(user|password):\s*([A-Za-z0-9@._+-]{3,128})\s*$", data)
        )
        if credentials.keys() != {"user", "password"}:
            raise ValueError("ambiguous_access_instructions")
        with tempfile.TemporaryFile(dir=directory) as temporary:
            stage = "official_download"
            with ftplib.FTP("ftp.scielo.br", timeout=30) as ftp:  # noqa: S321 - pinned public FTP
                ftp.login(credentials["user"], credentials["password"])
                ftp.cwd("xpm/multiplatform")
                ftp.voidcmd("TYPE I")
                expected_size = ftp.size(ARCHIVE)
                if not expected_size or not 1 <= expected_size <= MAX_ARCHIVE:
                    raise ValueError("xpm_size_budget")
                count = 0
                digest = hashlib.sha256()

                def receive(block):
                    nonlocal count
                    count += len(block)
                    if count > expected_size or count > MAX_ARCHIVE:
                        raise ValueError("xpm_size_budget")
                    digest.update(block)
                    temporary.write(block)

                ftp.retrbinary("RETR " + ARCHIVE, receive, blocksize=65536)
            stage = "integrity"
            if count != expected_size or digest.hexdigest() != EXPECTED:
                raise ValueError("xpm_hash_mismatch")
            inspection = verify_archive(temporary)
            stage = "persist_verified_archive"
            reused = target.exists()
            if reused:
                if (
                    target.is_symlink()
                    or hashlib.sha256(target.read_bytes()).hexdigest() != EXPECTED
                ):
                    raise ValueError("existing_archive_differs")
            else:
                temporary.seek(0)
                with target.open("xb") as output:
                    shutil.copyfileobj(temporary, output, 65536)
            report = {
                "version": "vh1-xpm-download-1.0",
                "retrieved_at": datetime.now(UTC).isoformat(),
                "source": f"ftp://ftp.scielo.br/xpm/multiplatform/{ARCHIVE}",
                "access_document": ACCESS_DOC,
                "access_document_sha256": hashlib.sha256(data.encode("utf-8")).hexdigest(),
                "archive_name": ARCHIVE,
                "archive_sha256": EXPECTED,
                "bytes": count,
                "vps_path": str(target),
                "archive_reused": reused,
                **inspection,
                "downloaded": True,
                "installed": False,
                "executed": False,
                "sps_1_10_compatibility_proven": False,
                "transport": "public-FTP; integrity pinned to previously recorded SHA-256",
            }
            report_name = "download-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + ".json"
            with (directory / report_name).open("x", encoding="utf-8") as output:
                output.write(json.dumps(report, indent=2) + "\n")
            print(json.dumps(report))
        return 0
    except Exception as error:
        print(json.dumps({"downloaded": False, "stage": stage, "error_type": type(error).__name__}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
