"""Collect only public, allowlisted ESA/ORCID evidence into an ignored private directory."""

import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from ops.editorial_authority import (
    ISSUE_URL,
    MAX_SNAPSHOT,
    PROFILE,
    BoundEditorialAuthority,
    digest,
    orcid_identifiers,
    parse_candidate,
    valid_orcid,
)

ROOT = Path(__file__).resolve().parents[1]
CASES = {
    "esa-e20240086": "7081d302358f8c022114a0ebf568372af43e115bda38a748cc7c2ebbc1494ad0",
    "esa-e20240135": "1757cdb3a15b7fd44beb009e794ff812995eb59cd6e2c1eee2cabee15f9a9706",
}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError("editorial_authority_redirect_denied")


def fetch(url):
    allowed = url == ISSUE_URL or (
        url.startswith("https://pub.orcid.org/v3.0/")
        and url.endswith("/person")
        and valid_orcid(url.removeprefix("https://pub.orcid.org/v3.0/").removesuffix("/person"))
    )
    if not allowed:
        raise ValueError("editorial_origin_denied")
    try:
        request = Request(  # noqa: S310 - exact HTTPS authority allowlist above
            url, headers={"Accept": "application/json", "User-Agent": "IDML-VH1/1.0"}
        )
        with build_opener(NoRedirect()).open(request, timeout=15) as response:
            if response.status != 200 or response.headers.get_content_type() != "application/json":
                raise ValueError("editorial_response_invalid")
            raw = response.read(MAX_SNAPSHOT + 1)
            if not 0 < len(raw) <= MAX_SNAPSHOT:
                raise ValueError("editorial_response_budget")
            json.loads(raw)
        return raw
    except (HTTPError, URLError, TimeoutError):
        return None  # Never interpret network failure / 404 / 429 as a validation pass.


def main():
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output = ROOT / "benchmarks/private/output/vh1-editorial" / run_id
    output.mkdir(parents=True, exist_ok=False)
    cache = {}
    for case, expected in CASES.items():
        source = ROOT / "benchmarks/private/output/h1-country-codes-v1" / case / "candidate.xml"
        candidate = source.read_bytes()
        if digest(candidate) != expected:
            raise ValueError("editorial_fixed_candidate_required")
        ids = orcid_identifiers(parse_candidate(candidate))
        urls = {"journal": ISSUE_URL} | {
            i: f"https://pub.orcid.org/v3.0/{i}/person" for i in ids if valid_orcid(i)
        }
        folder = output / case
        folder.mkdir()
        manifest = {
            "version": "editorial-authority-1.0",
            "profile_id": PROFILE,
            "candidate_sha256": expected,
            "sources": {},
        }
        for key, url in urls.items():
            if url not in cache:
                cache[url] = fetch(url), datetime.now(UTC).isoformat()
            raw, retrieved = cache[url]
            manifest["sources"][key] = {
                "url": url,
                "retrieved_at": retrieved,
                "sha256": digest(raw) if raw is not None else None,
                "status": "available" if raw is not None else "unavailable",
            }
            if raw is not None:
                (folder / (key + ".json")).write_bytes(raw)
        BoundEditorialAuthority(
            candidate,
            manifest,
            lambda n, base=folder: (base / n).read_bytes(),
            now=datetime.now(UTC),
        )
        with (folder / "manifest.json").open("x", encoding="utf-8") as stream:
            json.dump(manifest, stream, indent=2)
        print(
            json.dumps(
                {
                    "case": case,
                    "sources": len(urls),
                    "available": sum(
                        e["status"] == "available" for e in manifest["sources"].values()
                    ),
                }
            ),
            flush=True,
        )
    print(json.dumps({"run_id": run_id, "private_output": str(output)}))


if __name__ == "__main__":
    main()
