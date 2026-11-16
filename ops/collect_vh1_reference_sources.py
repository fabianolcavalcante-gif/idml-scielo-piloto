"""Capture a fixed set of public institutional sources in the private vault."""

import json
from datetime import UTC, datetime
from urllib.request import Request, build_opener

from ops.collect_vh1_editorial_sources import NoRedirect
from ops.qualify_vh1_metadata import ROOT, sha, write_json

SOURCES = {
    "srac.pdf": "https://srac.msstate.edu/pdfs/Fact%20Sheets/3700%20Pond%20Aeration.pdf",
    "who.html": "https://www.who.int/publications/m/item/situation-report---106",
    "saae.html": "https://saaesaocarlos.com.br/servicos/agua/mananciais/",
}


def main():
    now = datetime.now(UTC)
    output = (
        ROOT / "benchmarks/private/output" / now.strftime("vh1-reference-sources-%Y%m%dT%H%M%SZ")
    )
    output.mkdir(exist_ok=False)
    manifest = {}
    for name, url in SOURCES.items():
        # Only fixed HTTPS URLs above; redirects and user-supplied locations are not accepted.
        request = Request(url, headers={"User-Agent": "IDML-VH1-bibliographic-review/1.0"})  # noqa: S310
        with build_opener(NoRedirect()).open(request, timeout=30) as response:
            data = response.read(8 * 1024**2 + 1)
            if response.status != 200 or not 0 < len(data) <= 8 * 1024**2:
                raise ValueError("reference_source_response_invalid")
            media = response.headers.get_content_type()
            if media != ("application/pdf" if name.endswith(".pdf") else "text/html"):
                raise ValueError("reference_source_media_invalid")
            if name.endswith(".pdf") and not data.startswith(b"%PDF-"):
                raise ValueError("reference_source_not_pdf")
        with (output / name).open("xb") as stream:
            stream.write(data)
        manifest[name] = {
            "url": url,
            "sha256": sha(data),
            "media_type": media,
            "retrieved_at": datetime.now(UTC).isoformat(),
            "bytes": len(data),
        }
        print(json.dumps({"source": name, "sha256": sha(data), "bytes": len(data)}), flush=True)
    write_json(output / "manifest.json", manifest)
    print(json.dumps({"directory": str(output)}))


if __name__ == "__main__":
    main()
