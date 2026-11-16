"""Create immutable private upload bundle; does not deploy or execute validators."""

import argparse
import json
import re
import shutil
from pathlib import Path

from ops.collect_vh1_editorial_sources import CASES
from ops.editorial_authority import digest

ROOT = Path(__file__).resolve().parents[1]
CODE = (
    "editorial_authority.py",
    "editorial_authority_runtime.py",
    "probe_vh1_editorial.py",
    "doi_validation_evidence.py",
    "run_vh1_editorial_linux.py",
    "validator_broker.py",
    "doi_authority_transport.py",
    "doi_package_binding.py",
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run_id")
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9]{8}T[0-9]{6}Z", args.run_id):
        raise ValueError("run_id_invalid")
    sources = ROOT / "benchmarks/private/output/vh1-editorial" / args.run_id
    plan = {
        "code_sha256": {},
        "cases": {},
        "validators": [
            spec
            for spec in json.loads((ROOT / "config/validator-registry-vh1.json").read_bytes())[
                "validators"
            ]
            if spec["channel"] == "active"
        ],
    }
    for name in CODE:
        plan["code_sha256"][name] = digest((ROOT / "ops" / name).read_bytes())
    for case, expected in CASES.items():
        package = ROOT / "benchmarks/private/output/h1-country-codes-v1" / case / "candidate.zip"
        plan["cases"][case] = {
            "xml_sha256": expected,
            "zip_sha256": digest(package.read_bytes()),
            "editorial_manifest_sha256": digest((sources / case / "manifest.json").read_bytes()),
            "doi_manifest_sha256": digest(
                (
                    ROOT
                    / "benchmarks/private/output"
                    / "incoming-25ca4293d4e180ad32b7751b50fd30cd0f66ace056ff7226cddf01640b69b1e8"
                    / case
                    / "authority/manifest.json"
                ).read_bytes()
            ),
        }
    raw = (json.dumps(plan, indent=2) + "\n").encode()
    output = ROOT / "benchmarks/private/output" / ("vh1-editorial-upload-" + digest(raw)[:16])
    output.mkdir(exist_ok=False)
    for name in CODE:
        shutil.copyfile(ROOT / "ops" / name, output / name)
    for case in CASES:
        shutil.copytree(sources / case, output / case)
    (output / "qualification.json").write_bytes(raw)
    print(json.dumps({"output": str(output), "manifest_sha256": digest(raw)}))


if __name__ == "__main__":
    main()
