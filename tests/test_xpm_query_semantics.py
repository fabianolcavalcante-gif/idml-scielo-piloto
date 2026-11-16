"""Semantic negatives must never become approval or leak private authority responses."""

import copy
import hashlib
import json
from datetime import UTC, datetime, timedelta
from io import BytesIO
from uuid import uuid4
from zipfile import ZipFile

import pytest

from idml_foundation.release.xpm_query_semantics import QueryEvidence, assess_queries
from idml_foundation.services.xpm_execution import assess_xpm_execution
from idml_foundation.services.xpm_query_targets import endpoint, parse_candidate, query_targets
from ops import xpm_authority_collect as collector
from tests.test_xpm_execution import execution

ORCID = "0000-0002-1825-0097"
XML = (
    "<article><front><journal-meta><issn>1234-5678</issn><journal-title-group>"
    "<journal-title>Journal</journal-title></journal-title-group></journal-meta>"
    "<article-meta><article-id pub-id-type='doi'>10.1234/test</article-id>"
    "<title-group><article-title>Title</article-title></title-group><contrib-group>"
    "<contrib contrib-type='author'><name><given-names>Ana</given-names><surname>Silva</surname>"
    f"</name><contrib-id contrib-id-type='orcid'>{ORCID}</contrib-id>"
    "</contrib></contrib-group></article-meta></front></article>"
).encode()


def sha(value):
    return hashlib.sha256(value).hexdigest()


def sample():
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("article.xml", XML)
    package = buffer.getvalue()
    scope = dict(
        organization_id=str(uuid4()),
        resource_id=str(uuid4()),
        source_idml_sha256="a" * 64,
        journal_profile_id="esa-aop-1.1.0",
        xml_sha256=sha(XML),
        package_sha256=sha(package),
    )
    now = datetime.now(UTC)
    crossref = dict(
        status="ok",
        message=dict(
            DOI="10.1234/test",
            ISSN=["1234-5678"],
            title=["Title"],
            **{"container-title": ["Journal"]},
            author=[dict(given="Ana", family="Silva")],
        ),
    )
    orcid = dict(
        path=f"/{ORCID}/person",
        name={
            "visibility": "public",
            "given-names": {"value": "Ana"},
            "family-name": {"value": "Silva"},
        },
    )
    rows = []
    for target, body in zip(query_targets(XML), (crossref, orcid), strict=True):
        host, path = endpoint(target["kind"], target["identifier"])
        payload = json.dumps(body)
        rows.append(
            dict(
                kind=target["kind"],
                identifier=target["identifier"],
                url="https://" + host + path,
                status="available",
                retrieved_at=now.isoformat(),
                payload=payload,
                response_sha256=sha(payload.encode()),
            )
        )
    evidence = dict(
        version="xpm-query-evidence-1.0", scope=scope, report_sha256="b" * 64, receipts=rows
    )
    return scope, package, now, evidence


def assess(scope, now, evidence):
    return assess_queries(
        xml=XML,
        evidence=QueryEvidence.model_validate(evidence),
        scope=scope,
        report_sha256="b" * 64,
        now=now,
    )


def test_selected_matches_do_not_grant_global_success():
    scope, _, now, evidence = sample()
    result = assess(scope, now, evidence)
    assert result["selected_checks_matched"]
    assert not result["required_queries_complete"] and not result["authenticated_orcid_ownership"]
    assert all(c["status"] == "matched" for c in result["checks"])
    assert "Ana" not in json.dumps(result) and "10.1234" not in json.dumps(result)


@pytest.mark.parametrize(
    "change",
    [
        "scope",
        "report",
        "stale",
        "future",
        "hash",
        "origin",
        "missing",
        "extra",
        "duplicate",
        "false_unavailable",
    ],
)
def test_untrusted_evidence_rejected(change):
    scope, _, now, value = sample()
    evidence = copy.deepcopy(value)
    row = evidence["receipts"][0]
    if change == "scope":
        evidence["scope"]["resource_id"] = str(uuid4())
    elif change == "report":
        evidence["report_sha256"] = "c" * 64
    elif change in {"stale", "future"}:
        row["retrieved_at"] = (now + timedelta(hours=25 if change == "future" else -25)).isoformat()
    elif change == "hash":
        row["payload"] += " "
    elif change == "origin":
        row["url"] = "https://evil.test/"
    elif change == "missing":
        evidence["receipts"].pop()
    elif change == "extra":
        extra = copy.deepcopy(row)
        extra["identifier"] = "10.1234/other"
        evidence["receipts"].append(extra)
    elif change == "duplicate":
        evidence["receipts"].append(row)
    else:
        row["status"] = "unavailable"
    with pytest.raises(ValueError):
        assess(scope, now, evidence)


@pytest.mark.parametrize(
    "change",
    [
        "doi",
        "issn",
        "article_title",
        "journal_title",
        "author",
        "orcid_path",
        "orcid_name",
        "orcid_private",
        "json",
        "crossref_unavailable",
        "orcid_unavailable",
    ],
)
def test_real_response_conflicts_and_absence_remain_visible(change):
    scope, _, now, value = sample()
    row = value["receipts"][1 if change.startswith("orcid") else 0]
    raw = json.loads(row["payload"])
    if change == "doi":
        raw["message"]["DOI"] = "10.1234/other"
    elif change == "issn":
        raw["message"]["ISSN"] = ["9999-9999"]
    elif change in {"article_title", "journal_title"}:
        raw["message"]["title" if change == "article_title" else "container-title"] = ["Other"]
    elif change == "author":
        raw["message"]["author"][0]["given"] = "Other"
    elif change == "orcid_path":
        raw["path"] = "/other/person"
    elif change == "orcid_name":
        raw["name"]["given-names"]["value"] = "Other"
    elif change == "orcid_private":
        raw["name"]["visibility"] = "private"
    row["payload"] = "not json" if change == "json" else json.dumps(raw)
    row["response_sha256"] = sha(row["payload"].encode())
    if change.endswith("unavailable"):
        row.update(status="unavailable", payload=None, response_sha256=None)
    result = assess(scope, now, value)
    assert not result["selected_checks_matched"]
    assert any(
        c["status"] == ("unavailable" if change.endswith("unavailable") else "conflict")
        for c in result["checks"]
    )


@pytest.mark.parametrize(
    "kind,identifier",
    [
        ("crossref", "http://localhost"),
        ("orcid", "0000-0000-0000-0000"),
        ("crossref", "10.1234/x?secret=y"),
        ("orcid", ORCID + "/../private"),
        ("unknown", ORCID),
    ],
)
def test_closed_targets(kind, identifier):
    with pytest.raises(ValueError):
        endpoint(kind, identifier)


@pytest.mark.parametrize(
    "xml",
    [
        b"<article/>",
        XML.replace(b"10.1234/test", b"invalid"),
        b'<!DOCTYPE article [<!ENTITY x "xx">]>' + XML,
        XML.replace(b"<article>", b"<article>" + b"<a>" * 129),
        XML.replace(b"0000-0002-1825-0097", b"0000-0000-0000-0000"),
        XML[:-10],
        XML.decode().encode("utf-16"),
    ],
)
def test_invalid_xml_targets_not_dispatched(xml):
    with pytest.raises(ValueError):
        query_targets(xml)


def test_public_doctype_never_fetched():
    assert (
        parse_candidate(b'<!DOCTYPE article SYSTEM "http://127.0.0.1/private">' + XML).tag
        == "article"
    )


@pytest.mark.parametrize("tamper", [False, True])
def test_bridge_preserves_xpm_errors_and_hides_payload(tamper):
    scope, package, _, value = sample()
    response = execution(package, scope, errors=2, queries=True)
    value["report_sha256"] = response.attestation.report_sha256
    if tamper:
        value["scope"] = dict(scope, resource_id=str(uuid4()))
    response = response.model_copy(update={"query_evidence": QueryEvidence.model_validate(value)})
    result = assess_xpm_execution(
        xml=XML, package=package, expected_scope=scope, executor=lambda *_args: response
    )
    assert result["counts"]["errors"] == 2 and not result["raw_passed"]
    assert not result["required_queries_complete"]
    assert "Ana" not in json.dumps(result)
    if tamper:
        assert result["selected_queries"]["status"] == "unavailable"
    else:
        assert result["selected_queries"]["selected_checks_matched"]


def test_private_dns_denied_before_tls(monkeypatch):
    monkeypatch.setattr(
        collector.socket, "getaddrinfo", lambda *_a, **_k: [(2, 1, 6, "", ("127.0.0.1", 443))]
    )
    monkeypatch.setattr(
        collector.socket, "create_connection", lambda *_a, **_k: pytest.fail("network")
    )
    with pytest.raises(ValueError):
        collector.fetch("crossref", "10.1234/test")


@pytest.mark.parametrize("failure", ["timeout", "nonzero", "invalid_json", "oversize", "none"])
def test_collector_seals_unavailable_without_exception_text(tmp_path, monkeypatch, failure):
    from types import SimpleNamespace

    scope, _, _, value = sample()
    calls = []

    def run(args, **kwargs):
        assert args[-3:] == ["-m", "ops.xpm_authority_collect", "--fetch"]
        assert 0 < kwargs["timeout"] <= 15
        calls.append(json.loads(kwargs["input"]))
        if failure == "timeout":
            raise collector.subprocess.TimeoutExpired("private-secret", 15)
        raw = value["receipts"][len(calls) - 1]["payload"].encode()
        if failure == "invalid_json":
            raw = b"private-secret"
        if failure == "oversize":
            raw = b"x" * (collector.MAX_RESPONSE + 1)
        return SimpleNamespace(returncode=1 if failure == "nonzero" else 0, stdout=raw)

    monkeypatch.setattr(collector.subprocess, "run", run)
    evidence = collector.collect(XML, scope, "b" * 64, tmp_path)
    assert len(calls) == 2
    assert all(
        r["status"] == ("available" if failure == "none" else "unavailable")
        for r in evidence["receipts"]
    )
    assert "private-secret" not in (tmp_path / "query-evidence.json").read_text()


@pytest.mark.parametrize(
    "failure", ["none", "redirect", "not_found", "content_type", "oversized", "json", "tls"]
)
def test_fetch_pins_public_address_and_checks_response(monkeypatch, failure):
    from types import SimpleNamespace

    seen = {}
    raw = SimpleNamespace(close=lambda: seen.update(raw_closed=True))

    class Connection:
        sock = None

        def __init__(self, host, timeout):
            assert host == "api.crossref.org" and timeout == 8

        def request(self, method, path, headers):
            assert method == "GET" and path == "/works/10.1234%2Ftest"
            assert headers["Accept"] == "application/json"

        def getresponse(self):
            return SimpleNamespace(
                status=302 if failure == "redirect" else 404 if failure == "not_found" else 200,
                getheader=lambda *_args: (
                    "text/html" if failure == "content_type" else "application/json"
                ),
                read=lambda n: (
                    b"x" * n
                    if failure == "oversized"
                    else b"invalid"
                    if failure == "json"
                    else b"{}"
                ),
            )

        def close(self):
            seen["closed"] = True

    def connect(address, timeout):
        assert address == ("1.1.1.1", 443) and timeout == 8
        return raw

    def wrap(value, server_hostname):
        assert value is raw and server_hostname == "api.crossref.org"
        if failure == "tls":
            raise collector.ssl.SSLError("private TLS detail")
        return raw

    monkeypatch.setattr(
        collector.socket, "getaddrinfo", lambda *_a, **_k: [(2, 1, 6, "", ("1.1.1.1", 443))]
    )
    monkeypatch.setattr(collector.socket, "create_connection", connect)
    monkeypatch.setattr(collector.http.client, "HTTPSConnection", Connection)
    monkeypatch.setattr(
        collector.ssl, "create_default_context", lambda: SimpleNamespace(wrap_socket=wrap)
    )
    if failure == "none":
        assert collector.fetch("crossref", "10.1234/test") == b"{}"
    else:
        with pytest.raises((ValueError, collector.ssl.SSLError)):
            collector.fetch("crossref", "10.1234/test")
    assert seen["closed"]
    if failure == "tls":
        assert seen["raw_closed"]


def test_collection_global_deadline_retains_unavailable_receipts(tmp_path, monkeypatch):
    scope, _, _, _ = sample()
    times = iter([0, 71, 72])
    monkeypatch.setattr(collector.time, "monotonic", lambda: next(times))
    monkeypatch.setattr(collector.subprocess, "run", lambda *_a, **_k: pytest.fail("past deadline"))
    result = collector.collect(XML, scope, "b" * 64, tmp_path)
    assert len(result["receipts"]) == 2
    assert all(r["status"] == "unavailable" for r in result["receipts"])


@pytest.mark.parametrize("kind", ["matched", "conflict", "unavailable", "tampered"])
def test_formal_package_preserves_semantic_failures_even_without_xpm_errors(kind):
    from idml_foundation.services.package_validation import assess_package
    from tests.test_package_formal_validation import completed

    scope, package, _, value = sample()
    response = execution(package, scope, errors=0, queries=True)
    value["report_sha256"] = response.attestation.report_sha256
    if kind == "conflict":
        row = value["receipts"][1]
        body = json.loads(row["payload"])
        body["name"]["given-names"]["value"] = "Different"
        row["payload"] = json.dumps(body)
        row["response_sha256"] = sha(row["payload"].encode())
    elif kind == "unavailable":
        value["receipts"][1].update(status="unavailable", payload=None, response_sha256=None)
    elif kind == "tampered":
        value["report_sha256"] = "c" * 64
    response = response.model_copy(update={"query_evidence": QueryEvidence.model_validate(value)})
    result = assess_package(
        xml=XML,
        package=package,
        expected_scope=scope,
        executor=completed,
        xpm_executor=lambda *_args: response,
    )
    assert not result["complete"] and not result["ready_for_scielo"]
    if kind == "conflict":
        assert result["state"] == "blocked"
        assert "xpm-authority-response-conflict" in result["reasons"]
    elif kind in {"unavailable", "tampered"}:
        assert "xpm-authority-response-unavailable" in result["reasons"]
    assert "xpm-required-queries-incomplete" in result["reasons"]
