import hashlib
import json
from datetime import UTC, datetime, timedelta

import pytest

from idml_foundation.release.doi_snapshot import bind_doi_snapshot

NOW = datetime(2026, 9, 30, tzinfo=UTC)
XML = (
    b"<article><front><journal-meta><issn>1809-4457</issn></journal-meta><article-meta>"
    b'<article-id pub-id-type="doi">10.1234/test</article-id></article-meta></front></article>'
)
RESPONSE = {
    "status": "ok",
    "message": {
        "DOI": "10.1234/test",
        "ISSN": ["1809-4457"],
        "title": ["Different title is not automatically approved"],
    },
}


def bind(*, response=None, xml=XML, retrieved=NOW, **updates):
    snapshot = json.dumps(RESPONSE if response is None else response).encode()
    args = dict(
        candidate=xml,
        snapshot=snapshot,
        expected_candidate_sha256=hashlib.sha256(xml).hexdigest(),
        expected_snapshot_sha256=hashlib.sha256(snapshot).hexdigest(),
        retrieved_at=retrieved,
        now=NOW,
    )
    args.update(updates)
    return bind_doi_snapshot(**args)


def test_binding_is_not_metadata_approval_and_lookup_does_not_share_mutable_data():
    bound = bind()
    result = bound.lookup("10.1234/TEST", candidate_sha256=bound.candidate_sha256, now=NOW)
    assert "valid" not in result
    result["message"]["title"] = ["modified"]
    assert bound.lookup("10.1234/test", candidate_sha256=bound.candidate_sha256, now=NOW)[
        "message"
    ]["title"] != ["modified"]


@pytest.mark.parametrize("field", ["expected_candidate_sha256", "expected_snapshot_sha256"])
def test_rejects_modified_artifacts(field):
    with pytest.raises(ValueError, match="hash mismatch"):
        bind(**{field: "a" * 64})


@pytest.mark.parametrize(
    "date", [NOW + timedelta(seconds=1), NOW - timedelta(days=8), NOW.replace(tzinfo=None)]
)
def test_rejects_untrusted_time_window(date):
    with pytest.raises(ValueError):
        bind(retrieved=date)


@pytest.mark.parametrize(
    "message",
    [
        {"DOI": "10.1234/other", "ISSN": ["1809-4457"]},
        {"DOI": "10.1234/test", "ISSN": ["0000-0000"]},
        {},
    ],
)
def test_rejects_wrong_doi_journal_or_missing_authority(message):
    with pytest.raises(ValueError):
        bind(response={"status": "ok", "message": message})


def test_lookup_rechecks_expiration_and_requested_identifier():
    bound = bind()
    with pytest.raises(ValueError):
        bound.lookup("10.1234/other", candidate_sha256=bound.candidate_sha256, now=NOW)
    with pytest.raises(ValueError):
        bound.lookup(
            "10.1234/test", candidate_sha256=bound.candidate_sha256, now=NOW + timedelta(days=8)
        )
    with pytest.raises(ValueError):
        bound.lookup("10.1234/test", candidate_sha256="a" * 64, now=NOW)
