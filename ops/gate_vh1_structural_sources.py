"""Exact, native-replayed successor of the compatibility composer; no broad waiver."""

import hashlib
import json

PROOF = "benchmarks/qualification/reports/vh17-structural-native-replay-v1.json"
PROOF_SHA256 = "8661f42bcda1370c463a4fff6b17a05924fcacb48e8cbfe83705af39196662cd"
PATH = "src/idml_foundation/services/xpm_runtime_compatibility.py"
PREDECESSOR_SHA256 = "c11b65e7fa2b95623608bd05c5994265b4d9a6cb0d76049a941231698b05b95d"


def source_matches(path, expected, reader):
    def sha(raw):
        return hashlib.sha256(raw).hexdigest()

    if sha(reader(path)) == expected:
        return True
    if path != PATH or expected != PREDECESSOR_SHA256:
        return False
    try:
        raw = reader(PROOF)
        if sha(raw) != PROOF_SHA256:
            return False
        proof = json.loads(raw)
        cases = proof["cases"]
        positives = [c for c in cases if "compatibility" in c]
        negatives = [c for c in cases if "compatibility" not in c]
        return (
            all(sha(reader(p)) == h for p, h in proof["source_sha256"].items())
            and len(positives) == len(negatives) == 2
            and all(c["additional_error_blocked"] is True for c in positives)
            and all(c["current_offline_valid"] is False for c in negatives)
            and all(c["compatibility"]["technical_errors_resolved"] is True for c in positives)
            and all(c["compatibility"]["release_approved"] is False for c in positives)
            and proof["formal_xml_approved"] is False
            and proof["homologation_ready"] is False
            and proof["active_runtime_changed"] is False
            and proof["replay_original_time"] is True
            and proof["new_native_executions"] == 0
        )
    except (KeyError, ValueError, TypeError, OSError):
        return False
