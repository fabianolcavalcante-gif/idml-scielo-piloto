"""Collect the fixed public sources used by the ESA development catalogs."""

import argparse
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from urllib.error import URLError
from urllib.request import Request, build_opener

from idml_foundation.release.articlemeta_dates import source_url
from idml_foundation.release.articlemeta_orcids import person_url
from idml_foundation.release.journal_metadata import REGISTRY_URL
from ops.collect_vh1_affiliation_sources import URLS
from ops.collect_vh1_articlemeta_dates import PID
from ops.collect_vh1_editorial_sources import NoRedirect
from ops.collect_vh1_funding_sources import URL
from ops.collect_vh1_reference_sources import SOURCES
from ops.prepare_esa_runtime_catalogs import ORCIDS, ROOT


def collect():
    folder = (
        ROOT
        / "benchmarks/private/output"
        / datetime.now(UTC).strftime("catalog-sources-%Y%m%dT%H%M%SZ")
    )
    folder.mkdir(exist_ok=False)
    urls = dict(URLS)
    from idml_foundation.release.institution_locations import SOURCES as locations

    urls["easwari_disclosure"] = locations["easwari_disclosure"].url
    urls.update({k.replace(".", "_"): url for k, url in SOURCES.items()})
    urls.update(
        journal=REGISTRY_URL,
        articlemeta=source_url(PID),
        funding=URL,
        crossref86="https://api.crossref.org/works/10.1590%2Fs1413-415220240086",
        crossref="https://api.crossref.org/works/10.1590%2Fs1413-415220240135",
    )
    urls.update({i: person_url(i) for i in ORCIDS})

    def fetch(item):
        key, url = item
        accept = (
            "application/json"
            if key in {*ORCIDS, "articlemeta", "crossref", "crossref86"}
            else "*/*"
        )
        try:
            request = Request(  # noqa: S310 - fixed HTTPS addresses above, redirects refused
                url, headers={"Accept": accept, "User-Agent": "IDML-qualified-enrichment/1.0"}
            )
            with build_opener(NoRedirect()).open(request, timeout=35) as response:
                raw = response.read(8 * 1024**2 + 1)
                if response.status != 200 or not 0 < len(raw) <= 8 * 1024**2:
                    raise ValueError("source_response_invalid")
                media = response.headers.get_content_type()
            with (folder / (key + ".bin")).open("xb") as stream:
                stream.write(raw)
            result = dict(
                status="available",
                media_type=media,
                bytes=len(raw),
                sha256=hashlib.sha256(raw).hexdigest(),
            )
        except (URLError, TimeoutError, ValueError) as exc:
            result = dict(status="unavailable", failure=type(exc).__name__)
        return key, dict(result, url=url, retrieved_at=datetime.now(UTC).isoformat())

    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = dict(pool.map(fetch, urls.items()))
    (folder / "verified-manifest.json").write_text(json.dumps(rows, indent=2), encoding="utf8")
    return folder


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__).parse_args()
    print(collect())
