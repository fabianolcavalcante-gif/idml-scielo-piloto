"""Policy-only replay of a pinned native cohort; never promotes historical evidence."""

import argparse
import copy
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZipFile

from idml_foundation.pipeline.validation import OfflineJatsValidator
from idml_foundation.services.autocorrection_promotion_policy import draft_admission

ROOT = Path(__file__).resolve().parents[1]
SUMMARY_SHA = "54e1ee9ddb0291828aa9f9092482ffbadcd920c7e8ebf97296404d023349003c"
STRUCTURAL_SHA = "b597f1f154ffb94fb8ab483344bb502c1451a81ee93589ebd5b5430edbdef503"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--modern", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary_path = args.matrix / "summary.json"
    structural_path = ROOT / "benchmarks/qualification/reports/vh1-structural-native-replay-v1.json"
    assert sha(summary_path) == SUMMARY_SHA
    assert sha(structural_path) == STRUCTURAL_SHA
    summary = json.loads(summary_path.read_bytes())
    structural = json.loads(structural_path.read_bytes())
    assert structural["native_summary_sha256"] == SUMMARY_SHA
    assert all(sha(ROOT / name) == digest for name, digest in structural["source_sha256"].items())
    results = []
    for case in summary["cases"]:
        key = case["article"] + "-" + case["mutation"]
        folder = args.modern / key
        scope = json.loads((folder / "scope.json").read_bytes())
        assert sha(folder / "candidate.xml") == case["xml_sha256"] == scope["xml_sha256"]
        assert sha(folder / "candidate.zip") == case["package_sha256"] == scope["package_sha256"]
        with ZipFile(folder / "candidate.zip") as package:
            offline = OfflineJatsValidator(ROOT / "vendor/jats/1.3").validate(
                (folder / "candidate.xml").read_bytes(), asset_names=set(package.namelist())
            )
        formal = copy.deepcopy(case["package_assessment"])
        replay = next(row for row in structural["cases"] if row["case"] == key)
        if case["mutation"] == "baseline":
            assert offline.valid
            assert replay["xml_sha256"] == case["xml_sha256"]
            assert replay["package_sha256"] == case["package_sha256"]
            assert replay["report_sha256"] == formal["xpm"]["report_sha256"]
            formal["xpm"]["compatibility"] = replay["compatibility"]
        else:
            assert not offline.valid and replay["native_negative_blocked"]
        decision = draft_admission(
            offline=offline.model_dump(mode="json"),
            formal=formal,
            xml_sha256=scope["xml_sha256"],
            package_sha256=scope["package_sha256"],
            validation_scope=scope,
        )
        expected = key == "esa-e20240086-baseline"
        assert decision["eligible"] is expected, (key, decision)
        assert not decision["release_approved"] and not decision["warnings_accepted"]
        results.append(
            dict(
                case=key,
                xml_sha256=scope["xml_sha256"],
                package_sha256=scope["package_sha256"],
                offline_valid=offline.valid,
                historical_policy_decision=decision,
                actual_promotion=False,
            )
        )
    result = dict(
        version="vh09-promotion-historical-policy-replay-1.0",
        executed_at=datetime.now(UTC).isoformat(),
        summary_sha256=SUMMARY_SHA,
        structural_sha256=STRUCTURAL_SHA,
        cases=results,
        policy_sha256=sha(ROOT / "src/idml_foundation/services/autocorrection_promotion_policy.py"),
        driver_sha256=sha(Path(__file__)),
        fresh_offline_validation=True,
        new_external_executions=0,
        authorization_renewed=False,
        actual_promotions=0,
        release_approved=False,
    )
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(result, output, indent=2)
    print(
        json.dumps(dict(cases=len(results), expected_decisions_verified=True, actual_promotions=0))
    )


if __name__ == "__main__":
    main()
