import hashlib
import json
from copy import deepcopy
from zipfile import ZipFile

import pytest

from ops import audit_vh1_xpm_online as audit_module
from ops.audit_vh1_xpm_online import audit, catalogue_comparison, sealed, transport_evidence
from ops.qualify_vh1_xpm_linux import mutate
from ops.run_xpm_qualification import ARCHIVE_SHA256, digest, inspect_report

XML = b"""<article><front><journal-meta>
<journal-id journal-id-type="publisher-id">esa</journal-id>
<journal-title-group><journal-title>Journal</journal-title></journal-title-group>
<issn pub-type="ppub">1111-1111</issn><issn pub-type="epub">2222-2222</issn>
<publisher><publisher-name>Publisher</publisher-name></publisher>
</journal-meta></front></article>"""
CATALOGUE = (
    b"scl\t1111-1111\t1111-1111\t2222-2222\tBrasil\tesa\tJ.\tJournal\t\tPublisher\turl\tby/4.0\n"
)


def test_exact_catalogue_match_is_not_xml_approval():
    result = catalogue_comparison(XML, CATALOGUE)
    assert all(value["matches"] for value in result.values())
    assert "release_approved" not in result
    assert "Journal" not in json.dumps(result)


@pytest.mark.parametrize("old,new", [(b"Journal", b"JournAl"), (b"Publisher", b"Publisher - ABES")])
def test_real_metadata_difference_stays_visible(old, new):
    result = catalogue_comparison(XML.replace(old, new), CATALOGUE)
    assert sum(not value["matches"] for value in result.values()) == 1


@pytest.mark.parametrize(
    "catalogue",
    [b"", CATALOGUE * 2, CATALOGUE.replace(b"scl", b"other"), CATALOGUE.replace(b"2222", b"9999")],
)
def test_missing_ambiguous_or_other_journal_not_accepted(catalogue):
    with pytest.raises(ValueError, match="catalogue_match_not_unique"):
        catalogue_comparison(XML, catalogue)


def test_xml_entities_never_resolved():
    with pytest.raises(ValueError, match="unsafe_xml"):
        catalogue_comparison(
            b'<!DOCTYPE article [<!ENTITY x SYSTEM "file:///secret">]>' + XML, CATALOGUE
        )


def test_duplicate_candidate_field_denied():
    with pytest.raises(ValueError, match="journal_field_not_unique"):
        catalogue_comparison(XML.replace(b"<journal-title>Journal</journal-title>", b""), CATALOGUE)


def test_sealed_file_rejects_tampering(tmp_path):
    path = tmp_path / "proof"
    path.write_bytes(b"original")
    expected = digest(path)
    path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="evidence_hash_mismatch"):
        sealed(path, expected)


def events():
    catalogue = {
        "event": "catalogue_https_response",
        "status": 200,
        "sha256": hashlib.sha256(CATALOGUE).hexdigest(),
        "bytes": len(CATALOGUE),
        "last_modified": "synthetic",
    }
    return [deepcopy(catalogue) for _ in range(3)] + [
        {"event": "tls_tunnel", "host": host, "result": "closed"}
        for host in ("api.crossref.org", "orcid.org")
    ]


def test_closed_tls_tunnels_do_not_prove_semantic_validation():
    result = transport_evidence(events(), hashlib.sha256(CATALOGUE).hexdigest())
    assert result["catalogue_https_responses"] == 3
    assert not result["all_external_queries_completed"]
    assert not result["authenticated_orcid_ownership_proven"]


@pytest.mark.parametrize("key,value", [("status", 403), ("sha256", "b" * 64), ("bytes", 0)])
def test_catalogue_response_requires_complete_transport_evidence(key, value):
    values = events()
    values[0][key] = value
    with pytest.raises(ValueError, match="catalogue_transport_unproven"):
        transport_evidence(values, hashlib.sha256(CATALOGUE).hexdigest())


@pytest.fixture
def synthetic_run(tmp_path, monkeypatch):
    # Generated fixtures test the audit, not the vendor. Native proof is stored separately.
    run = tmp_path / "run"
    run.mkdir()
    baseline = tmp_path / "baseline"
    packages, cases = {}, []
    for article, mutation in sorted(audit_module.MATRIX):
        original = {
            "1809-4457-esa-30-e20240086.xml": XML,
            "1809-4457-esa-30-e20240086-gf01.jpg": b"asset",
        }
        source = baseline / article / "candidate.zip"
        if not source.exists():
            source.parent.mkdir(parents=True)
            with ZipFile(source, "w") as archive:
                for name, data in original.items():
                    archive.writestr(name, data)
        packages[article] = digest(source)
        folder = run / (article + "-" + mutation)
        work = folder / "work"
        work.mkdir(parents=True)
        (folder / "input").mkdir()
        (work / "input_xpm/errors").mkdir(parents=True)
        (work / "input_xpm/scielo_package").mkdir()
        members = mutate(original, mutation)
        manifest = {}
        for name, data in members.items():
            (folder / "input" / name).write_bytes(data)
            (work / "input_xpm/scielo_package" / name).write_bytes(data)
            manifest[name] = hashlib.sha256(data).hexdigest()
        count = 4 if mutation == "missing_graphic" else 3
        message = (
            "Not found 1809-4457-esa-30-e20240086-gf01.jpg in the package."
            if mutation == "missing_graphic"
            else "baseline"
        )
        report = work / "input_xpm/errors/xpm.html"
        report.write_text(
            "<html><body><!-- 4.0.096 22/04/2019 -->"
            f"Total of blocking errors: {count} Total of fatal errors: 1 "
            f"Total of errors: 5 Total of warnings: 2 <p>{message}</p></body></html>",
            encoding="utf-8",
        )
        for stream in ("stdout", "stderr"):
            (work / (stream + ".log")).write_bytes(b"synthetic")
        execution = {
            "archive_sha256": ARCHIVE_SHA256,
            "runner_sha256": digest(audit_module.REPO / "ops/run_xpm_online_qualification.py"),
            "proxy_source_sha256": digest(audit_module.REPO / "ops/xpm_egress_proxy.py"),
            "returncode": 0,
            "timed_out": False,
            "network": "internal_bridge_via_allowlisted_proxy",
            "input_unchanged": True,
            "vendor_files_unchanged": True,
            "input_manifest": manifest,
            "generated_package_manifest": manifest,
            "reports": {"input_xpm/errors/xpm.html": inspect_report(report)},
            "catalogue_sha256": hashlib.sha256(CATALOGUE).hexdigest(),
            "catalogue_bytes": len(CATALOGUE),
            "stdout_sha256": digest(work / "stdout.log"),
            "stderr_sha256": digest(work / "stderr.log"),
            "elapsed_seconds": 1,
            "child_max_rss_kib": 100,
            "release_approved": False,
            "sps_1_10_compatibility_proven": False,
            "authenticated_orcid_ownership_proven": False,
        }
        execution_path = work / "execution.json"
        execution_path.write_text(json.dumps(execution))
        cases.append(
            {
                "article": article,
                "mutation": mutation,
                "original_package_sha256": packages[article],
                "actual_image": "sha256:" + "a" * 64,
                "actual_network": "idml-xpm-net-synthetic",
                "docker_exit_code": 0,
                "oom_killed": False,
                "execution": execution,
                "execution_sha256": digest(execution_path),
            }
        )
    (run / "proxy").mkdir()
    (run / "proxy/catalogue.csv").write_bytes(CATALOGUE)
    (run / "proxy/events.jsonl").write_text("\n".join(json.dumps(e) for e in events()))
    health = {"services": ["test-service"], "readiness": {"status": "ok"}}
    raw = {
        "run_id": "synthetic",
        "image": "sha256:" + "a" * 64,
        "cases": cases,
        "before": health,
        "after": health,
        "services_unchanged": True,
        "boundary_denials": [True, True, True],
        "release_approved": False,
        "production_deployed": False,
        "sps_1_10_compatibility_proven": False,
        "proxy_events_sha256": digest(run / "proxy/events.jsonl"),
        "host_sources_sha256": {
            name: digest(audit_module.REPO / "ops" / name)
            for name in ("qualify_vh1_xpm_online.py", "qualify_vh1_xpm_linux.py")
        },
    }
    (run / "report.json").write_text(json.dumps(raw))
    monkeypatch.setattr(audit_module, "BASELINE", baseline)
    monkeypatch.setattr(audit_module, "PACKAGES", packages)
    return run, raw


def test_complete_audit_preserves_native_severities_and_denies_approval(synthetic_run):
    run, _ = synthetic_run
    result = audit(run)
    assert len(result["cases"]) == 3 and result["negative_control_detected"]
    assert not result["release_approved"]
    assert all(c["counts"]["errors"] == 5 and not c["validation_approved"] for c in result["cases"])


@pytest.mark.parametrize(
    "key,value",
    [
        ("release_approved", True),
        ("production_deployed", True),
        ("sps_1_10_compatibility_proven", True),
        ("services_unchanged", False),
        ("boundary_denials", [True, False, True]),
        ("host_sources_sha256", {}),
        ("proxy_events_sha256", "a" * 64),
    ],
)
def test_top_level_tampering_rejected(synthetic_run, key, value):
    run, raw = synthetic_run
    raw[key] = value
    (run / "report.json").write_text(json.dumps(raw))
    with pytest.raises(ValueError):
        audit(run)


@pytest.mark.parametrize(
    "key,value",
    [
        ("actual_image", "wrong"),
        ("actual_network", "bridge"),
        ("docker_exit_code", 1),
        ("oom_killed", True),
        ("original_package_sha256", "a" * 64),
    ],
)
def test_execution_identity_tampering_rejected(synthetic_run, key, value):
    run, raw = synthetic_run
    raw["cases"][0][key] = value
    (run / "report.json").write_text(json.dumps(raw))
    with pytest.raises(ValueError):
        audit(run)


@pytest.mark.parametrize(
    "relative", ["work/execution.json", "work/input_xpm/errors/xpm.html", "work/stdout.log"]
)
def test_private_artifact_tampering_rejected(synthetic_run, relative):
    run, raw = synthetic_run
    case = raw["cases"][0]
    folder = run / (case["article"] + "-" + case["mutation"])
    with (folder / relative).open("ab") as stream:
        stream.write(b"tampered")
    with pytest.raises(ValueError, match="evidence_hash_mismatch"):
        audit(run)
