#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from idml_foundation.ai.real_domain_corpus import build_real_domain_corpus


def _write_private(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as target:
        json.dump(value, target, ensure_ascii=False, indent=2)
        target.write("\n")
    os.replace(temporary, path)
    os.chmod(path, 0o600)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--idml", type=Path, required=True)
    parser.add_argument("--approved-xml", type=Path, required=True)
    parser.add_argument("--corpus-id", required=True)
    parser.add_argument("--source-idml-sha256", required=True)
    parser.add_argument("--dataset-output", type=Path, required=True)
    parser.add_argument("--report-output", type=Path, required=True)
    args = parser.parse_args()

    dataset, report = build_real_domain_corpus(
        idml_data=args.idml.read_bytes(),
        approved_xml=args.approved_xml.read_bytes(),
        logical_name=args.idml.name,
        corpus_id=args.corpus_id,
        source_idml_sha256=args.source_idml_sha256,
    )
    _write_private(args.dataset_output, dataset)
    _write_private(args.report_output, report)
    print(
        json.dumps(
            {
                "cases": len(dataset["cases"]),
                "dataset_version": dataset["version"],
                "display_formula_pairing_complete": report["math_notes"][
                    "display_formula_pairing_complete"
                ],
                "status": "prepared-not-executed",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
