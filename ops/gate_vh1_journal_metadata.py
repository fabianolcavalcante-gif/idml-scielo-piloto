"""Verify the native journal-only successor; never approve the XML or release."""

import hashlib
import json
from collections import Counter
from functools import lru_cache
from pathlib import Path

from ops.gate_vh1_doctype import DEPENDENCIES as DOCTYPE_DEPENDENCIES
from ops.gate_vh1_doctype import code_matches
from ops.gate_vh1_doctype import source_matches as doctype_source_matches
from ops.gate_vh17_catalog_sources import DEPENDENCIES as CATALOG_DEPENDENCIES
from ops.gate_vh17_catalog_sources import source_matches as catalog_source_matches
from ops.gate_vh17_scoped_sources import DEPENDENCIES as SCOPED_DEPENDENCIES
from ops.qualify_vh1_journal_metadata import RUNNER, SOURCES

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "benchmarks/qualification/reports/vh1-journal-metadata-linux-v1.json"
PREVIOUS = ROOT / "benchmarks/qualification/reports/vh1-final-validation-linux-v2.json"
NATIVE = "61c57c43c081a537fc95d12c1c1e802a092cbf5ee3a26c093debcfb89d3ad66a"
PRIOR = "6f4d474012bb2d5bfc02a47aec8be1156a7baa337f5358cfd266193aa3f48269"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def fixture_matches(path, expected, reader):
    """Reconstruct the attested test file by reversing only its ZIP timestamp fix."""
    if path != "tests/test_xpm_compatibility.py":
        return False
    current = reader(path)
    edits = (
        (b"from zipfile import ZipFile, ZipInfo", b"from zipfile import ZipFile"),
        (
            b'archive.writestr(ZipInfo("article.xml", (2000, 1, 1, 0, 0, 0)), xml)',
            b'archive.writestr("article.xml", xml)',
        ),
    )
    for replacement, original in edits:
        if current.count(replacement) != 1:
            return False
        current = current.replace(replacement, original, 1)
    return sha(current) == expected


def evaluate(report, previous, reader):
    checks = {}
    try:
        plan = report["qualification"]
        checks["native_identity"] = (
            sha(json.dumps(report, sort_keys=True, indent=2).encode()) == NATIVE
            and sha(json.dumps(previous, sort_keys=True, indent=2).encode()) == PRIOR
            and report["version"] == "vh1-history-linux-1.0"
            and plan["version"] == "vh1-journal-metadata-local-1.0"
        )
        checks["current_sources"] = (
            set(plan["source_sha256"]) == set(SOURCES)
            and plan["before_source_sha256"] == previous["qualification"]["source_sha256"]
            and all(
                doctype_source_matches(p, h, reader)
                or catalog_source_matches(p, h, reader)
                or fixture_matches(p, h, reader)
                for p, h in plan["source_sha256"].items()
            )
            and code_matches(plan["code_sha256"], RUNNER, reader)
            and plan["registry_sha256"] == sha(reader("config/validator-registry-vh1-history.json"))
        )
        checks["not_release"] = (
            all(
                obj[k] is False
                for obj in (report, plan)
                for k in ("formal_xml_approved", "active_application_changed")
            )
            and plan["gold_read"] is False
            and plan["autonomous_application"] is False
            and plan["human_review_required"] is True
        )
        checks["cases"] = len(report["cases"]) == 2 and {c["case"] for c in report["cases"]} == {
            "esa-e20240086",
            "esa-e20240135",
        }
        for case in report["cases"]:
            name = case["case"]
            detail = plan["cases"][name]
            old = previous["qualification"]["cases"][name]
            checks[name + "/preservation"] = (
                detail["before_xml_sha256"] == old["xml_sha256"]
                and detail["before_package_sha256"] == old["package_sha256"]
                and detail["unchanged_assets"] == old["unchanged_assets"]
                and detail["source_idml_sha256"] == old["source_idml_sha256"]
                and detail["offline_valid"] is True
                and detail["deterministic"] is True
                and detail["delta"]["all_other_xml_unchanged"] is True
                and {d["field"] for d in detail["delta"]["fields"]}
                == (
                    {"front/journal-meta/publisher/publisher-name"}
                    | (
                        {"front/journal-meta/journal-title-group/journal-title"}
                        if name.endswith("86")
                        else set()
                    )
                )
            )
            old_case = next(c for c in previous["cases"] if c["case"] == name)
            checks[name + "/tools"] = len(case["validators"]) == 2 and {
                v["name"] for v in case["validators"]
            } == {"packtools", "spsvalidator"}
            for run in case["validators"]:
                tool = run["name"]
                before = next(v for v in old_case["validators"] if v["name"] == tool)
                checks[name + "/" + tool] = (
                    run["image_id"] == before["image_id"]
                    and run["candidate_sha256"]
                    == detail["xml_sha256" if tool == "packtools" else "package_sha256"]
                    and run["findings"] == before["findings"]
                    and run["counts"]
                    == dict(Counter(f["response"] for f in run["findings"]))
                    == {"warning": 5}
                    and run["authority_evidence"]
                    == {
                        **before["authority_evidence"],
                        "binding": {
                            "bundle_sha256": detail["files"]["incoming/manifest.json"],
                            "grant_sha256": detail["files"]["grant.json"],
                            "scope_sha256": detail["scope_sha256"],
                        },
                    }
                    and run["history_policy_evidence"]
                    == {
                        **before["history_policy_evidence"],
                        "candidate_sha256": run["candidate_sha256"],
                    }
                )
    except (KeyError, ValueError, TypeError, OSError, StopIteration):
        checks["complete_evidence"] = False
    return {
        "passed": bool(checks) and all(checks.values()),
        "checks": checks,
        "formal_xml_approved": False,
        "active_application_changed": False,
    }


def inputs():
    return json.loads(REPORT.read_bytes()), json.loads(PREVIOUS.read_bytes())


@lru_cache(maxsize=2)
def _evaluate_snapshot(raw, previous_raw, files):
    # Pure, bounded cache keyed by all actual bytes, never mtime or reader identity.
    # Each caller still reads every required current source; any mutation invalidates it.
    return evaluate(json.loads(raw), json.loads(previous_raw), dict(files).__getitem__)["passed"]


def source_matches(path, expected, reader):
    current = sha(reader(path))
    if current == expected:
        return True
    if fixture_matches(path, expected, reader):
        return True
    if doctype_source_matches(path, expected, reader) or catalog_source_matches(
        path, expected, reader
    ):
        return True
    try:
        raw = reader(REPORT.relative_to(ROOT).as_posix())
        previous_raw = reader(PREVIOUS.relative_to(ROOT).as_posix())
        report = json.loads(raw)
        previous = json.loads(previous_raw)
        plan = report["qualification"]
        return (
            # The exact pinned predecessor contains its own native transition.
            # This includes the source-evolution helper changed in both increments.
            expected
            in {
                plan["before_source_sha256"].get(path),
                previous["qualification"]["before_source_sha256"].get(path),
            }
            and doctype_source_matches(path, plan["source_sha256"].get(path), reader)
            and _evaluate_snapshot(
                raw,
                previous_raw,
                tuple(
                    (p, reader(p))
                    for p in sorted(
                        set(SOURCES)
                        | set(DOCTYPE_DEPENDENCIES)
                        | set(CATALOG_DEPENDENCIES)
                        | set(SCOPED_DEPENDENCIES)
                        | set(RUNNER.values())
                        | {"config/validator-registry-vh1-history.json"}
                    )
                ),
            )
        )
    except (KeyError, ValueError, TypeError, OSError):
        return False


if __name__ == "__main__":
    result = evaluate(*inputs(), lambda p: (ROOT / p).read_bytes())
    print(json.dumps(result))
    raise SystemExit(0 if result["passed"] else 1)
