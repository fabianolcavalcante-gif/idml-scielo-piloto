"""Inventory-only retention advice. Never remove/move or read backup payloads."""

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

REQUIRED = ("database.dump", "artifacts.tar.gz", "openclaw-state.tar.gz", "SHA256SUMS")
UTC = timezone.utc  # noqa: UP017 - host inventory supports VPS Python 3.10.


def inventory(root, *, now=None, keep_latest=7, keep_days=30, max_entries=10000):
    if keep_latest < 1 or keep_days < 1 or not 1 <= max_entries <= 10000:
        raise ValueError("invalid retention policy")
    now = now or datetime.now(UTC)
    result = {
        "version": "backup-retention-plan-1.0",
        "read_only": True,
        "complete": True,
        "checksums_verified": False,
        "restore_verified": False,
        "delete_authorized": False,
        "manual_review_candidates": [],
        "protected": 0,
        "unrecognized_or_incomplete": 0,
        "classification": {
            "noncanonical_name": 0,
            "unsafe_path": 0,
            "missing_or_empty_payload": 0,
            "future_timestamp": 0,
        },
        "missing_or_empty_by_file": dict.fromkeys(REQUIRED, 0),
    }
    candidates = []
    try:
        for index, directory in enumerate(root.iterdir()):
            if index >= max_entries:
                result["complete"] = False
                break
            try:
                stamp = datetime.strptime(directory.name, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
                if directory.name != stamp.strftime("%Y%m%dT%H%M%SZ"):
                    raise ValueError("noncanonical timestamp")
            except ValueError:
                result["unrecognized_or_incomplete"] += 1
                result["classification"]["noncanonical_name"] += 1
                continue
            reason = None
            if (
                directory.is_symlink()
                or not directory.resolve().is_relative_to(root.resolve())
                or not directory.is_dir()
            ):
                reason = "unsafe_path"
            elif not all(
                (directory / name).is_file()
                and not (directory / name).is_symlink()
                and (directory / name).stat().st_size > 0
                for name in REQUIRED
            ):
                reason = "missing_or_empty_payload"
            elif stamp > now:
                reason = "future_timestamp"
            if reason:
                if reason == "missing_or_empty_payload":
                    for name in REQUIRED:
                        payload = directory / name
                        if (
                            not payload.is_file()
                            or payload.is_symlink()
                            or payload.stat().st_size == 0
                        ):
                            result["missing_or_empty_by_file"][name] += 1
                result["unrecognized_or_incomplete"] += 1
                result["classification"][reason] += 1
                continue
            candidates.append((stamp, directory.name))
        if result["complete"]:
            for index, (stamp, name) in enumerate(sorted(candidates, reverse=True)):
                if index < keep_latest or stamp >= now - timedelta(days=keep_days):
                    result["protected"] += 1
                else:
                    result["manual_review_candidates"].append(name)
    except OSError:
        result["complete"] = False
    if not result["complete"]:
        result["manual_review_candidates"] = []
    result["policy"] = {"keep_latest": keep_latest, "keep_days": keep_days}
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    report = inventory(args.root)
    print(json.dumps(report, sort_keys=True))
    raise SystemExit(0 if report["complete"] else 3)
