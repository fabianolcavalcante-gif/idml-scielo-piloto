"""Capture the public specification linked by pinned Packtools; never a runtime fetch."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

URL = (
    "https://docs.google.com/document/d/"
    "1GTv4Inc2LS_AXY-ToHT3HmO66UT0VAHWJNOIqzBNSgA/export?format=txt"
)
DOCUMENT_SHA256 = "09ade688acbf1aa6c48324b660bf4baeb9293c92ff315a2d68c371251909bbef"
ROOT = Path(__file__).resolve().parents[1]


class GoogleExportRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urlsplit(newurl)
        if parsed.scheme != "https" or not (
            parsed.hostname == "docs.google.com"
            or (parsed.hostname or "").endswith(".googleusercontent.com")
        ):
            raise ValueError("spec_redirect_denied")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def main():
    request = Request(URL, headers={"User-Agent": "IDML-VH1-normative-review/1.0"})
    with build_opener(GoogleExportRedirect()).open(request, timeout=40) as response:
        raw = response.read(2 * 1024**2 + 1)
        if response.status != 200 or len(raw) > 2 * 1024**2:
            raise ValueError("spec_response_invalid")
    if hashlib.sha256(raw).hexdigest() != DOCUMENT_SHA256:
        raise ValueError("spec_changed_requires_review")
    text = raw.decode("utf-8-sig")
    # The first occurrence is the table of contents; the second is the specification.
    marker = "<history>: Datas de Histórico"
    start = text.index(marker, text.index(marker) + len(marker))
    end = text.index("<issue>:", start)
    section = text[start:end]
    now = datetime.now(UTC)
    folder = ROOT / "benchmarks/private/output" / now.strftime("vh1-history-spec-%Y%m%dT%H%M%SZ")
    folder.mkdir(exist_ok=False)
    (folder / "sps-specification.txt").write_bytes(raw)
    (folder / "history.txt").write_text(section, encoding="utf-8", newline="\n")
    manifest = {
        "url": URL,
        "retrieved_at": now.isoformat(),
        "sha256": DOCUMENT_SHA256,
        "history_sha256": hashlib.sha256((folder / "history.txt").read_bytes()).hexdigest(),
        "size_bytes": len(raw),
        "section": marker,
        "runtime_network": False,
    }
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"directory": str(folder), **manifest}))


if __name__ == "__main__":
    main()
