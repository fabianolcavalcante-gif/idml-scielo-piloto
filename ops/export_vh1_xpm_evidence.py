"""Export private XPM logs/reports without copying its full runtime or article assets."""

import argparse
import re
import tarfile
from pathlib import Path

ROOT = Path("/opt/idml-platform/private/qualification")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_id")
    args = parser.parse_args()
    if not re.fullmatch(r"vh1-xpm-linux-[0-9]{8}T[0-9]{6}Z", args.run_id):
        raise ValueError("invalid_run")
    source = ROOT / args.run_id
    if source.resolve() != source or not (source / "report.json").is_file():
        raise ValueError("invalid_source")
    paths = [source / "report.json"]
    for case in sorted(source.glob("esa-*")):
        paths.extend(
            case / "work" / name for name in ("execution.json", "stdout.log", "stderr.log")
        )
        paths.extend((case / "work").rglob("xpm.html"))
    with (source / "evidence.tar.gz").open("xb") as output:
        with tarfile.open(fileobj=output, mode="w:gz") as archive:
            for path in paths:
                if path.is_symlink() or not path.is_relative_to(source) or not path.is_file():
                    raise ValueError("invalid_evidence")
                archive.add(path, arcname=path.relative_to(source).as_posix(), recursive=False)
    print(source / "evidence.tar.gz")


if __name__ == "__main__":
    main()
