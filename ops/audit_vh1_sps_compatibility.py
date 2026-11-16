"""Re-evaluate preserved exact candidates with qualified SPS rules, without rerunning XPM."""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from idml_foundation.release.validation_engine import UnifiedIssue, ValidatorRun
from idml_foundation.release.xpm import XpmAttestation
from idml_foundation.release.xpm_compatibility import (
    IMAGE,
    TOOL_SHA256,
    VENDOR_COMPARISON_SHA256,
    XpmCompatibilityEvidence,
)
from idml_foundation.release.xpm_sps_compatibility import (
    VALIDATORS,
    VENDOR_FILES,
    SpsCompatibilityEvidence,
    assess_xpm_sps_compatibility,
)
from ops import gate_vh1_journal_metadata as modern_gate
from ops import gate_vh1_journal_xpm as xpm_gate
from ops.audit_vh1_journal_xpm import audit as original_audit

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "benchmarks/private/output/vh1-journal-metadata-20261016T165920Z"
PLAN = "478ea3ee76e7ccee3db39d0d05c5d6c84fb8f643a703cdd0de9665afa64ba784"
PROBE = "benchmarks/qualification/reports/vh1-xpm-sps-dates-probe-v1.json"
PROBE_SHA = "e5f3bfeb57e8c06b60b25cca94d7c86611ebea1bf27bb14d20337c4d980a44de"
SOURCES = (
    "src/idml_foundation/release/xpm_sps_compatibility.py",
    "ops/audit_vh1_sps_compatibility.py",
    "ops/probe_xpm_sps_dates.py",
    "tests/test_xpm_sps_compatibility.py",
)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def audit():
    reader = lambda path: (ROOT / path).read_bytes()  # noqa: E731
    modern, previous = modern_gate.inputs()
    historical = json.loads(xpm_gate.REPORT.read_bytes())
    if not modern_gate.evaluate(modern, previous, reader)["passed"]:
        raise ValueError("modern_native_evidence_failed")
    if not xpm_gate.evaluate(historical, reader)["passed"]:
        raise ValueError("xpm_native_evidence_failed")
    # Full native/private-input audit is still required; historical JSON alone is not an execution.
    original = original_audit(SOURCE, SOURCE / "xpm-evidence", PLAN)
    probe = json.loads(reader(PROBE))
    if (
        sha(reader(PROBE)) != PROBE_SHA
        or probe["vendor_sha256"] != VENDOR_FILES
        or probe["probe_sha256"] != sha(reader("ops/probe_xpm_sps_dates.py"))
        or probe["vendor_files_unchanged"] is not True
        or probe["network"] != "none"
    ):
        raise ValueError("native_probe_invalid")
    modern_sha = sha(modern_gate.REPORT.read_bytes())
    now = datetime.now(UTC)
    results = {}
    for name, before in original["assessments"].items():
        folder = SOURCE / name
        scope = json.loads((folder / "scope.json").read_bytes())
        authority = json.loads((folder / "incoming/doi-manifest.json").read_bytes())
        native = next(c for c in modern["cases"] if c["case"] == name)
        runs = tuple(
            ValidatorRun(
                name=v["name"],
                version=VALIDATORS[v["name"]][0],
                tool_sha256=v["image_id"].removeprefix("sha256:"),
                status="completed",
                candidate_sha256=v["candidate_sha256"],
                profile_id="sps-1.10/jats-1.3",
                adapter_contract="1.1.0",
                environment="same-vps-isolated-qualification",
                sanitized_output_sha256=modern_sha,
                issues=tuple(
                    UnifiedIssue(
                        validator=v["name"],
                        severity=f["response"],
                        category="deterministic",
                        code=f["code"],
                        message=f["message"],
                        location=f.get("path"),
                    )
                    for f in v["findings"]
                ),
            )
            for v in native["validators"]
        )
        trusted = XpmCompatibilityEvidence(
            contract_version="xpm-compatibility-evidence-1.0",
            scope=scope,
            image=IMAGE,
            attestation=XpmAttestation(
                candidate_package_sha256=scope["package_sha256"],
                report_sha256=before["original"]["report_sha256"],
                tool_sha256=TOOL_SHA256,
                xpm_version="4.0.096",
                command_id=before["original"]["command_id"],
                environment=before["original"]["environment"],
            ),
            vendor_comparison_sha256=VENDOR_COMPARISON_SHA256,
            crossref_sha256=authority["snapshot_sha256"],
            crossref_retrieved_at=authority["retrieved_at"],
            required_queries_complete=False,
        )
        result = assess_xpm_sps_compatibility(
            xml=(folder / "candidate.xml").read_bytes(),
            package=(folder / "candidate.zip").read_bytes(),
            report=(
                SOURCE / "xpm-evidence" / (name + "-baseline") / "work/input_xpm/errors/xpm.html"
            ).read_bytes(),
            crossref=(folder / "incoming/crossref.json").read_bytes(),
            trusted=trusted,
            expected_scope=scope,
            now=now,
            sps_evidence=SpsCompatibilityEvidence(
                contract_version="xpm-sps-compatibility-evidence-1.0",
                scope=scope,
                vendor_sha256=probe["vendor_sha256"],
                independent_report_sha256=modern_sha,
                runs=runs,
            ),
        )
        if result.base.model_dump(mode="json") != before or len(result.exceptions) != 4:
            raise ValueError("sps_qualification_expectation_failed")
        results[name] = result.model_dump(mode="json")
    return {
        "version": "vh1-sps-compatibility-1.0",
        "created_at": now.isoformat(),
        "source_sha256": {p: sha(reader(p)) for p in SOURCES},
        "probe_sha256": sha(reader(PROBE)),
        "native_probe_cases": len(probe["cases"]),
        "independent_report_sha256": modern_sha,
        "previous_xpm_proof_sha256": sha(xpm_gate.REPORT.read_bytes()),
        "native_run_id": original["native"]["run_id"],
        "plan_sha256": PLAN,
        "assessments": results,
        "native_xpm_rerun": False,
        "candidate_changed": False,
        "vendor_changed": False,
        "active_application_changed": False,
        "homologation_ready": False,
        "release_approved": False,
        "outstanding": [
            "DOCTYPE_JATS_DELIVERY_DECISION",
            "EMBEDDED_XPM_PACKTOOLS_ERROR",
            "REQUIRED_WAYTA_QUERIES",
            "SUPERVISED_WEB_INTEGRATION",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit()
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print(json.dumps({k: v["unresolved_counts"] for k, v in result["assessments"].items()}))
