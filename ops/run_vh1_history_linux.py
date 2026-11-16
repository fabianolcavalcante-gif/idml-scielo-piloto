"""Reuse the qualified executor/limits; also retain default-vs-effective history proof."""

import json
import os
from pathlib import Path

import run_vh1_metadata_linux as baseline


def main():
    original = baseline.execute
    evidence = {}

    def execute(spec, candidate, work):
        raw = original(spec, candidate, work)
        response = json.loads(raw)
        proof = response["result"]["history_policy_evidence"]
        if proof["candidate_sha256"] != response["candidate_sha256"]:
            raise ValueError("history_candidate_mismatch")
        evidence[(spec["name"], response["candidate_sha256"])] = proof
        return raw

    baseline.execute = execute
    try:
        baseline.main()
    finally:
        baseline.execute = original
    folder = Path(__file__).resolve().parent
    report = json.loads((folder / "report.json").read_bytes())
    report["version"] = "vh1-history-linux-1.0"
    for case in report["cases"]:
        for run in case["validators"]:
            run["history_policy_evidence"] = evidence[(run["name"], run["candidate_sha256"])]
    with (folder / "history-report.json").open("x", encoding="utf-8") as stream:
        json.dump(report, stream, sort_keys=True, indent=2)
    print(json.dumps({"history_report_saved": True, "formal_xml_approved": False}))


if __name__ == "__main__":
    os.umask(0o077)
    try:
        main()
    except Exception as error:
        print(json.dumps({"failed": True, "failure_type": type(error).__name__}))
        raise SystemExit(1) from None
