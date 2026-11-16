"""Isolated Packtools SPS adapter; stdout is one canonical JSON document."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import packtools
from lxml import etree
from packtools.sps.validation.xml_validator import get_validation_results
from validator_adapter_common import sanitize_validator_result

PACKTOOLS_VERSION = "4.17.2"
PACKTOOLS_REVISION = os.environ.get(
    "PACKTOOLS_REVISION", "ef0e6f874ea7eb26cfc406c888b3c95d405d2613"
)
PROFILE_ID = "sps-1.10/jats-1.3"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("xml", type=Path)
    arguments = parser.parse_args()
    xml_path = arguments.xml.resolve(strict=True)
    if not xml_path.is_file() or xml_path.stat().st_size > 100 * 1024 * 1024:
        raise ValueError("XML input must be a regular file up to 100 MiB")
    payload = xml_path.read_bytes()
    parser = etree.XMLParser(
        resolve_entities=False,
        load_dtd=False,
        no_network=True,
        recover=False,
        huge_tree=False,
    )
    xmltree = etree.fromstring(payload, parser=parser)
    result = sanitize_validator_result(list(get_validation_results(xmltree, {})))
    output = {
        "adapter_contract": "1.1.0",
        "candidate_sha256": hashlib.sha256(payload).hexdigest(),
        "profile_id": PROFILE_ID,
        "result": result,
        "validator_name": "packtools",
        "validator_version": (
            f"{getattr(packtools, '__version__', PACKTOOLS_VERSION)}+{PACKTOOLS_REVISION[:12]}"
        ),
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
