"""Read-only, allowlisted runtime fingerprints for the functional homologation baseline."""

import argparse
import hashlib
import json
from pathlib import Path

TREES = ("src/idml_foundation", "profiles", "schemas", "prompts", "migrations")
FILES = ("requirements.lock", "pyproject.toml", "config/validator-registry-v1.json")
SUFFIXES = {".py", ".json", ".md", ".html", ".js", ".css"}


def inventory(root):
    root = root.resolve(strict=True)
    paths = [root / name for name in FILES]
    for name in TREES:
        paths.extend(
            p
            for p in (root / name).rglob("*")
            if p.suffix in SUFFIXES and "__pycache__" not in p.parts and p.is_file()
        )
    fingerprints = {}
    for path in sorted(paths):
        if path.is_symlink() or not path.resolve().is_relative_to(root) or not path.is_file():
            raise ValueError("unsafe_or_missing_runtime_source")
        fingerprints[path.relative_to(root).as_posix()] = hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
    return {
        "version": "homologation-source-inventory-1.0",
        "scope": [*TREES, *FILES],
        "sha256": fingerprints,
        "fingerprint": hashlib.sha256(
            json.dumps(fingerprints, sort_keys=True).encode()
        ).hexdigest(),
        "ready_for_expert": False,
    }


def compare(candidate, deployed):
    if candidate["scope"] != deployed["scope"]:
        raise ValueError("incompatible_inventory_scope")
    current, previous = candidate["sha256"], deployed["sha256"]
    return {
        "candidate_fingerprint": candidate["fingerprint"],
        "deployed_fingerprint": deployed["fingerprint"],
        "added": sorted(current.keys() - previous.keys()),
        "removed": sorted(previous.keys() - current.keys()),
        "changed": sorted(k for k in current.keys() & previous.keys() if current[k] != previous[k]),
        "unchanged": sum(current[k] == previous[k] for k in current.keys() & previous.keys()),
        "ready_for_expert": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--deployed", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = inventory(args.root)
    if args.deployed:
        report["comparison"] = compare(report, json.loads(args.deployed.read_text()))
    output = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
