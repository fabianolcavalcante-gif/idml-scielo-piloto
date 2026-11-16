"""Preserve bounded public ORCID evidence privately; reuse original ArticleMeta timestamp."""

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from idml_foundation.release.articlemeta_orcids import person_url, sha
from ops.collect_vh1_articlemeta_dates import PID
from ops.collect_vh1_editorial_sources import fetch
from ops.qualify_vh1_metadata import write_json

ROOT = Path(__file__).resolve().parents[1]
ARTICLEMETA = ROOT / "benchmarks/private/output/vh1-articlemeta-20261005T181540Z"
IDENTIFIERS = ("0000-0003-1136-7986", "0000-0002-3963-5973", "0000-0002-0839-9947")


def main():
    raw = (ARTICLEMETA / "articlemeta.json").read_bytes()
    manifest = json.loads((ARTICLEMETA / "manifest.json").read_bytes())
    if manifest["sha256"] != sha(raw) or manifest["pid"] != PID:
        raise ValueError("articlemeta_snapshot_mismatch")
    directory = (
        ROOT
        / "benchmarks/private/output"
        / ("vh1-orcids-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"))
    )
    directory.mkdir(exist_ok=False)
    shutil.copyfile(ARTICLEMETA / "articlemeta.json", directory / "articlemeta.json")
    shutil.copyfile(ARTICLEMETA / "manifest.json", directory / "articlemeta-manifest.json")
    records = {}
    for identifier in IDENTIFIERS:
        url = person_url(identifier)
        content = fetch(url)
        if content is None:
            raise ValueError("public_orcid_unavailable")
        if json.loads(content).get("path") != f"/{identifier}/person":
            raise ValueError("public_orcid_identity_mismatch")
        with (directory / f"{identifier}.json").open("xb") as stream:
            stream.write(content)
        records[identifier] = {
            "url": url,
            "sha256": sha(content),
            "status": "available",
            "retrieved_at": datetime.now(UTC).isoformat(),
        }
    write_json(directory / "persons-manifest.json", records)
    print(json.dumps({"directory": str(directory), "public_records": len(records)}))


if __name__ == "__main__":
    main()
