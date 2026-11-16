"""Read-only, content-free inventory, also executable on stdin inside a pinned image."""

import hashlib
import importlib.metadata
import json
import platform
from pathlib import Path


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def runtime_inventory():
    packages, trees = {}, {}
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata["Name"].lower().replace("_", "-")
        packages[name] = distribution.version
        if name not in {"packtools", "spsvalidator"}:
            continue
        files = {}
        for entry in distribution.files or ():
            relative = entry.as_posix()
            if relative.startswith(f"{name}/") and "__pycache__" not in relative:
                path = Path(distribution.locate_file(entry))
                if path.is_file() and not path.is_symlink():
                    files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        trees[name] = {"file_count": len(files), "sha256": digest(files)}
    wrappers = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(Path("/validator").glob("*.py"))
        if p.is_file() and not p.is_symlink()
    }
    return {
        "python": platform.python_version(),
        "platform": platform.system(),
        "machine": platform.machine(),
        "packages": dict(sorted(packages.items())),
        "package_trees": trees,
        "wrappers_sha256": wrappers,
    }


if __name__ == "__main__":
    print(json.dumps(runtime_inventory(), sort_keys=True))
