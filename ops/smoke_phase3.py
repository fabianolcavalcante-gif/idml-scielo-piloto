"""Offline image smoke test for the deterministic pipeline."""

import argparse
import hashlib
import json
from pathlib import Path

from idml_foundation.pipeline.service import DeterministicPipeline


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    vendor = Path("/app/vendor/jats/1.3")
    provenance = json.loads((vendor / "SOURCE.json").read_text(encoding="utf-8"))
    for name, expected in provenance["files"].items():
        actual = hashlib.sha256((vendor / name).read_bytes()).hexdigest()
        if actual != expected:
            raise SystemExit(f"vendored JATS hash mismatch: {name}")
    result = DeterministicPipeline().run(
        args.input.read_bytes(),
        logical_name=args.input.name,
    )
    print(
        f"valid={str(result.validation.valid).lower()} "
        f"issues={len(result.validation.issues)} "
        f"jats_files={len(provenance['files'])} "
        f"xml_sha256={result.validation.xml_sha256}"
    )
    if not result.validation.valid:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
