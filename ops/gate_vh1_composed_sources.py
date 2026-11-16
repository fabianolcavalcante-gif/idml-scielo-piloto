"""Bind the two legacy rule contracts to their already audited runtime composition."""

import hashlib
import json

from ops.gate_vh1_structural_sources import source_matches as structural_source_matches

PROOF = "benchmarks/qualification/reports/vh1-xpm-composed-v1.json"
REAL = "benchmarks/qualification/reports/vh1-xpm-composed-real-v1.json"
PINS = {
    PROOF: "69496156adab8a2d80470917fc2e698e883f127f92e24a7f39c56fd23125a0f7",
    REAL: "aeaafc8e2375a3d464cfccf749ec95ba98fb8115f12d60cd6b9839e9e30dc5d2",
}
PREDECESSORS = {
    "src/idml_foundation/release/xpm_sps_compatibility.py": (
        "887927934d67408d6ea6a7df122813ab4ad45de4dfc7b6f34d9f2968c3e230ef"
    ),
    "src/idml_foundation/release/xpm_query_requirements.py": (
        "405669f176d989a1c136a666660f9ab4dc6a0e1a8db2f2854f47392e6e447bdb"
    ),
}
RUNTIME = (
    *PREDECESSORS,
    "src/idml_foundation/services/xpm_runtime_compatibility.py",
    "src/idml_foundation/services/xpm_execution.py",
    "src/idml_foundation/services/package_validation.py",
    "ops/xpm_wayta_collect.py",
    "ops/xpm_validator_broker.py",
    "tests/test_xpm_composed.py",
    "config/validator-registry-vh1-composed.json",
)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


FRESH_PROOF = "benchmarks/qualification/reports/vh17-xpm-composed-v1.json"
FRESH_PIN = "d64837867acd216bbca52685f9c9dd6cc89485a696f4810ecc6e39035cdec0b4"


def _current_composed_input(path, expected, reader):
    if structural_source_matches(path, expected, reader):
        return True
    if path not in {
        "ops/xpm_validator_broker.py",
        "src/idml_foundation/services/package_validation.py",
    }:
        return False
    raw = reader(FRESH_PROOF)
    if sha(raw) != FRESH_PIN:
        return False
    proof = json.loads(raw)
    return (
        proof["before"].get(path) == expected
        and all(sha(reader(p)) == h for p, h in proof["source_sha256"].items())
        and proof["release_approved"] is False
        and proof["new_xpm_runs"] == 4
    )


def source_matches(path, expected, reader):
    if sha(reader(path)) == expected:
        return True
    if PREDECESSORS.get(path) != expected or path not in PREDECESSORS:
        return False
    try:
        payloads = {p: reader(p) for p in PINS}
        if any(sha(payloads[p]) != pin for p, pin in PINS.items()):
            return False
        proof, real = json.loads(payloads[PROOF]), json.loads(payloads[REAL])
        # Runtime and its contract tests are current. Qualification harness/logs
        # belong to the immutable historical execution, not a newly claimed run.
        return (
            all(
                _current_composed_input(p, proof["source_and_evidence_sha256"][p], reader)
                for p in RUNTIME
            )
            and proof["real_execution"]["formal_xml_approved"] is False
            and proof["active_runtime_changed"] is False
            and real["formal_xml_approved"] is False
            and len(real["cases"]) == 4
            and all(c["package_assessment"]["state"] == "blocked" for c in real["cases"])
        )
    except (KeyError, ValueError, TypeError, OSError):
        return False
