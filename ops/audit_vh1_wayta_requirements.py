"""Bind the Wayta decision to native probes, the norm and exact preserved candidates."""

import argparse
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
from idml_foundation.release.xpm_query_requirements import (
    NATIVE_PROOF_SHA256,
    NORMATIVE_SHA256,
    VENDOR_FILES,
    WaytaRequirementEvidence,
    assess_wayta_requirement,
)
from idml_foundation.release.xpm_sps_compatibility import (
    VALIDATORS,
    SpsCompatibilityEvidence,
)
from idml_foundation.release.xpm_sps_compatibility import (
    VENDOR_FILES as SPS_VENDOR_FILES,
)
from ops import gate_vh1_sps_compatibility as previous_gate
from ops.audit_vh1_sps_compatibility import ROOT, SOURCE, sha
from ops.audit_vh1_sps_compatibility import audit as audit_previous
from ops.gate_vh1_journal_metadata import REPORT as MODERN_REPORT

PROBE = "benchmarks/qualification/reports/vh1-wayta-native-v3.json"
SERVICE = "benchmarks/qualification/reports/vh1-wayta-service-v1.json"
NORM = ROOT / "benchmarks/private/output/vh1-history-spec-20261017T133639Z/sps-specification.txt"
SOURCES = (
    "src/idml_foundation/release/xpm_query_requirements.py",
    "ops/audit_vh1_wayta_requirements.py",
    "ops/probe_xpm_wayta.py",
    "ops/probe_wayta_https.py",
    "tests/test_xpm_query_requirements.py",
    "tests/test_wayta_service_probe.py",
)


def candidate_inputs(name, previous, modern, now):
    folder = SOURCE / name
    scope = json.loads((folder / "scope.json").read_bytes())
    authority = json.loads((folder / "incoming/doi-manifest.json").read_bytes())
    before = previous["base"]
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
    native = next(c for c in modern["cases"] if c["case"] == name)
    modern_sha = sha(MODERN_REPORT.read_bytes())
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
    return dict(
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
            vendor_sha256=SPS_VENDOR_FILES,
            independent_report_sha256=modern_sha,
            runs=runs,
        ),
    )


def audit():
    reader = lambda path: (ROOT / path).read_bytes()  # noqa: E731
    preserved = json.loads(previous_gate.REPORT.read_bytes())
    if not previous_gate.evaluate(preserved, reader)["passed"]:
        raise ValueError("previous_sps_proof_invalid")
    # Re-audit private native evidence and candidate bytes; JSON success alone is insufficient.
    previous = audit_previous()
    if previous["assessments"] != preserved["assessments"]:
        raise ValueError("previous_sps_assessments_changed")
    probe = json.loads(reader(PROBE))
    service = json.loads(reader(SERVICE))
    if (
        sha(NORM.read_bytes()) != NORMATIVE_SHA256
        or sha(reader(PROBE)) != NATIVE_PROOF_SHA256
        or probe["probe_sha256"] != sha(reader("ops/probe_xpm_wayta.py"))
        or probe["vendor_sha256"] != VENDOR_FILES
        or probe["network"] != "none"
        or probe["vendor_files_unchanged"] is not True
        or service["probe_sha256"] != sha(reader("ops/probe_wayta_https.py"))
    ):
        raise ValueError("wayta_authorities_invalid")
    if {c["case"]: c["result_count"] for c in probe["query_cases"]} != {
        "match": 1,
        "empty": 0,
        "malformed": 0,
        "absent": 0,
        "timeout": 0,
    }:
        raise ValueError("wayta_native_query_behavior_changed")
    modern = json.loads(MODERN_REPORT.read_bytes())
    results = {}
    now = datetime.now(UTC)
    for name, before in previous["assessments"].items():
        inputs = candidate_inputs(name, before, modern, now)
        evidence = WaytaRequirementEvidence(
            contract_version="wayta-requirement-evidence-1.0",
            scope=inputs["expected_scope"],
            normative_sha256=NORMATIVE_SHA256,
            native_proof_sha256=NATIVE_PROOF_SHA256,
            vendor_sha256=probe["vendor_sha256"],
            service_report_sha256=sha(reader(SERVICE)),
            observation=service["service_observation"],
        )
        result = assess_wayta_requirement(**inputs, wayta_evidence=evidence)
        if (
            result.base.model_dump(mode="json") != before
            or result.requirement != "advisory_for_qualified_profile"
        ):
            raise ValueError("wayta_qualification_failed")
        results[name] = result.model_dump(mode="json")
    return {
        "version": "vh1-wayta-requirements-1.0",
        "created_at": now.isoformat(),
        "source_sha256": {p: sha(reader(p)) for p in SOURCES},
        "previous_sps_proof_sha256": sha(previous_gate.REPORT.read_bytes()),
        "normative_sha256": NORMATIVE_SHA256,
        "native_probe_sha256": NATIVE_PROOF_SHA256,
        "service_report_sha256": sha(reader(SERVICE)),
        "native_query_cases": 5,
        "native_affiliation_cases": 18,
        "native_missing_country_gap": True,
        "assessments": results,
        "native_xpm_full_rerun": False,
        "candidate_changed": False,
        "vendor_changed": False,
        "active_application_changed": False,
        "homologation_ready": False,
        "release_approved": False,
        "outstanding": [
            "DOCTYPE_JATS_DELIVERY_DECISION",
            "EMBEDDED_XPM_PACKTOOLS_ERROR",
            "OTHER_REQUIRED_QUERIES",
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
    print(json.dumps({k: v["requirement"] for k, v in result["assessments"].items()}))
