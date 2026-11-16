"""Run an unmodified, pinned XPM in a disposable offline container, not a release gate.

The writable /work mount is private and unique per case. Input is mounted read-only.
This wrapper only copies files, writes documented configuration and invokes the CLI.
It never patches vendor code, creates substitute reports or accepts XML warnings.
Compatible with the vendor's Python 3.8 runtime.
"""

import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from lxml import etree, html

ARCHIVE_SHA256 = "1b22157b9e816255db8d8910acc46a13b78c0f286cbb68155a39a95ed0f0bdec"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest(directory):
    return {
        p.relative_to(directory).as_posix(): digest(p)
        for p in sorted(directory.rglob("*"))
        if p.is_file()
    }


def inspect_report(path):
    """Inventory genuine HTML; the application parser remains the release authority."""
    data = path.read_bytes()
    document = html.fromstring(data, parser=html.HTMLParser(no_network=True))
    texts = document.xpath(
        "//text()[not(ancestor::script) and not(ancestor::style) and not(ancestor::template)]"
    )
    import re

    visible = " ".join(" ".join(str(t) for t in texts).split())
    totals = {}
    for label in ("blocking errors", "fatal errors", "errors", "warnings"):
        matches = re.findall(r"Total of " + label + r"\s*:\s*(\d+)", visible, re.I)
        totals[label.replace(" ", "_")] = [int(v) for v in matches]
    return {"sha256": digest(path), "bytes": len(data), "totals": totals}


def run():
    import resource  # Linux-only measurement; pure report helpers also run in local tests.

    os.umask(0o077)
    work = Path("/work")
    original = Path("/opt/original/SciELO_XPM")
    source = Path("/input")
    if list(work.iterdir()):
        raise ValueError("case_workspace_must_be_empty")
    before_input = manifest(source)
    before_vendor = manifest(original)
    runtime = work / "SciELO_XPM"
    shutil.copytree(original, runtime)
    package = work / "input"
    shutil.copytree(source, package)
    # BIN_PATH in the multiplatform ZIP is its root, not an extra bin directory.
    config = runtime / "scielo_env.ini"
    config.write_text(
        "ENABLED_WEB_ACCESS=off\nXML_STRUCTURE_VALIDATOR_PREFERENCE_ORDER=packtools|java\n",
        encoding="utf-8",
    )
    started = time.time()
    command = ["python", "xml_package_maker.py", str(package), "-auto"]
    timed_out = False
    with (work / "stdout.log").open("wb") as out, (work / "stderr.log").open("wb") as err:
        try:
            result = subprocess.run(  # noqa: S603 - fixed vendor CLI in isolated container
                command, cwd=runtime / "xml", stdout=out, stderr=err, timeout=150, check=False
            )
            returncode = result.returncode
        except subprocess.TimeoutExpired:
            returncode = None
            timed_out = True
    reports = {}
    for path in sorted(work.rglob("xpm.html")):
        try:
            reports[path.relative_to(work).as_posix()] = inspect_report(path)
        except (ValueError, etree.LxmlError) as error:
            reports[path.relative_to(work).as_posix()] = {
                "sha256": digest(path),
                "parse_error": type(error).__name__,
            }
    original_files_unchanged = all(
        (runtime / name).is_file() and digest(runtime / name) == sha
        for name, sha in before_vendor.items()
    )
    record = {
        "version": "vh1-xpm-linux-case-1.0",
        "archive_sha256": ARCHIVE_SHA256,
        "runner_sha256": digest(Path(__file__)),
        "command": command,
        "returncode": returncode,
        "timed_out": timed_out,
        "elapsed_seconds": round(time.time() - started, 3),
        "child_max_rss_kib": resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
        "network": "none",
        "external_queries_completed": False,
        "documented_config_sha256": digest(config),
        "input_manifest": before_input,
        "input_unchanged": before_input == manifest(source),
        "vendor_files_unchanged": original_files_unchanged,
        "reports": reports,
        "stdout_sha256": digest(work / "stdout.log"),
        "stderr_sha256": digest(work / "stderr.log"),
        "runtime_dependencies": Path("/opt/dependencies.txt").read_text().splitlines(),
        "system_packages_sha256": digest(Path("/opt/system-packages.txt")),
        "generated_package_manifest": manifest(work / "input_xpm/scielo_package"),
        "release_approved": False,
        "sps_1_10_compatibility_proven": False,
    }
    (work / "execution.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in record.items() if k not in ("input_manifest", "command")}))
    return 0 if returncode == 0 and reports and original_files_unchanged else 1


if __name__ == "__main__":
    raise SystemExit(run())
