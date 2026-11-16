"""Read private candidates locally; run only the network-free reference year rule."""

import json
from pathlib import Path

from lxml import etree
from packtools.sps.models.references import XMLReferences
from packtools.sps.validation.references import ReferenceValidation


def main():
    rows = []
    for label, path in (
        ("before", "benchmarks/private/output/h1-real/esa-e20240086/candidate.xml"),
        ("after", "benchmarks/private/output/h1-publication-metadata-v1/candidate.xml"),
    ):
        root = etree.fromstring(
            Path(path).read_bytes(),
            etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True),
        )
        total = errors = findings = 0
        for item in XMLReferences(root).items:
            total += 1
            try:
                results = list(
                    ReferenceValidation(item, {"publication_type_requires": {}}).validate_year()
                )
                findings += sum(r.get("response") not in {"OK", None} for r in results)
            except ValueError:
                errors += 1
        rows.append(
            {
                "candidate": label,
                "references": total,
                "value_errors": errors,
                "non_ok_findings": findings,
            }
        )
    print(json.dumps({"scope": "local installed reference-year rule only", "cases": rows}))
    if rows[0]["references"] != rows[1]["references"] or rows[1]["value_errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
