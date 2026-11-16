"""Pinned SPSValidator adapter; stdout is one canonical JSON document."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from spsvalidator.domain.validation import validate_sps_zip
from validator_adapter_common import sanitize_validator_result

SPSVALIDATOR_REVISION = os.environ.get(
    "SPSVALIDATOR_REVISION", "d1aa774d4e335d6559c24c2c728471b8fd2e6e42"
)
SPSVALIDATOR_VERSION = f"0.3.0+{SPSVALIDATOR_REVISION[:12]}"
PROFILE_ID = "sps-1.10/jats-1.3"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("package", type=Path)
    arguments = parser.parse_args()
    package_path = arguments.package.resolve(strict=True)
    if not package_path.is_file() or package_path.stat().st_size > 500 * 1024 * 1024:
        raise ValueError("package must be a regular ZIP file up to 500 MiB")
    payload = package_path.read_bytes()
    result = sanitize_validator_result(validate_sps_zip(str(package_path)))
    output = {
        "adapter_contract": "1.1.0",
        "candidate_sha256": hashlib.sha256(payload).hexdigest(),
        "profile_id": PROFILE_ID,
        "result": result,
        "validator_name": "spsvalidator",
        "validator_version": SPSVALIDATOR_VERSION,
    }
    print(
        json.dumps(
            output,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
