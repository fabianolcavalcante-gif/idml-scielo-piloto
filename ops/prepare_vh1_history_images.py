"""Code-only isolated image layer; no changes to deployed services or old images."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = {
    "history_compat.py": "ops/history_compat.py",
    "history_validator_adapter.py": "ops/history_validator_adapter.py",
    "scoped_validator_adapter.py": "ops/scoped_validator_adapter.py",
    "Dockerfile": "deploy/Dockerfile.validator-history-compat",
}


def main():
    hashes = {
        name: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for name, p in FILES.items()
    }
    key = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    folder = ROOT / "tmp" / ("vh1-history-build-" + key[:16])
    folder.mkdir(exist_ok=False)
    for name, path in FILES.items():
        (folder / name).write_bytes((ROOT / path).read_bytes())
    (folder / "manifest.json").write_text(json.dumps(hashes, indent=2), encoding="utf-8")
    print(json.dumps({"directory": str(folder), "build_fingerprint": key}))


if __name__ == "__main__":
    main()
