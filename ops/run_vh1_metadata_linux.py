"""Pinned native comparisons through the scoped broker executor, not deployed E2E."""

import hashlib
import json
import os
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

from provision_scoped_authorities import provision
from scoped_validator_broker import execute
from validator_broker import reserve


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    source = Path(__file__).resolve().parent
    raw = (source / "plan.json").read_bytes()
    if len(sys.argv) != 2 or sha(raw) != sys.argv[1]:
        raise ValueError("plan_mismatch")
    plan = json.loads(raw)
    for name, expected in plan["code_sha256"].items():
        if Path(name).name != name or sha((source / name).read_bytes()) != expected:
            raise ValueError("code_mismatch")
    if sha((source / "registry.json").read_bytes()) != plan["registry_sha256"]:
        raise ValueError("registry_mismatch")
    registry = json.loads((source / "registry.json").read_bytes())
    work = Path("/var/lib/idml-vh1-qualification")
    reserve(work, starting=True)
    result = {
        "version": "vh1-metadata-linux-1.0",
        "plan_sha256": sha(raw),
        "qualification": plan,
        "cases": [],
        "active_application_changed": False,
        "formal_xml_approved": False,
        "transport": "scoped-broker-executor-not-socket",
    }
    with tempfile.TemporaryDirectory(prefix="metadata-", dir=work) as temporary:
        lab = Path(temporary)
        authority = lab / "authority"
        (authority / "authorizations").mkdir(parents=True, mode=0o700)
        for case, details in plan["cases"].items():
            if case not in {"esa-e20240086", "esa-e20240135"}:
                raise ValueError("case_denied")
            for name, expected in details["files"].items():
                path = Path(name)
                if (
                    path.is_absolute()
                    or ".." in path.parts
                    or sha((source / case / path).read_bytes()) != expected
                ):
                    raise ValueError("input_mismatch")
            inputs = lab / case
            shutil.copytree(source / case, inputs)
            grant = json.loads((inputs / "grant.json").read_bytes())
            grant_path = authority / "authorizations" / (grant["authorization_id"] + ".json")
            grant_path.write_bytes((inputs / "grant.json").read_bytes())
            scope = json.loads((inputs / "scope.json").read_bytes())
            provision(
                authority, inputs / "incoming", inputs / "candidate.xml", inputs / "candidate.zip"
            )
            rows = []
            for original in registry["validators"]:
                if original["channel"] != "active":
                    continue
                spec = {**original, "_scope": scope, "_authority_root": str(authority)}
                run = lab / (case + "-" + spec["name"])
                run.mkdir(mode=0o700)
                candidate = run / ("candidate" + spec["input_suffix"])
                candidate.write_bytes((inputs / candidate.name).read_bytes())
                candidate.chmod(0o444)
                response = json.loads(execute(spec, candidate, work))
                if response["candidate_sha256"] != sha(candidate.read_bytes()):
                    raise ValueError("response_candidate_mismatch")
                findings = response["result"]["findings"]
                rows.append(
                    {
                        "name": spec["name"],
                        "image_id": spec["image_id"],
                        "candidate_sha256": sha(candidate.read_bytes()),
                        "counts": dict(Counter(f["response"] for f in findings)),
                        "findings": findings,
                        "authority_evidence": response["result"]["authority_evidence"],
                    }
                )
                print(
                    json.dumps({"case": case, "name": spec["name"], "counts": rows[-1]["counts"]}),
                    flush=True,
                )
            result["cases"].append({"case": case, "validators": rows})
    with (source / "report.json").open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
    print(json.dumps({"report_saved": True, "active_application_changed": False}))


if __name__ == "__main__":
    os.umask(0o077)
    try:
        main()
    except Exception as error:
        print(json.dumps({"failed": True, "failure_type": type(error).__name__}))
        raise SystemExit(1) from None
