"""Fetch a fixed public DOI/PID record; preserve raw evidence privately, never renew a copy."""

import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import Request, build_opener

from idml_foundation.release.articlemeta_dates import MAX_RESPONSE, source_url
from ops.collect_vh1_editorial_sources import NoRedirect
from ops.qualify_vh1_metadata import sha, write_json

ROOT = Path(__file__).resolve().parents[1]
PID = "S1413-41522025000100212"
DOI = "10.1590/s1413-415220240086"


def main():
    url = source_url(PID)
    request = Request(  # noqa: S310 - fixed official HTTPS origin, no redirects
        url, headers={"Accept": "application/json", "User-Agent": "IDML-VH1/1.0"}
    )
    with build_opener(NoRedirect()).open(request, timeout=20) as response:
        if response.status != 200 or response.headers.get_content_type() != "application/json":
            raise ValueError("articlemeta_response_invalid")
        raw = response.read(MAX_RESPONSE + 1)
        if not 0 < len(raw) <= MAX_RESPONSE:
            raise ValueError("articlemeta_response_budget")
    record = json.loads(raw)
    if record.get("code") != PID or record.get("doi", "").casefold() != DOI:
        raise ValueError("articlemeta_record_identity_mismatch")
    now = datetime.now(UTC)
    directory = (
        ROOT / "benchmarks/private/output" / ("vh1-articlemeta-" + now.strftime("%Y%m%dT%H%M%SZ"))
    )
    directory.mkdir(exist_ok=False)
    with (directory / "articlemeta.json").open("xb") as stream:
        stream.write(raw)
    manifest = {
        "url": url,
        "pid": PID,
        "doi": DOI,
        "retrieved_at": now.isoformat(),
        "sha256": sha(raw),
        "status": "available",
    }
    write_json(directory / "manifest.json", manifest)
    print(json.dumps({"output": str(directory), "snapshot_sha256": sha(raw)}))


if __name__ == "__main__":
    main()
