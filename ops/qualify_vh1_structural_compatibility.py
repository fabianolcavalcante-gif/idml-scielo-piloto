"""Replay sealed native evidence at its original time; no renewed authorizations."""

import argparse
import base64
import hashlib
import json
import stat
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZipFile

from idml_foundation.pipeline.validation import OfflineJatsValidator
from idml_foundation.release.validation_engine import ValidationEngine
from idml_foundation.release.validator_registry import ValidatorChannel, load_validator_registry
from idml_foundation.release.xpm import XpmAttestation
from idml_foundation.release.xpm_query_semantics import QueryEvidence, assess_queries
from idml_foundation.services.xpm_runtime_compatibility import (
    WaytaExecutionEvidence,
    assess_runtime_compatibility,
)
from ops.gate_vh1_composed_sources import RUNTIME

ROOT = Path(__file__).resolve().parents[1]
SOURCES = (
    *RUNTIME,
    "src/idml_foundation/release/xpm_structural_compatibility.py",
    "src/idml_foundation/pipeline/validation.py",
    "src/idml_foundation/pipeline/jats_builder.py",
    "tests/test_xpm_structural_compatibility.py",
    "ops/qualify_vh1_structural_compatibility.py",
    "vendor/jats/1.3/JATS-journalpublishing1-3-mathml3.dtd",
)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--modern", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary_bytes = (args.matrix / "summary.json").read_bytes()
    # This particular qualified cohort is immutable, including all native receipts.
    assert sha(summary_bytes) == "54e1ee9ddb0291828aa9f9092482ffbadcd920c7e8ebf97296404d023349003c"
    summary = json.loads(summary_bytes)
    registry = load_validator_registry(ROOT / "config/validator-registry-vh1-composed.json")
    rows = []
    for case in summary["cases"]:
        key = case["article"] + "-" + case["mutation"]
        folder = args.matrix / key
        record = next(folder.rglob("evidence.json"))
        sealed = json.loads(record.read_bytes())
        report = (record.parent / "report.html").read_bytes()
        for path in (record, record.parent / "report.html"):
            metadata = path.stat()
            assert metadata.st_uid == 0 and stat.S_IMODE(metadata.st_mode) == 0o600
        assert base64.b64decode(sealed["report_base64"]) == report
        assert (
            sha(report)
            == sealed["attestation"]["report_sha256"]
            == case["assessment"]["report_sha256"]
        )
        scope = sealed["scope"]
        modern = args.modern / key
        xml, package = (
            (modern / "candidate.xml").read_bytes(),
            (modern / "candidate.zip").read_bytes(),
        )
        assert scope == json.loads((modern / "scope.json").read_bytes())
        assert sha(xml) == scope["xml_sha256"] and sha(package) == scope["package_sha256"]
        manifest = json.loads((modern / "modern-manifest.json").read_bytes())
        runs = []
        for name, digest in manifest["responses"].items():
            raw = (modern / (name + "-response.json")).read_bytes()
            assert sha(raw) == digest
            assert (folder / "inputs" / (name + "-response.json")).read_bytes() == raw
            spec = registry.select(name, ValidatorChannel.ACTIVE).command_specification()
            runs.append(
                ValidationEngine().ingest(
                    xml if spec.input_suffix == ".xml" else package, spec, raw
                )
            )
        old = case["assessment"].get("compatibility", {})
        if case["mutation"] != "baseline":
            # Re-run the mandatory local prerequisite with the current sources.
            with ZipFile(modern / "candidate.zip") as archive:
                offline = OfflineJatsValidator(ROOT / "vendor/jats/1.3").validate(
                    xml, asset_names=set(archive.namelist())
                )
            assert not offline.valid
            assert old.get("status") != "assessed"
            assert case["package_assessment"]["state"] == "blocked"
            rows.append(
                dict(
                    case=key,
                    structural_status="unavailable",
                    native_negative_blocked=True,
                    current_offline_valid=offline.valid,
                    current_offline_codes=sorted({i.code for i in offline.issues}),
                )
            )
            continue
        replay_at = datetime.fromisoformat(old["independent_assembled_at"])
        query = QueryEvidence.model_validate(sealed["query_evidence"])
        selected = assess_queries(
            xml=xml, evidence=query, scope=scope, report_sha256=sha(report), now=replay_at
        )
        arguments = dict(
            xml=xml,
            package=package,
            report=report,
            scope=scope,
            image=sealed["image"],
            attestation=XpmAttestation.model_validate(sealed["attestation"]),
            queries=query,
            selected=selected,
            now=replay_at,
            independent_runs=tuple(runs),
            wayta=WaytaExecutionEvidence.model_validate(sealed["wayta_evidence"]),
        )
        result = assess_runtime_compatibility(**arguments)
        assert result["structural_status"] == "assessed", result.get("structural_status")
        assert len(result["exceptions"]) == 8 and result["technical_errors_resolved"]
        assert result["unresolved_counts"] == dict(
            blocking_errors=0,
            fatal_errors=0,
            errors=0,
            warnings=case["assessment"]["counts"]["warnings"],
        )
        assert not result["homologation_ready"] and not result["release_approved"]
        # Mutate only the replay copy and re-attest as a synthetic executor; the
        # new diagnostic is unknown even when transport bindings are internally consistent.
        altered = report.replace(
            b"Parse/validation finished",
            b"Error: real additional error Parse/validation finished",
            1,
        )
        assert altered != report
        bad = dict(
            arguments,
            report=altered,
            attestation=arguments["attestation"].model_copy(update={"report_sha256": sha(altered)}),
        )
        rejected = assess_runtime_compatibility(**bad)
        assert rejected["structural_status"] == "unavailable"
        assert rejected["unresolved_counts"]["fatal_errors"] == 1
        rows.append(
            dict(
                case=key,
                xml_sha256=sha(xml),
                package_sha256=sha(package),
                report_sha256=sha(report),
                replay_at=replay_at.isoformat(),
                raw_counts=case["assessment"]["counts"],
                compatibility=result,
                additional_error_blocked=True,
                selected_query_status=selected.get("status"),
            )
        )
    result = dict(
        version="vh1-structural-native-replay-1.0",
        executed_at=datetime.now(UTC).isoformat(),
        native_summary_sha256=sha(summary_bytes),
        cases=rows,
        replay_original_time=True,
        new_native_executions=0,
        active_runtime_changed=False,
        homologation_ready=False,
        formal_xml_approved=False,
        source_sha256={p: sha((ROOT / p).read_bytes()) for p in SOURCES},
    )
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
    print(
        json.dumps(
            dict(
                qualified_articles=2,
                native_negative_cases=2,
                additional_error_controls=2,
                formal_xml_approved=False,
            )
        )
    )


if __name__ == "__main__":
    main()
