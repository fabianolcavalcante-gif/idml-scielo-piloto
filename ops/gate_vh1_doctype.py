"""Only the audited, exact MathML3 header successor can supersede the old builder."""

import hashlib
import json
from functools import lru_cache

from ops.audit_vh1_doctype import SOURCES
from ops.gate_vh17_scoped_sources import source_matches as scoped_source_matches

REPORT = "benchmarks/qualification/reports/vh17-doctype-native-v1.json"
AUDIT = "ops/audit_vh1_doctype.py"
BUILDER = "src/idml_foundation/pipeline/jats_builder.py"
PACKAGE_VALIDATION = "src/idml_foundation/services/package_validation.py"
NATIVE_SHA256 = "f84e45e10d1eb4fc77e00d1a54bb774cf65c4f9ca459113b4a16f62624fa77de"
DEPENDENCIES = (*SOURCES, AUDIT, REPORT)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


@lru_cache(maxsize=2)
def _qualified_snapshot(raw, audit, files):
    if sha(raw) != NATIVE_SHA256:
        return False
    proof = json.loads(raw)
    return (
        proof["version"] == "vh1-doctype-native-successor-1.0"
        and proof["formal_xml_approved"] is False
        and proof["active_application_changed"] is False
        and proof["historical_reports_modified"] is False
        and proof["compatibility_exceptions_added"] == 0
        and set(proof["source_sha256"]) == set(SOURCES)
        and all(sha(data) == proof["source_sha256"][p] for p, data in files)
        and sha(audit) == proof["audit_sha256"]
    )


def qualified(reader):
    try:
        # Read every byte again; the bounded cache never uses reader identity or mtime.
        return _qualified_snapshot(
            reader(REPORT), reader(AUDIT), tuple((p, reader(p)) for p in SOURCES)
        )
    except (KeyError, ValueError, TypeError, OSError):
        return False


def source_matches(path, expected, reader):
    current = sha(reader(path))
    if current == expected:
        return True
    if scoped_source_matches(path, expected, reader):
        return True
    if path not in {BUILDER, PACKAGE_VALIDATION} or not qualified(reader):
        return False
    proof = json.loads(reader(REPORT))
    before = "before_builder_sha256" if path == BUILDER else "before_package_validation_sha256"
    return expected == proof[before] and current == proof["source_sha256"][path]


def code_matches(expected, mapping, reader):
    return set(expected) == set(mapping) and all(
        source_matches(path, expected[name], reader) for name, path in mapping.items()
    )
