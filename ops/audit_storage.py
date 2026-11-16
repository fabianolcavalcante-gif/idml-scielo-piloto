"""Read-only, bounded storage alerts. Never repair, unlink, or claim a stable snapshot."""

import argparse
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from idml_foundation.database import create_database_engine
from idml_foundation.models import Artifact
from idml_foundation.settings import Settings

KEY = re.compile(r"^([0-9a-f-]{36})/([0-9a-f]{2})/([0-9a-f]{64})$")


def valid_key(key, tenant, digest):
    try:
        if str(UUID(tenant)) != tenant:
            return False
    except (ValueError, TypeError, AttributeError):
        return False
    match = KEY.fullmatch(key)
    return bool(match and match[1] == tenant and match[2] == digest[:2] and match[3] == digest)


def audit_storage(db, settings, *, max_entries=50000, max_records=50000, timeout=30):
    if not 1 <= max_entries <= 100000 or not 1 <= max_records <= 100000 or not 0 < timeout <= 120:
        raise ValueError("invalid audit budget")
    started = time.monotonic()
    root = settings.artifact_root
    report = {
        "version": "storage-audit-1.0",
        "read_only": True,
        "consistency": "best_effort",
        "hashes_verified": False,
        "complete": True,
        "alerts": [],
        "counts": {
            "registered": 0,
            "files": 0,
            "orphan_candidates": 0,
            "missing": 0,
            "size_mismatch": 0,
            "unsafe_entries": 0,
            "invalid_records": 0,
            "tenants_warning": 0,
            "tenants_full": 0,
        },
        "restricted_content_emitted": False,
        "policy": {
            "tenant_quota_bytes": settings.artifact_tenant_quota_bytes,
            "tenant_max_files": settings.artifact_tenant_max_files,
            "disk_reserve_bytes": settings.artifact_disk_reserve_bytes,
        },
    }
    counts = report["counts"]
    expected = {}
    rows = db.execute(
        select(
            Artifact.organization_id, Artifact.storage_key, Artifact.sha256, Artifact.size_bytes
        ).limit(max_records + 1)
    )
    for index, row in enumerate(rows):
        if index == max_records or time.monotonic() - started > timeout:
            report["complete"] = False
            report["alerts"].append("database_scan_budget")
            break
        counts["registered"] += 1
        if not valid_key(row.storage_key, row.organization_id, row.sha256) or row.size_bytes < 1:
            counts["invalid_records"] += 1
        else:
            expected[row.storage_key] = row.size_bytes
    rows.close()
    try:
        free = shutil.disk_usage(root).free
        report["disk_free_bytes"] = free
        if free < settings.artifact_disk_reserve_bytes:
            report["alerts"].append("disk_reserve_critical")
        elif free < settings.artifact_disk_reserve_bytes + 2 * settings.upload_max_bytes:
            report["alerts"].append("disk_reserve_warning")
        if not root.is_dir():
            raise OSError("unavailable root")
        seen, usage = {}, {}
        pending = [(root, 0, None)]
        visited = 0
        while pending and report["complete"]:
            directory, depth, tenant = pending.pop()
            with os.scandir(directory) as children:
                for child in children:
                    visited += 1
                    if visited > max_entries or time.monotonic() - started > timeout:
                        report["complete"] = False
                        report["alerts"].append("filesystem_scan_budget")
                        break
                    path = Path(child.path)
                    if child.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
                        counts["unsafe_entries"] += 1
                        continue
                    if depth == 0 and child.name in {".storage-budget.lock", ".upload-admission"}:
                        expected_type = (
                            child.is_file(follow_symlinks=False)
                            if child.name == ".storage-budget.lock"
                            else child.is_dir(follow_symlinks=False)
                        )
                        if not expected_type:
                            counts["unsafe_entries"] += 1
                        continue
                    if child.is_dir(follow_symlinks=False):
                        if depth == 0:
                            try:
                                if str(UUID(child.name)) != child.name:
                                    raise ValueError("noncanonical")
                            except ValueError:
                                counts["unsafe_entries"] += 1
                                continue
                            pending.append((path, 1, child.name))
                        elif depth == 1 and re.fullmatch("[0-9a-f]{2}", child.name):
                            pending.append((path, 2, tenant))
                        else:
                            counts["unsafe_entries"] += 1
                    elif child.is_file(follow_symlinks=False) and tenant is not None:
                        size = child.stat(follow_symlinks=False).st_size
                        seen[path.relative_to(root).as_posix()] = size
                        total, number = usage.get(tenant, (0, 0))
                        usage[tenant] = (total + size, number + 1)
                        counts["files"] += 1
                    else:
                        counts["unsafe_entries"] += 1
        if report["complete"]:
            counts["orphan_candidates"] = len(seen.keys() - expected.keys())
            counts["missing"] = len(expected.keys() - seen.keys())
            counts["size_mismatch"] = sum(
                seen[k] != expected[k] for k in seen.keys() & expected.keys()
            )
            for size, number in usage.values():
                if (
                    size >= settings.artifact_tenant_quota_bytes
                    or number >= settings.artifact_tenant_max_files
                ):
                    counts["tenants_full"] += 1
                elif (
                    size * 5 >= settings.artifact_tenant_quota_bytes * 4
                    or number * 5 >= settings.artifact_tenant_max_files * 4
                ):
                    counts["tenants_warning"] += 1
    except OSError:
        report["complete"] = False
        report["alerts"].append("filesystem_unavailable")
    critical = (
        counts["missing"]
        or counts["size_mismatch"]
        or counts["unsafe_entries"]
        or counts["invalid_records"]
        or counts["tenants_full"]
        or "disk_reserve_critical" in report["alerts"]
    )
    warning = (
        counts["orphan_candidates"]
        or counts["tenants_warning"]
        or "disk_reserve_warning" in report["alerts"]
    )
    report["severity"] = (
        "critical"
        if critical
        else "unknown"
        if not report["complete"]
        else "warning"
        if warning
        else "ok"
    )
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-entries", type=int, default=50000)
    parser.add_argument("--max-records", type=int, default=50000)
    parser.add_argument("--timeout", type=float, default=30)
    args = parser.parse_args()
    engine = None
    try:
        settings = Settings()
        audit_settings = SimpleNamespace(
            artifact_root=settings.artifact_root,
            upload_max_bytes=settings.upload_max_bytes,
            artifact_tenant_quota_bytes=getattr(
                settings, "artifact_tenant_quota_bytes", 2 * 1024**3
            ),
            artifact_tenant_max_files=getattr(settings, "artifact_tenant_max_files", 10000),
            artifact_disk_reserve_bytes=getattr(
                settings, "artifact_disk_reserve_bytes", 5 * 1024**3
            ),
        )
        engine = create_database_engine(settings)
        with engine.connect() as connection, connection.begin():
            if connection.dialect.name == "postgresql":
                connection.exec_driver_sql("SET TRANSACTION READ ONLY")
                connection.exec_driver_sql("SET LOCAL statement_timeout = '5000ms'")
            elif connection.dialect.name == "sqlite":
                connection.exec_driver_sql("PRAGMA query_only = ON")
            else:
                raise ValueError("unsupported audit database")
            with Session(bind=connection) as db:
                report = audit_storage(
                    db,
                    audit_settings,
                    max_entries=args.max_entries,
                    max_records=args.max_records,
                    timeout=args.timeout,
                )
                report["policy_source"] = (
                    "runtime_settings"
                    if hasattr(settings, "artifact_tenant_quota_bytes")
                    else "candidate_defaults_for_legacy_runtime"
                )
    except Exception:
        report = {
            "version": "storage-audit-1.0",
            "read_only": True,
            "complete": False,
            "severity": "unknown",
            "alerts": ["audit_unavailable"],
            "restricted_content_emitted": False,
        }
    finally:
        if engine is not None:
            engine.dispose()
    print(json.dumps(report, sort_keys=True))
    return {"ok": 0, "warning": 1, "critical": 2, "unknown": 3}[report["severity"]]


if __name__ == "__main__":
    sys.exit(main())
