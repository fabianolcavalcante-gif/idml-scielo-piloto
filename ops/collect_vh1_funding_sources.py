"""Collect fixed official funding evidence privately, without following redirects."""

import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import Request, build_opener

from ops.collect_vh1_editorial_sources import NoRedirect
from ops.qualify_vh1_metadata import sha, write_json

URL = (
    "https://www.alice.cnptia.embrapa.br/alice/bitstream/doc/1147178/1/"
    "P-Uso-do-jardim-aquicola-no-tratamento-e-reuso-da-agua-de-piscicultura.pdf"
)


def main():
    root = Path(__file__).resolve().parents[1]
    folder = (
        root
        / "benchmarks/private/output"
        / ("vh1-funding-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"))
    )
    request = Request(URL, headers={"User-Agent": "IDML-VH1/1.0"})
    with build_opener(NoRedirect()).open(request, timeout=30) as response:
        if response.status != 200 or response.headers.get_content_type() != "application/pdf":
            raise ValueError("funding_source_response_invalid")
        raw = response.read(4 * 1024**2 + 1)
        if not raw.startswith(b"%PDF-") or len(raw) > 4 * 1024**2:
            raise ValueError("funding_source_invalid")
    folder.mkdir(exist_ok=False)
    with (folder / "embrapa.pdf").open("xb") as stream:
        stream.write(raw)
    manifest = {"url": URL, "sha256": sha(raw), "retrieved_at": datetime.now(UTC).isoformat()}
    write_json(folder / "manifest.json", manifest)
    print(json.dumps({"output": str(folder), "source_sha256": sha(raw), "bytes": len(raw)}))


if __name__ == "__main__":
    main()
