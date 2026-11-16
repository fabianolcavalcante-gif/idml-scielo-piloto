"""Read-only audit of native DOCTYPE experiments; emit a content-free successor proof."""

import argparse
import hashlib
import json
import stat
from pathlib import Path
from zipfile import ZipFile

from idml_foundation.release.validation_engine import ValidationEngine
from idml_foundation.release.validator_registry import ValidatorChannel, load_validator_registry
from idml_foundation.services.package_validation import assess_package
from idml_foundation.services.scoped_validator_transport import check_evidence
from ops.qualify_vh1_doctype import ARTICLES, BASE, MODERN_MATRIX, OLD, tree

SOURCES = (
    "src/idml_foundation/pipeline/jats_builder.py",
    "src/idml_foundation/pipeline/validation.py",
    "ops/qualify_vh1_doctype.py",
    "ops/qualify_vh1_composed.py",
    "ops/probe_xpm_doctype.py",
    "tests/test_jats_doctype.py",
    "config/validator-registry-vh1-composed.json",
    "vendor/jats/1.3/JATS-journalpublishing1-3-mathml3.dtd",
    "vendor/jats/1.3/catalog-jats-v1-3-no-base.xml",
    "src/idml_foundation/services/package_validation.py",
)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def audit(root, source):
    plan = json.loads((root / "inputs/plan.json").read_bytes())
    native = json.loads((root / "native/doctype.json").read_bytes())
    assert native["probe_sha256"] == sha((source / "ops/probe_xpm_doctype.py").read_bytes())
    assert native["vendor_files_unchanged"] and native["input_unchanged"]
    assert native["network"] == "none" and native["compatibility_exceptions_added"] == 0
    assert len(native["cases"]) == len(plan["cases"]) == 6
    for row in native["cases"]:
        expected = next(c for c in plan["cases"] if c["case"] == row["case"])
        assert row["xml_sha256"] == expected["xml_sha256"]
        for kind, suffix in [("dtd", "txt"), ("style", "html")]:
            path = root / "native" / row["case"] / (kind + "." + suffix)
            assert sha(path.read_bytes()) == row[kind + "_report_sha256"]
        assert row["dtd_valid"] is False and row["style_counts"] == [0, 1, 0]
        assert row["fallback_jats11"] and row["style_sps_unsupported"]
    registry = load_validator_registry(source / "config/validator-registry-vh1-composed.json")
    results = []
    for article, variant in MODERN_MATRIX:
        case = article + "-" + variant
        folder = root / "inputs" / case
        detail = next(c for c in plan["cases"] if c["case"] == case)
        xml = (folder / "candidate.xml").read_bytes()
        package = (folder / "candidate.zip").read_bytes()
        assert sha(xml) == detail["xml_sha256"] and sha(package) == detail["package_sha256"]
        with ZipFile(folder / "candidate.zip") as archive:
            conversion = json.loads(archive.read("conversion-manifest.json"))
            assert all(sha(archive.read(f["name"])) == f["sha256"] for f in conversion["files"])
            with ZipFile(BASE / article / "candidate.zip") as old:
                for name in archive.namelist():
                    if not name.endswith(".xml") and name != "conversion-manifest.json":
                        assert archive.read(name) == old.read(name)
        if variant == "corrected":
            old_xml = (BASE / article / "candidate.xml").read_bytes()
            assert tree(xml) == tree(old_xml) and detail["rebuilt_with_current_builder"]
            assert old_xml.replace(OLD, OLD.replace(b"DTD v1.3", b"DTD with MathML3 v1.3")) == xml
        scope = json.loads((folder / "scope.json").read_bytes())
        manifest = json.loads((folder / "modern-manifest.json").read_bytes())
        assert manifest["scope"] == scope
        assert scope["xml_sha256"] == sha(xml) and scope["package_sha256"] == sha(package)
        runs = []
        validated = {}
        for name in ("packtools", "spsvalidator"):
            spec = registry.select(name, ValidatorChannel.ACTIVE).command_specification()
            candidate = xml if name == "packtools" else package
            if name in manifest["failures"]:
                assert variant == "wrong_version" and name not in manifest["responses"]
                runs.append(
                    dict(name=name, status="failed", failure_code=manifest["failures"][name])
                )
                validated[name] = ValidationEngine().unavailable(
                    name,
                    spec.version,
                    candidate,
                    "native-execution-failed",
                    tool_sha256=spec.tool_sha256,
                )
                continue
            path = folder / (name + "-response.json")
            assert path.stat().st_uid == 0 and stat.S_IMODE(path.stat().st_mode) == 0o600
            raw = path.read_bytes()
            assert sha(raw) == manifest["responses"][name]
            envelope = json.loads(raw)
            evidence = check_evidence(envelope["result"]["authority_evidence"], scope)
            assert evidence["binding"]["grant_sha256"] == sha((folder / "grant.json").read_bytes())
            assert evidence["binding"]["bundle_sha256"] == sha(
                (folder / "incoming/manifest.json").read_bytes()
            )
            run = ValidationEngine().ingest(candidate, spec, raw)
            validated[name] = run
            assert run.status == "completed" and not run.failure_code
            assert run.counts == dict(
                blocking=0, critical=0, error=int(variant == "invalid_fn"), warning=5
            )
            runs.append(
                dict(
                    name=name,
                    status=run.status,
                    counts=run.counts,
                    receipt_sha256=sha(raw),
                    candidate_sha256=run.candidate_sha256,
                    tool_sha256=run.tool_sha256,
                    version=run.version,
                )
            )

        def executor(candidate, specification, current_runs=validated):
            run = current_runs[specification.name]
            assert run.candidate_sha256 == sha(candidate)
            return run

        formal = assess_package(
            xml=xml,
            package=package,
            expected_scope=scope,
            registry_path=source / "config/validator-registry-vh1-composed.json",
            executor=executor,
        )
        expected_state = "validation-unavailable" if variant == "wrong_version" else "blocked"
        assert formal["state"] == expected_state and formal["ready_for_scielo"] is False
        results.append(
            dict(
                case=case,
                detail=detail,
                validators=runs,
                formal_state=formal["state"],
                ready_for_scielo=False,
            )
        )
    previous = json.loads(
        (
            source / "benchmarks/qualification/reports/vh1-journal-metadata-linux-v1.json"
        ).read_bytes()
    )
    builder = SOURCES[0]
    return dict(
        version="vh1-doctype-native-successor-1.0",
        native_plan_sha256=sha((root / "inputs/plan.json").read_bytes()),
        native_probe=native,
        source_sha256={p: sha((source / p).read_bytes()) for p in SOURCES},
        audit_sha256=sha(Path(__file__).read_bytes()),
        before_builder_sha256=previous["qualification"]["source_sha256"][builder],
        before_package_validation_sha256=(
            previous["qualification"]["code_sha256"]["package_validation.py"]
        ),
        cases=results,
        articles=list(ARTICLES),
        formal_xml_approved=False,
        active_application_changed=False,
        historical_reports_modified=False,
        compatibility_exceptions_added=0,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.root, args.source)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, sort_keys=True, indent=2)
    args.output.chmod(0o600)
    print(json.dumps(dict(cases=len(result["cases"]), audit_passed=True)))
