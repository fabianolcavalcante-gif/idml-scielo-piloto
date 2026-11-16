"""Exact successor for the three catalog consumers replayed on the two journal inputs."""

import hashlib
import json

from ops.qualify_vh17_catalog_replay import BASELINE_REPORT, CATALOG_SOURCES

REPORT = "benchmarks/qualification/reports/vh17-catalog-regression-v1.json"
AUDIT = "ops/qualify_vh17_catalog_replay.py"
PIN = "32af42bbd8e746cf5a8d4e81d0e383b20ef5a6f7fd85cd702093c03df9e192f3"
DEPENDENCIES = (REPORT, AUDIT, BASELINE_REPORT, *CATALOG_SOURCES)


def source_matches(path, expected, reader):
    if path not in CATALOG_SOURCES:
        return False
    try:
        raw = reader(REPORT)
        if hashlib.sha256(raw).hexdigest() != PIN:
            return False
        proof = json.loads(raw)
        return (
            proof["before"][path] == expected
            and hashlib.sha256(reader(BASELINE_REPORT)).hexdigest() == proof["baseline_sha256"]
            and hashlib.sha256(reader(AUDIT)).hexdigest() == proof["audit_sha256"]
            and set(proof["cases"]) == {"esa-e20240086", "esa-e20240135"}
            and all(
                hashlib.sha256(reader(p)).hexdigest() == proof["after"][p] for p in CATALOG_SOURCES
            )
            and proof["release_approved"] is False
        )
    except (KeyError, ValueError, TypeError, OSError):
        return False
