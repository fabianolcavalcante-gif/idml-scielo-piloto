"""Bind the private native XPM experiment to public, non-approving feasibility evidence."""

import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

from lxml import html

from idml_foundation.release.xpm import XpmReportParser
from ops.qualify_vh1_xpm_linux import PACKAGES, checked_members, digest, mutate
from ops.run_xpm_qualification import ARCHIVE_SHA256

REPO = Path(__file__).resolve().parents[1]
BASELINE = REPO / "benchmarks/private/output/vh1-final-validation-20261014T155218Z"
EXPECTED_CASES = {
    ("esa-e20240086", "baseline"),
    ("esa-e20240135", "baseline"),
    *(
        ("esa-e20240086", name)
        for name in ("missing_journal_title", "missing_graphic", "malformed_xml")
    ),
}
SOURCES = (
    "deploy/Dockerfile.xpm-qualification",
    "ops/run_xpm_qualification.py",
    "ops/qualify_vh1_xpm_linux.py",
    "ops/export_vh1_xpm_evidence.py",
    "ops/summarize_vh1_xpm_linux.py",
    "tests/test_vh1_xpm_linux.py",
    "src/idml_foundation/release/xpm.py",
)


def visible_text(data):
    doc = html.fromstring(data, parser=html.HTMLParser(no_network=True))
    values = doc.xpath(
        "//text()[not(ancestor::script) and not(ancestor::style) and not(ancestor::template)]"
    )
    return " ".join(" ".join(map(str, values)).split()).replace(" · ", " ")


def negative_detected(mutation, text, baseline, result):
    expected = {
        "missing_journal_title": "missing journal-title in:",
        "missing_graphic": "Not found 1809-4457-esa-30-e20240086-gf01.jpg in the package.",
        "malformed_xml": "invalid XML files.",
    }
    return (
        mutation in expected
        and expected[mutation] in text
        and expected[mutation] not in baseline
        and result.blocking_errors > 0
        and not result.passed
    )


def summarize(directory):
    raw = json.loads((directory / "report.json").read_text(encoding="utf-8"))
    if (
        len(raw["cases"]) != 5
        or {(c["article"], c["mutation"]) for c in raw["cases"]} != EXPECTED_CASES
    ):
        raise ValueError("case_matrix_mismatch")
    if not raw["services_unchanged"] or raw["before"] != raw["after"]:
        raise ValueError("service_state_changed")
    if raw["after"]["readiness"]["status"] != "ok":
        raise ValueError("readiness_failed")
    cases, texts, results = [], {}, {}
    for case in raw["cases"]:
        article, mutation = case["article"], case["mutation"]
        work = directory / (article + "-" + mutation) / "work"
        execution_path = work / "execution.json"
        execution = json.loads(execution_path.read_text(encoding="utf-8"))
        if digest(execution_path) != case["execution_sha256"] or execution != case["execution"]:
            raise ValueError("execution_evidence_mismatch")
        if (
            case["docker_exit_code"] != 0
            or case["docker_timeout"]
            or case["oom_killed"]
            or execution["returncode"] != 0
            or execution["timed_out"]
            or execution["network"] != "none"
            or execution["external_queries_completed"]
            or not execution["input_unchanged"]
            or not execution["vendor_files_unchanged"]
            or execution["archive_sha256"] != ARCHIVE_SHA256
            or execution["runner_sha256"] != digest(REPO / "ops/run_xpm_qualification.py")
            or execution["release_approved"]
            or execution["sps_1_10_compatibility_proven"]
        ):
            raise ValueError("unqualified_execution")
        candidate = BASELINE / article / "candidate.zip"
        if (
            digest(candidate) != PACKAGES[article]
            or case["original_package_sha256"] != PACKAGES[article]
        ):
            raise ValueError("baseline_binding_mismatch")
        with ZipFile(candidate) as archive:
            members = mutate(checked_members(archive), mutation)
        expected = {name: hashlib.sha256(data).hexdigest() for name, data in members.items()}
        if execution["input_manifest"] != expected:
            raise ValueError("input_manifest_mismatch")
        if list(execution["reports"]) != ["input_xpm/errors/xpm.html"]:
            raise ValueError("unexpected_reports")
        report = work / "input_xpm/errors/xpm.html"
        if digest(report) != execution["reports"]["input_xpm/errors/xpm.html"]["sha256"]:
            raise ValueError("report_hash_mismatch")
        for stream in ("stdout", "stderr"):
            if digest(work / (stream + ".log")) != execution[stream + "_sha256"]:
                raise ValueError("log_hash_mismatch")
        # Mutant folders are NOT attested as the unchanged baseline ZIP.
        identity = (
            PACKAGES[article]
            if mutation == "baseline"
            else hashlib.sha256(json.dumps(expected, sort_keys=True).encode()).hexdigest()
        )
        result = XpmReportParser().parse(
            report.read_bytes(), candidate_package_sha256=identity, tool_sha256=ARCHIVE_SHA256
        )
        texts[(article, mutation)] = visible_text(report.read_bytes())
        results[(article, mutation)] = result
        totals = {
            k: getattr(result, k) for k in ("blocking_errors", "fatal_errors", "errors", "warnings")
        }
        if any(
            execution["reports"]["input_xpm/errors/xpm.html"]["totals"][k] != [v]
            for k, v in totals.items()
        ):
            raise ValueError("totals_mismatch")
        cases.append(
            {
                "article": article,
                "mutation": mutation,
                "input_identity_sha256": identity,
                "report_sha256": result.report_sha256,
                "xpm_version": result.xpm_version,
                "counts": totals,
                "parser_errors": result.parser_errors,
                "elapsed_seconds": execution["elapsed_seconds"],
                "child_max_rss_kib": execution["child_max_rss_kib"],
                "input_unchanged": True,
                "vendor_files_unchanged": True,
                "generated_xml_differs": any(
                    expected[n] != execution["generated_package_manifest"].get(n)
                    for n in expected
                    if n.endswith(".xml")
                ),
                "execution_completed": True,
                "validation_approved": False,
            }
        )
    baseline = texts[("esa-e20240086", "baseline")]
    for case in cases:
        if case["mutation"] != "baseline":
            key = (case["article"], case["mutation"])
            if not negative_detected(key[1], texts[key], baseline, results[key]):
                raise ValueError("negative_control_not_detected")
            case["negative_control_detected"] = True
    return {
        "version": "vh1-xpm-linux-feasibility-public-1.0",
        "run_id": raw["run_id"],
        "private_report_sha256": digest(directory / "report.json"),
        "image": raw["image"],
        "archive_sha256": ARCHIVE_SHA256,
        "source_sha256": {name: digest(REPO / name) for name in SOURCES},
        "cases": cases,
        "same_vps_headless_execution_proven": True,
        "negative_controls_detected": 3,
        "network": "none",
        "services_unchanged": True,
        "observed_service_count": len(raw["before"]["services"]),
        "external_queries_completed": False,
        "sps_1_10_compatibility_proven": False,
        "production_deployed": False,
        "release_approved": False,
        "all_required_validations_completed": False,
        "outstanding": [
            "SPS_1_10_AND_JATS_1_3_COMPATIBILITY",
            "EXTERNAL_QUERIES",
            "SUPERVISED_WEB_WORKER_INTEGRATION",
            "LEGACY_RUNTIME_HARDENING",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = summarize(args.directory)
    with args.output.open("x", encoding="utf-8") as target:
        target.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"same_vps_headless_execution_proven": True, "release_approved": False}))
