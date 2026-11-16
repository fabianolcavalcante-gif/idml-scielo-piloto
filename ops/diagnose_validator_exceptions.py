"""Private-input diagnostic: emit only allowlisted exception classes and field names."""

import hashlib
import json
from pathlib import Path

from spsvalidator.domain.validation import validate_sps_zip

KNOWN_CLASSES = (
    "AttributeError",
    "KeyError",
    "TypeError",
    "ValueError",
    "IndexError",
    "ConnectionError",
    "TimeoutError",
    "FileNotFoundError",
    "NameError",
    "ZeroDivisionError",
)


def main():
    path = Path("/qualification/candidate.zip")
    result = validate_sps_zip(str(path))
    findings = []
    for item in result.get("exceptions", []):
        raw = json.dumps(item, default=str)
        findings.append(
            {
                "group": item.get("group")
                if item.get("group") in {"reference", "open-science"}
                else "other",
                "recognized_exception_classes": [name for name in KNOWN_CLASSES if name in raw],
                "none_type_mentioned": "NoneType" in raw,
                "network_failure_mentioned": any(
                    word in raw
                    for word in ("ConnectionError", "NameResolutionError", "Network is unreachable")
                ),
                "exception_sha256": hashlib.sha256(raw.encode()).hexdigest(),
            }
        )
    print(
        json.dumps(
            {
                "candidate_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "exceptions": findings,
            }
        )
    )


if __name__ == "__main__":
    main()
