import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from ops import article_authority_collect as collector
from ops import runtime_source_authority as runtime
from ops import scoped_authority_transport as transport
from tests.test_scoped_authority_transport import fixture, sha


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    scope, _, _, files, xml, _package = fixture()
    root = tmp_path / "authority"
    (root / "authorizations").mkdir(parents=True)
    (root / "bundles").mkdir()
    candidate = tmp_path / "input.xml"
    candidate.write_bytes(xml)
    approved = dict(
        version="public-validation-sources-1.0",
        decision_id=str(uuid4()),
        decision_sha256="c" * 64,
        scope=scope,
        expires_at=(datetime.now(UTC) + timedelta(days=7)).isoformat(),
    )
    calls = []
    monkeypatch.setattr(runtime, "decision", lambda scope: approved.copy())
    monkeypatch.setattr(runtime, "collect", lambda xml, scope: calls.append(True) or files.copy())

    def read(path, limit):
        raw = Path(path).read_bytes()
        assert len(raw) <= limit
        return raw

    monkeypatch.setattr(runtime, "trusted_read", read)
    monkeypatch.setattr(
        runtime,
        "load_selection",
        lambda root, scope: transport.load_selection(root, scope, reader=read),
    )
    return root, scope, candidate, approved, calls, files


def test_fresh_collection_cached_per_exact_scope_and_consent(prepared):
    root, scope, candidate, approved, calls, _ = prepared
    assert runtime.prepare(root, scope, candidate, "packtools") == approved
    assert runtime.prepare(root, scope, candidate, "packtools") == approved
    assert len(calls) == 1
    approved["decision_id"] = str(uuid4())
    runtime.prepare(root, scope, candidate, "packtools")
    assert len(calls) == 2 and len(list((root / "history").iterdir())) == 1
    scope["package_sha256"] = "d" * 64
    # Sources must be fetched again and rebound when the candidate package changes.
    with pytest.raises(ValueError, match="candidate_mismatch"):
        runtime.prepare(root, scope, candidate, "packtools")
    assert len(calls) == 3 and len(list((root / "bundles").iterdir())) == 1


@pytest.mark.parametrize(
    "mode",
    [
        "denied",
        "revoked_during_fetch",
        "changed_before_publish",
        "bad_hash",
        "locked",
        "tampered",
        "budget",
    ],
)
def test_no_unauthorized_or_partial_publication(prepared, monkeypatch, mode):
    root, scope, candidate, approved, calls, _files = prepared
    if mode == "denied":
        monkeypatch.setattr(
            runtime, "decision", lambda scope: (_ for _ in ()).throw(ValueError("denied"))
        )
    elif mode in {"revoked_during_fetch", "changed_before_publish"}:
        n = []

        def decide(scope):
            n.append(1)
            return (
                approved.copy()
                if len(n) < (2 if mode == "revoked_during_fetch" else 3)
                else approved | {"decision_id": str(uuid4())}
            )

        monkeypatch.setattr(runtime, "decision", decide)
    elif mode == "bad_hash":
        candidate.write_bytes(b"wrong")
    elif mode == "locked":
        (root / ".provision.lock").write_text("other admin")
    elif mode == "budget":
        for i in range(128):
            (root / "authorizations" / f"{i}.json").write_text("{}")
    else:
        runtime.prepare(root, scope, candidate, "packtools")
        bundle = next((root / "bundles").iterdir())
        (bundle / "crossref.json").write_bytes(b"tampered")
    with pytest.raises((ValueError, OSError)):
        runtime.prepare(root, scope, candidate, "packtools")
    if mode != "tampered":
        assert not list((root / "bundles").iterdir())
    if mode in {"denied", "bad_hash", "locked", "budget"}:
        assert not calls
    assert not list(root.glob("runtime-source-*"))


@pytest.mark.parametrize(
    "mode", ["crossref_failure", "journal_failure", "orcid_failure", "success"]
)
def test_collect_fixed_public_sources_and_honest_unavailability(monkeypatch, mode):
    xml = b"""<article><front><article-meta>
    <article-id pub-id-type="doi">10.1234/test</article-id><contrib-group><contrib>
    <name><surname>A</surname><given-names>B</given-names></name>
    <contrib-id contrib-id-type="orcid">0000-0002-1825-0097</contrib-id>
    </contrib></contrib-group></article-meta></front></article>"""
    scope = dict(journal_profile_id=collector.PROFILE, xml_sha256=sha(xml), package_sha256="b" * 64)
    seen = []

    def run(args, **kwargs):
        request = json.loads(kwargs["input"])
        seen.append(request)
        failure = request["kind"] + "_" + "failure" == mode or (
            mode == "journal_failure" and request["kind"] == "scielo_issue"
        )
        return SimpleNamespace(returncode=int(failure), stdout=b"{}")

    monkeypatch.setattr(collector.subprocess, "run", run)
    if mode in {"crossref_failure", "journal_failure"}:
        with pytest.raises(ValueError, match="required_public_source"):
            collector.collect(xml, scope)
    else:
        files = collector.collect(xml, scope)
        manifest = json.loads(files["editorial-manifest.json"])
        assert manifest["sources"]["0000-0002-1825-0097"]["status"] == (
            "unavailable" if mode == "orcid_failure" else "available"
        )
        assert "journal.json" in files and "crossref.json" in files
    assert all(set(r) == {"kind", "identifier"} for r in seen)


def test_no_arbitrary_url_or_private_network(monkeypatch):
    with pytest.raises(ValueError):
        collector.target_endpoint("scielo_issue", "http://127.0.0.1")
    monkeypatch.setattr(
        collector.network.socket,
        "getaddrinfo",
        lambda *a, **kw: [(2, 1, 6, "", ("127.0.0.1", 443))],
    )
    with pytest.raises(ValueError, match="address_denied"):
        collector.fetch("scielo_issue", collector.PROFILE)


@pytest.mark.parametrize("changed", [False, True])
def test_modern_broker_checks_consent_after_native_execution(tmp_path, monkeypatch, changed):
    from ops import scoped_validator_broker as broker

    scope, *_ = fixture()
    approved = {"decision_id": "synthetic"}
    binding = {"grant_sha256": "a" * 64}
    monkeypatch.setattr(runtime, "prepare", lambda *a: approved)
    monkeypatch.setattr(runtime, "decision", lambda *a: {} if changed else approved)
    monkeypatch.setattr(broker, "stage_selection", lambda *a: (tmp_path, binding))
    monkeypatch.setattr(broker, "load_selection", lambda *a: ({}, binding))
    monkeypatch.setattr(
        broker,
        "LEGACY_EXECUTE",
        lambda *a: json.dumps({"result": {"authority_evidence": {"binding": binding}}}).encode(),
    )
    spec = dict(
        _runtime_authorization=True, _authority_root=tmp_path, _scope=scope, name="packtools"
    )
    if changed:
        with pytest.raises(ValueError, match="consent_changed"):
            broker.execute(spec, tmp_path / "candidate.xml", tmp_path)
    else:
        assert broker.execute(spec, tmp_path / "candidate.xml", tmp_path)


@pytest.mark.parametrize("mode", ["failure", "wrong_scope", "expired", "extra", "success"])
def test_supervisor_only_accepts_bounded_current_database_decision(monkeypatch, mode):
    scope, *_ = fixture()
    response = dict(
        version="public-validation-sources-1.0",
        decision_id=str(uuid4()),
        decision_sha256="a" * 64,
        scope=scope,
        expires_at=(datetime.now(UTC) + timedelta(days=1)).isoformat(),
    )
    if mode == "wrong_scope":
        response["scope"] = scope | {"organization_id": str(uuid4())}
    if mode == "expired":
        response["expires_at"] = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    if mode == "extra":
        response["command"] = "untrusted"

    def run(args, **kwargs):
        assert (
            args[0] == "/usr/bin/docker"
            and args[-1] == "idml_foundation.services.article_source_access"
        )
        assert json.loads(kwargs["input"]) == scope and kwargs["timeout"] == 15
        return SimpleNamespace(
            returncode=int(mode == "failure"), stdout=json.dumps(response).encode()
        )

    monkeypatch.setattr(runtime.subprocess, "run", run)
    if mode == "success":
        assert runtime.decision(scope) == response
    else:
        with pytest.raises(ValueError):
            runtime.decision(scope)
