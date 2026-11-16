"""Verify the bounded Wayta qualification without turning it into XML approval."""

import json

from idml_foundation.release.xpm_query_requirements import WaytaServiceObservation
from ops import gate_vh1_sps_compatibility as previous
from ops.audit_vh1_wayta_requirements import PROBE, ROOT, SERVICE, SOURCES, sha
from ops.gate_vh1_composed_sources import source_matches

REPORT = ROOT / "benchmarks/qualification/reports/vh1-wayta-requirements-v1.json"
PROOF = "f5a5c8fcb527a9cd193468e05fac1033114647a064bb3e32e9127ca2ec6c2efd"


def evaluate(report, reader):
    checks = {}
    try:
        checks["proof_identity"] = (
            sha(json.dumps(report, sort_keys=True, indent=2).encode()) == PROOF
        )
        checks["current_sources"] = set(report["source_sha256"]) == set(SOURCES) and all(
            source_matches(path, digest, reader) for path, digest in report["source_sha256"].items()
        )
        raw = reader(previous.REPORT.relative_to(ROOT).as_posix())
        prior = json.loads(raw)
        checks["native_predecessors"] = (
            sha(raw) == report["previous_sps_proof_sha256"]
            and previous.evaluate(prior, reader)["passed"]
        )
        checks["probe_binding"] = sha(reader(PROBE)) == report["native_probe_sha256"]
        checks["service_binding"] = sha(reader(SERVICE)) == report["service_report_sha256"]
        service = WaytaServiceObservation.model_validate(
            json.loads(reader(SERVICE))["service_observation"]
        ).model_dump(mode="json")
        checks["no_mutation_or_approval"] = all(
            report[key] is False
            for key in (
                "native_xpm_full_rerun",
                "candidate_changed",
                "vendor_changed",
                "active_application_changed",
                "homologation_ready",
                "release_approved",
            )
        )
        checks["cases"] = set(report["assessments"]) == {"esa-e20240086", "esa-e20240135"}
        for name, result in report["assessments"].items():
            checks[name] = (
                result["base"] == prior["assessments"][name]
                and result["requirement"] == "advisory_for_qualified_profile"
                and result["service_observation"] == service
                and result["service_report_sha256"] == report["service_report_sha256"]
                and result["native_proof_sha256"] == report["native_probe_sha256"]
                and result["normative_sha256"] == report["normative_sha256"]
                and result["article_query_completed"] is False
                and result["institution_identity_verified"] is False
                and result["mandatory_affiliation_validation_required"] is True
                and result["homologation_ready"] is False
                and result["release_approved"] is False
                and result["affiliation_count"] == (3 if name == "esa-e20240086" else 4)
                and "required-queries-incomplete" in result["base"]["reasons"]
            )
    except (OSError, ValueError, TypeError, KeyError):
        checks["complete_evidence"] = False
    return {
        "passed": bool(checks) and all(checks.values()),
        "checks": checks,
        "homologation_ready": False,
        "release_approved": False,
    }


if __name__ == "__main__":
    result = evaluate(json.loads(REPORT.read_bytes()), lambda path: (ROOT / path).read_bytes())
    print(json.dumps(result))
    raise SystemExit(0 if result["passed"] else 1)
