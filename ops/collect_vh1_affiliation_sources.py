"""Collect only fixed institutional/government pages; no uploaded URLs or browser scripts."""

import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import Request, build_opener

from ops.collect_vh1_editorial_sources import NoRedirect
from ops.qualify_vh1_metadata import sha, write_json

ROOT = Path(__file__).resolve().parents[1]
URLS = {
    "tokyo_department": "https://ml.c.u-tokyo.ac.jp/en/contact/",
    "tokyo_government": "https://www.english.metro.tokyo.lg.jp/w/000-101-007591",
    "cahcet": "https://cahcet.in/?page_id=659",
    "easwari": "https://www.nirfindia.org/Rankings/2024/EngineeringRanking200.html",
    "tindivanam": "https://viluppuram.nic.in/public-utility/university-college-of-engineering-tindivanam/",
    "syed_hameedha": "https://www.shartsandscience-edu.in/contact.php",
}


def main():
    folder = (
        ROOT
        / "benchmarks/private/output"
        / ("vh1-affiliations-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"))
    )
    folder.mkdir(exist_ok=False)
    manifest = {}
    for key, url in URLS.items():
        request = Request(  # noqa: S310 - fixed official HTTPS URLs, no redirects
            url, headers={"Accept": "text/html", "User-Agent": "IDML-VH1/1.0"}
        )
        with build_opener(NoRedirect()).open(request, timeout=20) as response:
            if response.status != 200 or response.headers.get_content_type() != "text/html":
                raise ValueError("affiliation_source_response_invalid")
            raw = response.read(4 * 1024**2 + 1)
            if not 0 < len(raw) <= 4 * 1024**2:
                raise ValueError("affiliation_source_budget")
        with (folder / f"{key}.html").open("xb") as stream:
            stream.write(raw)
        manifest[key] = {
            "url": url,
            "sha256": sha(raw),
            "retrieved_at": datetime.now(UTC).isoformat(),
        }
        print(json.dumps({"source": key, "bytes": len(raw)}), flush=True)
    write_json(folder / "manifest.json", manifest)
    print(
        json.dumps(
            {"output": str(folder), "manifest_sha256": sha((folder / "manifest.json").read_bytes())}
        )
    )


if __name__ == "__main__":
    main()
