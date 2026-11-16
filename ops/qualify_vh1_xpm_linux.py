"""Bounded XPM feasibility test on the existing VPS, never a production deployment."""

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen
from zipfile import ZipFile

ROOT = Path("/opt/idml-platform/private/qualification")
BASELINE = ROOT / "vh1-final-validation-20261014T155218Z"
PACKAGES = {
    "esa-e20240086": "ba685142396801ed3901d8c63e3ad5da0c81af3b753c6a16b27bb63457a66c6c",
    "esa-e20240135": "2c4aad2df2b1b61316d6bf2f44795c0b4c1acbb7088fb6fd822020a974f9583f",
}
UTC = timezone.utc  # noqa: UP017 - VPS host Python 3.10


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checked_members(archive):
    """Only small flat packages are permitted in this pinned qualification."""
    result = {}
    for item in archive.infolist():
        if (
            not re.fullmatch(r"[A-Za-z0-9_.-]{1,180}", item.filename)
            or item.filename in (".", "..")
            or item.orig_filename != item.filename
            or item.filename.casefold() in {n.casefold() for n in result}
            or item.is_dir()
            or stat.S_IFMT(item.external_attr >> 16) not in (0, stat.S_IFREG)
            or item.flag_bits & 1
            or item.file_size > 32 * 1024**2
        ):
            raise ValueError("unsafe_candidate_member")
        result[item.filename] = archive.read(item)
        if len(result) > 100 or sum(map(len, result.values())) > 64 * 1024**2:
            raise ValueError("candidate_budget_exceeded")
    if sum(n.endswith(".xml") for n in result) != 1:
        raise ValueError("expected_one_xml")
    return result


def mutate(members, mutation):
    result = dict(members)
    xml_name = next(n for n in result if n.endswith(".xml"))
    if mutation == "missing_journal_title":
        value, count = re.subn(rb"<journal-title>[^<]+</journal-title>", b"", result[xml_name])
        if count != 1:
            raise ValueError("journal_title_mutation_not_unique")
        result[xml_name] = value
    elif mutation == "missing_graphic":
        name = next(n for n in sorted(result) if n.endswith("-gf01.jpg"))
        del result[name]
    elif mutation == "malformed_xml":
        result[xml_name] = result[xml_name][:100]
    elif mutation != "baseline":
        raise ValueError("unknown_mutation")
    return result


def command(args, **kwargs):
    return subprocess.run(  # noqa: S603 - explicit argument lists; administrator-only script
        args, check=True, capture_output=True, text=True, timeout=30, **kwargs
    ).stdout


def health():
    names = command(["docker", "ps", "--format", "{{.Names}}"]).splitlines()
    services = {}
    for name in names:
        values = json.loads(command(["docker", "inspect", name]))[0]
        services[name] = {
            "image": values["Image"],
            "started_at": values["State"]["StartedAt"],
            "running": values["State"]["Running"],
            "health": values["State"].get("Health", {}).get("Status"),
        }
    with urlopen("http://127.0.0.1:18080/health/ready", timeout=10) as response:
        readiness = json.load(response)
    return {"services": services, "readiness": readiness}


def docker_arguments(image, name, source, work):
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", image):
        raise ValueError("immutable_image_required")
    if not re.fullmatch(r"idml-xpm-[a-z0-9-]{1,100}", name):
        raise ValueError("invalid_container_name")
    return [
        "docker",
        "run",
        "--name",
        name,
        "--network=none",
        "--read-only",
        "--user=65534:65534",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--memory=384m",
        "--memory-swap=384m",
        "--cpus=0.5",
        "--pids-limit=64",
        "--ulimit",
        "fsize=67108864:67108864",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=32m",  # noqa: S108 - private container tmpfs
        "--mount",
        "type=bind,src=" + str(source) + ",dst=/input,readonly",
        "--mount",
        "type=bind,src=" + str(work) + ",dst=/work",
        image,
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--baseline-only", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", args.image):
        raise ValueError("immutable_image_required")
    os.umask(0o077)
    if ROOT.resolve() != ROOT or not ROOT.is_dir():
        raise ValueError("unexpected_root")
    before = health()
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    destination = ROOT / ("vh1-xpm-linux-" + run_id)
    destination.mkdir(mode=0o700)
    cases = []
    matrix = [(article, "baseline") for article in PACKAGES]
    if not args.baseline_only:
        matrix += [
            ("esa-e20240086", m)
            for m in ("missing_journal_title", "missing_graphic", "malformed_xml")
        ]
    for index, (article, mutation) in enumerate(matrix):
        candidate = BASELINE / article / "candidate.zip"
        if candidate.is_symlink() or digest(candidate) != PACKAGES[article]:
            raise ValueError("candidate_hash_mismatch")
        with ZipFile(candidate) as archive:
            members = mutate(checked_members(archive), mutation)
        case = destination / (article + "-" + mutation)
        case.mkdir()
        source, work = case / "input", case / "work"
        source.mkdir(mode=0o700)
        work.mkdir(mode=0o700)
        os.chown(source, 65534, 65534)
        os.chown(work, 65534, 65534)
        for name, data in members.items():
            target = source / name
            target.write_bytes(data)
            os.chown(target, 65534, 65534)
            os.chmod(target, 0o400)
        name = "idml-xpm-" + run_id.lower() + "-" + str(index)
        cmd = docker_arguments(args.image, name, source, work)
        timed_out = False
        try:
            with (case / "container.log").open("wb") as output:
                try:
                    result = subprocess.run(  # noqa: S603 - bounded, isolated fixed image
                        cmd, stdout=output, stderr=subprocess.STDOUT, timeout=190, check=False
                    )
                    exit_code = result.returncode
                except subprocess.TimeoutExpired:
                    timed_out = True
                    exit_code = None
                    command(["docker", "stop", "-t", "3", name])
            state = json.loads(command(["docker", "inspect", name]))[0]
            execution_path = work / "execution.json"
            record = json.loads(execution_path.read_text()) if execution_path.exists() else None
            summary = {
                "article": article,
                "mutation": mutation,
                "original_package_sha256": PACKAGES[article],
                "docker_exit_code": exit_code,
                "docker_timeout": timed_out,
                "oom_killed": state["State"]["OOMKilled"],
                "execution_sha256": digest(execution_path) if record else None,
                "execution": record,
            }
            cases.append(summary)
            print(
                json.dumps(
                    {
                        "case": case.name,
                        "exit_code": exit_code,
                        "reports": record.get("reports") if record else None,
                    }
                ),
                flush=True,
            )
        finally:
            # Only the uniquely named container created above; no volumes or user files removed.
            command(["docker", "rm", "-f", name])
        if digest(candidate) != PACKAGES[article]:
            raise ValueError("baseline_changed")
    after = health()
    report = {
        "version": "vh1-xpm-linux-feasibility-1.0",
        "run_id": run_id,
        "image": args.image,
        "private_directory": str(destination),
        "cases": cases,
        "before": before,
        "after": after,
        "services_unchanged": before == after,
        "production_deployed": False,
        "release_approved": False,
        "all_required_validations_completed": False,
    }
    (destination / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {"report": str(destination / "report.json"), "services_unchanged": before == after}
        )
    )


if __name__ == "__main__":
    main()
