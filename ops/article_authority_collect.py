"""Fresh public records for an authorized article; fixed journal and bounded child fetches."""

import json
import subprocess
import sys
import time
from datetime import datetime, timezone

from idml_foundation.services.xpm_query_targets import endpoint, query_targets
from ops import xpm_authority_collect as network
from ops.scoped_authority_transport import digest

JOURNAL_HOST = "articlemeta.scielo.org"
JOURNAL_PATH = "/api/v1/issue/?collection=scl&code=1413-415220250001"
PROFILE = "esa-aop-1.1.0"


def target_endpoint(kind, identifier):
    if kind == "scielo_issue" and identifier == PROFILE:
        return JOURNAL_HOST, JOURNAL_PATH
    return endpoint(kind, identifier)


def fetch(kind, identifier):
    # A separate child process; reuse the qualified DNS/TLS/no-redirect transport.
    original = network.endpoint
    network.endpoint = target_endpoint
    try:
        return network.fetch(kind, identifier)
    finally:
        network.endpoint = original


def collect(xml, scope):
    if scope["journal_profile_id"] != PROFILE or digest(xml) != scope["xml_sha256"]:
        raise ValueError("source_profile_or_candidate_invalid")
    targets = query_targets(xml)
    targets.insert(1, dict(kind="scielo_issue", identifier=PROFILE))
    deadline = time.monotonic() + 60
    files, sources = {}, {}
    total = 0
    for target in targets:
        kind, identifier = target["kind"], target["identifier"]
        host, path = target_endpoint(kind, identifier)
        at = datetime.now(timezone.utc).isoformat()  # noqa: UP017 - host Python 3.10
        raw = None
        remaining = deadline - time.monotonic()
        if remaining > 0:
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "ops.article_authority_collect", "--fetch"],
                    input=json.dumps(dict(kind=kind, identifier=identifier)).encode(),
                    capture_output=True,
                    timeout=min(15, remaining),
                    check=False,
                )
                if result.returncode or not 0 < len(result.stdout) <= network.MAX_RESPONSE:
                    raise ValueError("public_source_unavailable")
                json.loads(result.stdout)
                raw = result.stdout
                total += len(raw)
                if total > 8 * 1024**2:
                    raise ValueError("public_source_budget")
                at = datetime.now(timezone.utc).isoformat()  # noqa: UP017
            except (ValueError, OSError, subprocess.TimeoutExpired):
                raw = None
                if kind != "orcid":
                    raise ValueError("required_public_source_unavailable") from None
        if kind == "crossref":
            if raw is None:
                raise ValueError("required_public_source_unavailable")
            files["crossref.json"] = raw
            files["doi-manifest.json"] = json.dumps(
                dict(
                    authority="https://api.crossref.org/works/",
                    candidate_sha256=scope["xml_sha256"],
                    package_sha256=scope["package_sha256"],
                    snapshot_sha256=digest(raw),
                    retrieved_at=at,
                ),
                sort_keys=True,
            ).encode()
        else:
            name = "journal" if kind == "scielo_issue" else identifier
            if name == "journal" and raw is None:
                raise ValueError("required_public_source_unavailable")
            sources[name] = dict(
                url="https://" + host + path,
                retrieved_at=at,
                sha256=digest(raw) if raw else None,
                status="available" if raw else "unavailable",
            )
            if raw is not None:
                files[name + ".json"] = raw
    files["editorial-manifest.json"] = json.dumps(
        dict(
            version="editorial-authority-1.0",
            profile_id=PROFILE,
            candidate_sha256=scope["xml_sha256"],
            sources=sources,
        ),
        sort_keys=True,
    ).encode()
    return files


if __name__ == "__main__":
    try:
        if sys.argv[1:] != ["--fetch"]:
            raise ValueError("unsupported_operation")
        request = json.loads(sys.stdin.buffer.read(1025))
        if set(request) != {"kind", "identifier"}:
            raise ValueError("invalid_request")
        sys.stdout.buffer.write(fetch(**request))
    except Exception:
        raise SystemExit(1) from None
