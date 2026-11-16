"""Reuse pinned online isolation with the two newly rebuilt, hash-bound packages."""

import hashlib
import json
import sys
from pathlib import Path

import qualify_vh1_xpm_online as online

IMAGE = "sha256:43ca49864959e4106d7cbb571f6f64a1222f9865068fee1ce61953aa19886d63"


def main():
    source = Path(__file__).resolve().parent
    raw = (source / "plan.json").read_bytes()
    if len(sys.argv) != 2 or hashlib.sha256(raw).hexdigest() != sys.argv[1]:
        raise ValueError("journal_plan_mismatch")
    plan = json.loads(raw)
    if set(plan["cases"]) != {"esa-e20240086", "esa-e20240135"}:
        raise ValueError("journal_cases_mismatch")
    online.BASELINE = source
    online.PACKAGES = {name: case["package_sha256"] for name, case in plan["cases"].items()}
    online.ROOT = source / "xpm-native"
    online.ROOT.mkdir(mode=0o700, exist_ok=False)
    sys.argv = [sys.argv[0], "--image", IMAGE]
    online.main()


if __name__ == "__main__":
    main()
