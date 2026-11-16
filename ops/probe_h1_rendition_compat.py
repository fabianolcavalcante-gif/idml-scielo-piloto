"""Exercise only rendition lookup on private packages; no network or full validation."""

import hashlib
import json
from pathlib import Path

from packtools.sps.pid_provider.xml_sps_lib import XMLWithPre
from sps_rendition_compat import PackageRenditionView

ROOT = Path(__file__).resolve().parents[1]


def main():
    rows = []
    for case, relative in (
        ("esa-e20240086-corrected", "h1-publication-metadata-v1/candidate.zip"),
        ("esa-e20240135", "h1-real/esa-e20240135/candidate.zip"),
    ):
        path = ROOT / "benchmarks/private/output" / relative
        before = after = articles = 0
        for article in XMLWithPre.create(path=str(path)):
            articles += 1
            names = set(article.filenames or [])
            before += sum(r["name"] not in names for r in article.renditions)
            after += sum(r["name"] not in names for r in PackageRenditionView(article).renditions)
        if not articles:
            raise ValueError("no articles inspected")
        rows.append(
            {
                "case": case,
                "package_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "legacy_missing_renditions": before,
                "corrected_missing_renditions": after,
            }
        )
    result = {
        "version": "h1-rendition-compat-1.0",
        "scope": "local rendition check only",
        "cases": rows,
        "formal_validation_passed": False,
        "active_adapter_changed": False,
    }
    (ROOT / "benchmarks/qualification/reports/h1-rendition-compat-v1.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
