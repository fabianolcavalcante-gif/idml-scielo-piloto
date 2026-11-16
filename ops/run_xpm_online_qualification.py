"""Execute the original XPM with documented web mode and an external allowlist proxy."""

import json
import os
import resource
import shutil
import subprocess
import sys
import time
from pathlib import Path

from run_xpm_qualification import ARCHIVE_SHA256, digest, inspect_report, manifest


def run():
    os.umask(0o077)
    work = Path("/work")
    if list(work.iterdir()):
        raise ValueError("workspace_not_empty")
    # Proxy settings must be supplied by the administrator, never by article metadata.
    proxy = os.environ["https_proxy"]
    if proxy != os.environ["http_proxy"] or not proxy.startswith("http://"):
        raise ValueError("proxy_required")
    original = Path("/opt/original/SciELO_XPM")
    input_before, vendor_before = manifest(Path("/input")), manifest(original)
    runtime = work / "SciELO_XPM"
    shutil.copytree(original, runtime)
    shutil.copytree("/input", work / "input")
    config = runtime / "scielo_env.ini"
    config.write_text(
        "ENABLED_WEB_ACCESS=on\nXML_STRUCTURE_VALIDATOR_PREFERENCE_ORDER=packtools|java\n"
    )
    started = time.monotonic()
    with (work / "stdout.log").open("wb") as out, (work / "stderr.log").open("wb") as err:
        try:
            result = subprocess.run(
                [sys.executable, "xml_package_maker.py", "/work/input", "-auto"],
                cwd=runtime / "xml",
                stdout=out,
                stderr=err,
                timeout=160,
                check=False,
            )
            returncode, timeout = result.returncode, False
        except subprocess.TimeoutExpired:
            returncode, timeout = None, True
    reports = {p.relative_to(work).as_posix(): inspect_report(p) for p in work.rglob("xpm.html")}
    catalogue = runtime / "markup/downloaded_markup_journals.csv"
    record = {
        "version": "vh1-xpm-online-case-1.0",
        "archive_sha256": ARCHIVE_SHA256,
        "runner_sha256": digest(Path(__file__)),
        "proxy_source_sha256": digest(Path("/opt/xpm_egress_proxy.py")),
        "returncode": returncode,
        "timed_out": timeout,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "child_max_rss_kib": resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
        "network": "internal_bridge_via_allowlisted_proxy",
        "input_manifest": input_before,
        "input_unchanged": input_before == manifest(Path("/input")),
        "vendor_files_unchanged": all(
            digest(runtime / name) == sha for name, sha in vendor_before.items()
        ),
        "reports": reports,
        "catalogue_sha256": digest(catalogue) if catalogue.is_file() else None,
        "catalogue_bytes": catalogue.stat().st_size if catalogue.is_file() else 0,
        "generated_package_manifest": manifest(work / "input_xpm/scielo_package"),
        "stdout_sha256": digest(work / "stdout.log"),
        "stderr_sha256": digest(work / "stderr.log"),
        "release_approved": False,
        "sps_1_10_compatibility_proven": False,
        "authenticated_orcid_ownership_proven": False,
    }
    (work / "execution.json").write_text(json.dumps(record, indent=2) + "\n")
    print(
        json.dumps(
            {
                "returncode": returncode,
                "reports": reports,
                "catalogue_bytes": record["catalogue_bytes"],
            }
        )
    )
    return 0 if returncode == 0 and reports and record["vendor_files_unchanged"] else 1


if __name__ == "__main__":
    raise SystemExit(run())
