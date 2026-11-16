"""Internal trusted-manifest boundary for offline Crossref lookups, not DOI approval."""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, cast

from lxml import etree


@dataclass(frozen=True)
class BoundDoiSnapshot:
    doi: str
    candidate_sha256: str
    snapshot_sha256: str
    retrieved_at: datetime
    payload: bytes

    def lookup(self, doi: str, *, candidate_sha256: str, now: datetime) -> dict[str, Any]:
        _fresh(self.retrieved_at, now)
        if candidate_sha256 != self.candidate_sha256:
            raise ValueError("snapshot cannot be reused for another candidate")
        if doi.strip().casefold() != self.doi:
            raise ValueError("DOI does not belong to this bound snapshot")
        # Return a fresh copy; upstream code cannot mutate the verified payload.
        result: dict[str, Any] = json.loads(self.payload)
        return result


def _fresh(retrieved_at: datetime, now: datetime) -> None:
    if retrieved_at.utcoffset() is None or now.utcoffset() is None:
        raise ValueError("authority timestamps require a timezone")
    age = now - retrieved_at
    if age < timedelta(0) or age > timedelta(days=7):
        raise ValueError("authority snapshot is future-dated or expired")


def bind_doi_snapshot(
    *,
    candidate: bytes,
    snapshot: bytes,
    expected_candidate_sha256: str,
    expected_snapshot_sha256: str,
    retrieved_at: datetime,
    now: datetime,
) -> BoundDoiSnapshot:
    """Expected hashes/time must come from a trusted server manifest, never upload fields.

    This verifies integrity, freshness, DOI and journal binding. Native validators
    must still compare titles/authors; no `valid=True` result is fabricated here.
    """
    _fresh(retrieved_at, now)
    if not candidate or len(candidate) > 100 * 1024**2:
        raise ValueError("invalid candidate size")
    if not snapshot or len(snapshot) > 10 * 1024**2:
        raise ValueError("invalid snapshot size")
    if hashlib.sha256(candidate).hexdigest() != expected_candidate_sha256:
        raise ValueError("candidate hash mismatch")
    if hashlib.sha256(snapshot).hexdigest() != expected_snapshot_sha256:
        raise ValueError("snapshot hash mismatch")
    response = json.loads(snapshot)
    if not isinstance(response, dict) or response.get("status") != "ok":
        raise ValueError("not a successful Crossref work response")
    message = response.get("message")
    if not isinstance(message, dict):
        raise ValueError("missing Crossref message")
    root = etree.fromstring(candidate, etree.XMLParser(resolve_entities=False, no_network=True))
    dois = cast(list[str], root.xpath("front/article-meta/article-id[@pub-id-type='doi']/text()"))
    doi = str(message.get("DOI", "")).strip().casefold()
    if not doi or len(dois) != 1 or str(dois[0]).strip().casefold() != doi:
        raise ValueError("snapshot DOI does not match unique article DOI")
    issns = cast(list[str], root.xpath("front/journal-meta/issn/text()"))
    authority_issns = message.get("ISSN")
    if not isinstance(authority_issns, list) or not {str(s).strip() for s in issns} & set(
        authority_issns
    ):
        raise ValueError("snapshot journal does not match candidate ISSN")
    return BoundDoiSnapshot(
        doi, expected_candidate_sha256, expected_snapshot_sha256, retrieved_at, snapshot
    )
