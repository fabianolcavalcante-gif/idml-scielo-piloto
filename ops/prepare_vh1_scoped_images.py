"""Stage code-only deterministic Docker build context. Never includes article data."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = {
    "editorial_authority.py": "ops/editorial_authority.py",
    "editorial_authority_runtime.py": "ops/editorial_authority_runtime.py",
    "doi_validation_evidence.py": "ops/doi_validation_evidence.py",
    "doi_package_binding.py": "ops/doi_package_binding.py",
    "doi_snapshot.py": "src/idml_foundation/release/doi_snapshot.py",
    "validation_scope.py": "src/idml_foundation/services/validation_scope.py",
    "scoped_validator_adapter.py": "ops/scoped_validator_adapter.py",
    "Dockerfile": "deploy/Dockerfile.validator-scoped-authority",
}


def main():
    source = {name: (ROOT / path).read_bytes() for name, path in FILES.items()}
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in source.items()}
    key = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    output = ROOT / "tmp" / ("vh1-scoped-build-" + key[:16])
    output.mkdir(exist_ok=False)
    for name, data in source.items():
        (output / name).write_bytes(data)
    (output / "manifest.json").write_text(json.dumps(hashes, indent=2), encoding="utf-8")
    print(json.dumps({"directory": str(output), "build_fingerprint": key}))


if __name__ == "__main__":
    main()
