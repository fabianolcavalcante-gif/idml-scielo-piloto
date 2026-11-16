"""Audit new journal candidates with original XPM, then derive exact-match exceptions."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from idml_foundation.release.xpm import XpmAttestation
from idml_foundation.release.xpm_compatibility import (
    IMAGE,
    TOOL_SHA256,
    VENDOR_COMPARISON_SHA256,
    XpmCompatibilityEvidence,
    assess_xpm_compatibility,
)
from ops import audit_vh1_xpm_online as native
from ops.qualify_vh1_journal_metadata import BASELINE, ROOT, verify_delta, verify_package


def audit(source, directory, expected_plan):
    raw_plan = native.sealed(source / "plan.json", expected_plan)
    plan = json.loads(raw_plan)
    for path, expected in plan["source_sha256"].items():
        native.sealed(ROOT / path, expected)
    for name, detail in plan["cases"].items():
        for path, expected in detail["files"].items():
            native.sealed(source / name / path, expected)
        if (
            verify_delta(
                (BASELINE / name / "candidate.xml").read_bytes(),
                (source / name / "candidate.xml").read_bytes(),
            )
            != detail["delta"]
        ):
            raise ValueError("delta_mismatch")
        if (
            verify_package(
                (BASELINE / name / "candidate.zip").read_bytes(),
                (source / name / "candidate.zip").read_bytes(),
            )
            != detail["unchanged_assets"]
        ):
            raise ValueError("assets_changed")
    # Reuse the entire qualified native audit, replacing only the explicitly bound inputs.
    before = native.BASELINE, native.PACKAGES
    try:
        native.BASELINE = source
        native.PACKAGES = {k: v["package_sha256"] for k, v in plan["cases"].items()}
        result = native.audit(directory)
    finally:
        native.BASELINE, native.PACKAGES = before
    if result["image"] != IMAGE:
        raise ValueError("image_mismatch")
    result["outstanding"] = [
        item for item in result["outstanding"] if item != "JOURNAL_CATALOGUE_METADATA_CORRECTIONS"
    ]
    if any(not f["matches"] for c in result["cases"] for f in c["catalogue_comparison"].values()):
        raise ValueError("journal_correction_unproven")
    probe = ROOT / "benchmarks/qualification/reports/vh1-xpm-doi-comparisons-v1.json"
    native.sealed(probe, "8144b908b87826e15d1287152ffcfea8e9fa32712df762f6a58e178e2cc38c3a")
    probe_result = json.loads(probe.read_bytes())
    if (
        not probe_result["vendor_files_unchanged"]
        or probe_result["vendor_module_sha256"] != VENDOR_COMPARISON_SHA256
    ):
        raise ValueError("native_comparison_unproven")
    now = datetime.now(UTC)
    assessments = {}
    for case in result["cases"]:
        if case["mutation"] != "baseline":
            continue
        name = case["article"]
        folder = source / name
        scope = json.loads((folder / "scope.json").read_bytes())
        authority = json.loads((folder / "incoming/doi-manifest.json").read_bytes())
        report = (directory / (name + "-baseline") / "work/input_xpm/errors/xpm.html").read_bytes()
        evidence = XpmCompatibilityEvidence(
            contract_version="xpm-compatibility-evidence-1.0",
            scope=scope,
            attestation=XpmAttestation(
                candidate_package_sha256=scope["package_sha256"],
                report_sha256=case["report_sha256"],
                tool_sha256=TOOL_SHA256,
                xpm_version="4.0.096",
                command_id=result["run_id"] + ":" + name,
                environment="same-vps-isolated-qualification",
            ),
            image=result["image"],
            vendor_comparison_sha256=VENDOR_COMPARISON_SHA256,
            crossref_sha256=authority["snapshot_sha256"],
            crossref_retrieved_at=authority["retrieved_at"],
            required_queries_complete=False,
        )
        assessment = assess_xpm_compatibility(
            xml=(folder / "candidate.xml").read_bytes(),
            package=(folder / "candidate.zip").read_bytes(),
            report=report,
            crossref=(folder / "incoming/crossref.json").read_bytes(),
            trusted=evidence,
            expected_scope=scope,
            now=now,
        )
        assessments[name] = assessment.model_dump(mode="json")
    sources = (
        "ops/audit_vh1_journal_xpm.py",
        "ops/run_vh1_journal_xpm.py",
        "src/idml_foundation/release/xpm_compatibility.py",
    )
    for name in ("run_vh1_journal_xpm.py", "qualify_vh1_xpm_online.py", "qualify_vh1_xpm_linux.py"):
        native.sealed(source / name, native.digest(ROOT / "ops" / name))
    return {
        "version": "vh1-journal-xpm-compatibility-1.0",
        "created_at": now.isoformat(),
        "plan_sha256": expected_plan,
        "native": result,
        "doi_comparison_probe_sha256": native.digest(probe),
        "assessments": assessments,
        "source_sha256": {p: native.digest(ROOT / p) for p in sources},
        "homologation_ready": False,
        "release_approved": False,
        "active_application_changed": False,
        "outstanding": [
            "SPS_1_10_JATS_1_3_DELIVERY_POLICY",
            "LEGACY_DATE_AND_SPS_RULES",
            "WAYTA_QUERY_DENIED",
            "SUPERVISED_WEB_INTEGRATION_AND_HARDENING",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("directory", type=Path)
    parser.add_argument("plan_sha256")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.source, args.directory, args.plan_sha256)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                k: {"exceptions": len(v["exceptions"]), "unresolved": v["unresolved_counts"]}
                for k, v in result["assessments"].items()
            }
        )
    )
