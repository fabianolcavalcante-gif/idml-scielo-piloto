import copy
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from urllib.error import URLError

import pytest

from idml_foundation.release.doi_snapshot import bind_doi_snapshot
from ops.collect_vh1_editorial_sources import NoRedirect, fetch
from ops.editorial_authority import (
    ISSUE_URL,
    PROFILE,
    BoundEditorialAuthority,
    digest,
    parse_candidate,
    valid_orcid,
)
from ops.editorial_authority_runtime import editorial_parameters

NOW = datetime.now(UTC)
IDENTIFIER = "0000-0001-6095-4568"
XML = (
    "<article><front><journal-meta><issn>1809-4457</issn></journal-meta>"
    "<article-meta><volume>30</volume><pub-date><year>2025</year></pub-date>"
    f'<contrib><contrib-id contrib-id-type="orcid">{IDENTIFIER}</contrib-id>'
    "<name><given-names>Test</given-names><surname>Person</surname></name>"
    "</contrib></article-meta></front></article>"
).encode()
JOURNAL = {
    "code": "1413-415220250001",
    "collection": "scl",
    "publication_year": "2025",
    "issue_type": "regular",
    "code_title": ["1809-4457", "1413-4152"],
    "issue": {
        "code": "1413-415220250001",
        "collection": "scl",
        "v31": [{"_": "30"}],
        "v49": [{"c": "ESA250", "l": "en", "t": "Scientific Paper"}],
    },
}
PERSON = {
    "path": f"/{IDENTIFIER}/person",
    "name": {
        "visibility": "PUBLIC",
        "given-names": {"value": "Test"},
        "family-name": {"value": "Person"},
        "credit-name": {"value": "Test Person"},
    },
}


def fixture(*, xml=XML, journal=None, person=None):
    snapshots = {
        "journal.json": json.dumps(JOURNAL if journal is None else journal).encode(),
        IDENTIFIER + ".json": json.dumps(PERSON if person is None else person).encode(),
    }
    manifest = {
        "version": "editorial-authority-1.0",
        "profile_id": PROFILE,
        "candidate_sha256": digest(xml),
        "sources": {},
    }
    for key in ("journal", IDENTIFIER):
        manifest["sources"][key] = {
            "url": ISSUE_URL if key == "journal" else f"https://pub.orcid.org/v3.0/{key}/person",
            "retrieved_at": NOW.isoformat(),
            "sha256": digest(snapshots[key + ".json"]),
            "status": "available",
        }
    return manifest, snapshots


def bind(*, xml=XML, manifest=None, snapshots=None, **kwargs):
    if manifest is None:
        manifest, snapshots = fixture(xml=xml, **kwargs)
    return BoundEditorialAuthority(xml, manifest, snapshots.__getitem__, now=NOW)


def test_public_matching_is_exact_and_does_not_mutate_shared_context():
    bound = bind()
    assert bound.lookup_orcid(IDENTIFIER, " test   PERSON ", now=NOW)["status"] == "registered"
    assert bound.lookup_orcid(IDENTIFIER, "T Person", now=NOW)["status"] == "unconfirmed"
    assert bound.lookup_orcid(IDENTIFIER, "Person Test", now=NOW)["status"] == "unconfirmed"
    context = bound.journal(now=NOW)
    context["issues"][0]["volume"] = "999"
    assert bound.journal(now=NOW)["issues"][0]["volume"] == "30"


@pytest.mark.parametrize("field", ["candidate_sha256", "profile_id", "version"])
def test_manifest_binding_tamper(field):
    manifest, snapshots = fixture()
    manifest[field] = "incorrect"
    with pytest.raises(ValueError, match="binding"):
        bind(manifest=manifest, snapshots=snapshots)


@pytest.mark.parametrize("mutation", ["url", "sha256", "missing", "extra", "future", "expired"])
def test_rejects_wrong_missing_or_expired_sources(mutation):
    manifest, snapshots = fixture()
    source = manifest["sources"][IDENTIFIER]
    if mutation in {"url", "sha256"}:
        source[mutation] = "incorrect"
    elif mutation == "missing":
        del manifest["sources"][IDENTIFIER]
    elif mutation == "extra":
        manifest["sources"]["../outside"] = copy.deepcopy(source)
    else:
        source["retrieved_at"] = (
            NOW + timedelta(days=1 if mutation == "future" else -8)
        ).isoformat()
    with pytest.raises(ValueError):
        bind(manifest=manifest, snapshots=snapshots)


def test_unavailable_is_not_approved_or_filled_from_candidate():
    manifest, snapshots = fixture()
    for entry in manifest["sources"].values():
        entry.update(status="unavailable", sha256=None)
    bound = bind(manifest=manifest, snapshots=snapshots)
    assert bound.journal(now=NOW) == {}
    assert bound.lookup_orcid(IDENTIFIER, "Test Person", now=NOW)["status"] == "unknown"


@pytest.mark.parametrize(
    "mutation", ["year", "issn", "code", "collection", "supplement", "sections"]
)
def test_journal_scope_or_schema_invalid(mutation):
    journal = copy.deepcopy(JOURNAL)
    if mutation == "year":
        journal["publication_year"] = "2024"
    elif mutation == "issn":
        journal["code_title"] = ["0000-0000"]
    elif mutation in {"code", "collection"}:
        journal[mutation] = "other"
    elif mutation == "supplement":
        journal["issue"]["v131"] = [{"_": "1"}]
    else:
        journal["issue"]["v49"] = []
    with pytest.raises(ValueError):
        bind(journal=journal)


def test_wrong_volume_is_compared_to_independent_registered_volume():
    # Binding isn't a pass: a native check must detect the different volume.
    bound = bind(xml=XML.replace(b"<volume>30", b"<volume>999"))
    assert bound.journal(now=NOW)["issues"][0]["volume"] == "30"


@pytest.mark.parametrize(
    "person",
    [
        {"path": f"/{IDENTIFIER}/person", "name": None},
        {"path": f"/{IDENTIFIER}/person", "name": {"visibility": "PRIVATE"}},
        {"path": f"/{IDENTIFIER}/person", "name": {"visibility": "PUBLIC"}},
    ],
)
def test_absent_private_or_empty_name_not_approved(person):
    assert (
        bind(person=person).lookup_orcid(IDENTIFIER, "Test Person", now=NOW)["status"] == "unknown"
    )


def test_wrong_record_and_modified_candidate_rejected_and_expiry_rechecked():
    with pytest.raises(ValueError, match="record_mismatch"):
        bind(person={**PERSON, "path": "/0000-0000-0000-0001/person"})
    bound = bind()
    with pytest.raises(ValueError, match="candidate_mismatch"):
        bound.check(tree=parse_candidate(XML.replace(b"Test", b"Other")), now=NOW)
    with pytest.raises(ValueError, match="expired"):
        bound.lookup_orcid(IDENTIFIER, "Test Person", now=NOW + timedelta(days=8))


def test_actual_public_schema_with_full_name_in_given_names():
    person = {
        **PERSON,
        "name": {
            "visibility": "public",
            "given-names": {"value": "Test Person"},
            "family-name": None,
            "credit-name": None,
        },
    }
    bound = bind(person=person)
    assert bound.lookup_orcid(IDENTIFIER, "Test Person", now=NOW)["status"] == "registered"
    assert bound.lookup_orcid(IDENTIFIER, "Test", now=NOW)["status"] == "unconfirmed"


@pytest.mark.parametrize(
    "identifier",
    [
        "0000-0000-0000-0000",
        "https://orcid.org/" + IDENTIFIER,
        "0000-0001-6095-4567",
        "../private",
        None,
    ],
)
def test_bad_identifier_not_registered(identifier):
    assert not valid_orcid(identifier)
    assert bind().lookup_orcid(identifier, "Test Person", now=NOW)["status"] == "unknown"


def test_scoped_bridge_restores_functions_preserves_rules_and_observes_native_rows():
    seen = []

    def native(tree, params):
        seen.append(params)
        yield {"title": "registered issue", "response": "ERROR"}
        yield {"title": "table of contents section", "sub_item": "subject", "response": "OK"}
        yield {"title": "Registered ORCID", "validation_type": "registered", "response": "OK"}

    module = SimpleNamespace(
        **{
            k: native
            for k in (
                "validate_bibliographic_strip",
                "validate_article_toc_sections",
                "validate_article_contribs",
            )
        }
    )
    params = {
        "article_toc_section_rules": {"value_error_level": "CRITICAL"},
        "journal_data": {"abbrev_journal_title": "Original"},
    }
    before = copy.deepcopy(params)
    with pytest.raises(RuntimeError), editorial_parameters(module, bind()) as results:
        rows = list(module.validate_article_toc_sections(parse_candidate(XML), params))
        assert rows[0]["response"] == "ERROR"
        assert results["issue"] == [False]
        assert results["section"] == [True]
        assert results["orcid"] == [True]
        assert seen[0]["journal_data"]["abbrev_journal_title"] == "Original"
        assert seen[0]["article_toc_section_rules"]["value_error_level"] == "CRITICAL"
        raise RuntimeError("test restore")
    assert params == before
    assert module.validate_article_toc_sections is native


@pytest.mark.parametrize("kind", ["match", "other_name", "other_id", "duplicate", "no_record"])
def test_crossref_corroboration_requires_public_registry_and_unique_exact_author(kind):
    xml = XML.replace(
        b"<article-meta>", b'<article-meta><article-id pub-id-type="doi">10.1234/test</article-id>'
    )
    author = {"given": "Test", "family": "Person", "ORCID": "https://orcid.org/" + IDENTIFIER}
    if kind == "other_name":
        author["family"] = "Someone"
    if kind == "other_id":
        author["ORCID"] = "https://orcid.org/0000-0002-0767-779X"
    snapshot = json.dumps(
        {
            "status": "ok",
            "message": {
                "DOI": "10.1234/test",
                "ISSN": ["1809-4457"],
                "author": [author] * (2 if kind == "duplicate" else 1),
            },
        }
    ).encode()
    crossref = bind_doi_snapshot(
        candidate=xml,
        snapshot=snapshot,
        expected_candidate_sha256=digest(xml),
        expected_snapshot_sha256=digest(snapshot),
        retrieved_at=NOW,
        now=NOW,
    )
    person = {
        **PERSON,
        "name": {
            "visibility": "public",
            "given-names": {"value": "T"},
            "family-name": {"value": "Person"},
        },
    }
    manifest, snapshots = fixture(xml=xml, person=person)
    if kind == "no_record":
        manifest["sources"][IDENTIFIER].update(status="unavailable", sha256=None)
    bound = BoundEditorialAuthority(
        xml, manifest, snapshots.__getitem__, now=NOW, crossref=crossref
    )
    outcome = bound.lookup_orcid(IDENTIFIER, "Test Person", now=NOW)
    assert (outcome["status"] == "registered") is (kind == "match")
    if kind == "match":
        assert outcome["reason"] == "public_registry_and_crossref_author_match"
    with pytest.raises(ValueError):
        foreign_manifest, foreign_snapshots = fixture()
        BoundEditorialAuthority(
            XML, foreign_manifest, foreign_snapshots.__getitem__, now=NOW, crossref=crossref
        )


@pytest.mark.parametrize(
    "url",
    [
        "file:///private",
        "http://pub.orcid.org/v3.0/" + IDENTIFIER,
        "https://other.example/person",
        ISSUE_URL + "&redirect=1",
    ],
)
def test_collector_refuses_unknown_origins(url):
    with pytest.raises(ValueError, match="origin_denied"):
        fetch(url)


def test_collector_denies_redirect_and_does_not_approve_network_failure(monkeypatch):
    with pytest.raises(ValueError, match="redirect_denied"):
        NoRedirect().redirect_request(None)

    class FailedOpener:
        def open(self, *args, **kwargs):
            raise URLError("test timeout")

    monkeypatch.setattr("ops.collect_vh1_editorial_sources.build_opener", lambda *a: FailedOpener())
    assert fetch(ISSUE_URL) is None


def test_mismatching_author_name_is_not_mislabeled_as_network_outage():
    from ops.external_verification import unavailable_dependency

    outcome = bind().lookup_orcid(IDENTIFIER, "Other Person", now=NOW)
    row = {
        "title": "Registered ORCID",
        "validation_type": "registered",
        "item": "contrib-id",
        "response": "ERROR",
        "got_value": outcome["status"],
        "data": outcome,
    }
    assert outcome["status"] == "unconfirmed"
    assert unavailable_dependency(row) is None
