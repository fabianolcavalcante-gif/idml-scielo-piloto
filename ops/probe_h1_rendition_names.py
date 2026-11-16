"""Local diagnostic using installed Packtools; no external lookups or approval."""

import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

from packtools.sps.pid_provider.xml_sps_lib import XMLWithPre
from rendition_name_diagnostic import classify_rendition_name

ROOT = Path(__file__).resolve().parents[1]


def main():
    rows = []
    for case, relative in (
        ("esa-e20240086-corrected", "h1-publication-metadata-v1/candidate.zip"),
        ("esa-e20240135", "h1-real/esa-e20240135/candidate.zip"),
    ):
        path = ROOT / "benchmarks/private/output" / relative
        results = []
        with ZipFile(path) as archive:
            names = archive.namelist()
        for article in XMLWithPre.create(path=str(path)):
            for rendition in article.renditions:
                results.append(
                    classify_rendition_name(
                        xml_name=article.xml_name + ".xml",
                        actual_names=names,
                        validator_expected=rendition["name"],
                        language=rendition.get("lang"),
                        main=rendition.get("main", False),
                    )
                )
        rows.append(
            {
                "case": case,
                "package_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "filename_diagnostics": results,
            }
        )
    report = {
        "version": "h1-rendition-name-triage-1.0",
        "scope": "local installed runtime, filename checks only",
        "cases": rows,
        "formal_validation_passed": False,
    }
    (ROOT / "benchmarks/qualification/reports/h1-rendition-name-triage-v1.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report))


if __name__ == "__main__":
    main()
