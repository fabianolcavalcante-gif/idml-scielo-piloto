"""Read-only preflight of a named Windows interpreter and the official XPM ZIP."""

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZipFile

from ops.download_xpm_official import ARCHIVE, EXPECTED, verify_archive

ROOT = Path(__file__).resolve().parents[1]
PROBE = """
import importlib.metadata as m, importlib.util as u, json, sys
versions = {}
for name in ('pillow', 'packtools'):
    try: versions[name] = m.version(name)
    except m.PackageNotFoundError: versions[name] = None
print(json.dumps({'python': sys.version.split()[0], 'platform': sys.platform,
                 'tkinter_module_present': u.find_spec('tkinter') is not None,
                 'packages': versions}))
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", type=Path, required=True)
    args = parser.parse_args()
    archive = ROOT / "benchmarks/private/vendor/xpm" / ARCHIVE
    if hashlib.sha256(archive.read_bytes()).hexdigest() != EXPECTED:
        raise ValueError("official_archive_mismatch")
    with archive.open("rb") as stream:
        safety = verify_archive(stream)
    with ZipFile(archive) as zipped:
        members = {
            n: hashlib.sha256(zipped.read(n)).hexdigest()
            for n in (
                "SciELO_XPM/xml/xml_package_maker.py",
                "SciELO_XPM/xml/app_modules/settings/requirements.txt",
                "SciELO_XPM/xpm_version.txt",
            )
        }
    process = subprocess.run(  # noqa: S603 - explicit local Python, fixed read-only probe
        [str(args.runtime.resolve(strict=True)), "-I", "-c", PROBE],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    runtime = json.loads(process.stdout)
    expected = {"packtools": "2.4.2", "pillow": "6.2.2"}
    report = {
        "version": "vh1-xpm-windows-preflight-1.0",
        "checked_at": datetime.now(UTC).isoformat(),
        "archive_sha256": EXPECTED,
        "official_member_sha256": members,
        "declared_dependencies": safety["declared_dependencies"],
        "runtime": runtime,
        "dependencies_match": runtime["packages"] == expected,
        "xpm_executed": False,
        "dedicated_worker_provisioned": False,
        "sps_1_10_compatibility_proven": False,
        "active_application_changed": False,
        "software_installed": False,
        "archive_extracted": False,
        "status": "preflight-only-not-qualified",
        "next_required": [
            "isolated-nonprivileged-windows-executor",
            "official-dependency-environment",
            "real-positive-and-negative-package-runs",
            "sps-1.10-rule-compatibility",
        ],
    }
    output = ROOT / "benchmarks/qualification/reports/vh1-xpm-preflight-windows-v1.json"
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, sort_keys=True, indent=2)
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
