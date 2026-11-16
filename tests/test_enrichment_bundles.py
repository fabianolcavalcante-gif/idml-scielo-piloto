import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from idml_foundation.ai.formula_catalog import build_formula_transcription_catalog
from idml_foundation.ai.security import payload_digest
from idml_foundation.ingest.scanner import PolicyOnlyScanner
from idml_foundation.models import Job, Organization, Resource
from idml_foundation.pipeline.service import DeterministicPipeline
from idml_foundation.services.artifacts import store_idml_artifact
from idml_foundation.services.enrichment import bundle_path, select_enrichment
from idml_foundation.worker import _process_idml_job
from tests.test_formula_catalog import _qualified_fixture


@pytest.fixture
def bundle(tmp_path, settings):
    source, dataset, result = _qualified_fixture()
    catalog, _ = build_formula_transcription_catalog(
        dataset=dataset,
        dataset_sha256=payload_digest(dataset),
        journal_profile_id="esa-aop-1.0.0",
        results=(result,),
    )
    org, resource = str(uuid4()), str(uuid4())
    source_hash = hashlib.sha256(source).hexdigest()
    settings.enrichment_root = tmp_path / "trusted"
    settings.enrichment_location = "local"
    folder = settings.enrichment_root / bundle_path(org, resource, source_hash)
    folder.mkdir(parents=True)
    content = catalog.model_dump_json().encode()
    (folder / "formula_catalog.json").write_bytes(content)
    manifest = {
        "version": "enrichment-bundle-1.1",
        "authorization_id": str(uuid4()),
        "organization_id": org,
        "resource_id": resource,
        "source_idml_sha256": source_hash,
        "profile_id": "esa-aop-1.0.0",
        "catalogs": {"formula_catalog": hashlib.sha256(content).hexdigest()},
    }
    (folder / "manifest.json").write_text(json.dumps(manifest))
    now = datetime.now(UTC)
    grant = {
        "version": "source-authorization-1.0",
        "authorization_id": manifest["authorization_id"],
        "organization_id": org,
        "resource_id": resource,
        "source_idml_sha256": source_hash,
        "profile_id": manifest["profile_id"],
        "destination": "local",
        "status": "active",
        "decision_id": str(uuid4()),
        "decision_sha256": "a" * 64,
        "issued_at": (now - timedelta(minutes=1)).isoformat(),
        "expires_at": (now + timedelta(days=1)).isoformat(),
        "catalogs": {
            "formula_catalog": {
                "source": "authorized_article",
                "catalog_sha256": manifest["catalogs"]["formula_catalog"],
                "evidence_sha256": "b" * 64,
                "collected_at": (now - timedelta(minutes=2)).isoformat(),
            }
        },
    }
    grants = settings.enrichment_root / "authorizations"
    grants.mkdir()
    (grants / f"{manifest['authorization_id']}.json").write_text(json.dumps(grant))
    return source, catalog, folder, manifest


def select(settings, manifest, **overrides):
    args = dict(
        organization_id=manifest["organization_id"],
        resource_id=manifest["resource_id"],
        source_sha256=manifest["source_idml_sha256"],
        profile_id=manifest["profile_id"],
    )
    args.update(overrides)
    return select_enrichment(settings, **args)


def test_bundle_matches_qualified_pipeline(settings, bundle):
    source, catalog, _, manifest = bundle
    chosen = select(settings, manifest)
    actual = chosen.pipeline(settings).run(source, logical_name="ESA_2024001_AOP.idml")
    expected = DeterministicPipeline(formula_catalog=catalog).run(
        source, logical_name="ESA_2024001_AOP.idml"
    )
    assert actual.xml == expected.xml
    assert chosen.provenance["human_review_required"]
    assert "<mml" not in json.dumps(chosen.provenance)


@pytest.mark.parametrize("field", ["organization_id", "resource_id", "source_sha256"])
def test_other_scope_never_loads_catalog(settings, bundle, field):
    _, _, _, manifest = bundle
    value = "a" * 64 if field == "source_sha256" else str(uuid4())
    result = select(settings, manifest, **{field: value})
    assert not result.catalogs
    assert result.provenance["status"] == "no_matching_bundle"


@pytest.mark.parametrize("kind", ["hash", "scope", "missing", "kind", "profile", "oversize"])
def test_invalid_bundle_fails_closed_without_content(settings, bundle, kind):
    _, _, folder, manifest = bundle
    original = dict(manifest)
    if kind == "hash":
        (folder / "formula_catalog.json").write_bytes(b"private corrupted metadata")
    elif kind == "missing":
        (folder / "formula_catalog.json").unlink()
    elif kind == "scope":
        manifest["organization_id"] = str(uuid4())
    elif kind == "profile":
        manifest["profile_id"] = "other"
    elif kind == "kind":
        manifest["catalogs"] = {"../../private": "a" * 64}
    elif kind == "oversize":
        (folder / "manifest.json").write_bytes(b"x" * 16385)
    if kind in {"scope", "profile", "kind"}:
        (folder / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match=r"^enrichment_bundle_invalid$"):
        select(settings, original)


def test_worker_uses_bound_catalog_and_records_provenance(db, settings, bundle):
    _exercise_catalog_worker(db, settings, bundle, None)


def test_worker_rechecks_consent_before_storing_conversion(db, settings, bundle, monkeypatch):
    _exercise_catalog_worker(db, settings, bundle, monkeypatch)


def _exercise_catalog_worker(db, settings, bundle, monkeypatch):
    source, catalog, _, manifest = bundle
    org = Organization(id=manifest["organization_id"], slug="bundle", name="Bundle")
    db.add(org)
    db.flush()
    resource = Resource(id=manifest["resource_id"], organization_id=org.id, title="Test")
    db.add(resource)
    db.flush()
    artifact, _ = store_idml_artifact(
        db,
        organization_id=org.id,
        original_name="ESA_2024001_AOP.idml",
        data=source,
        scanner=PolicyOnlyScanner(),
        settings=settings,
    )
    job = Job(
        organization_id=org.id,
        kind="idml.process",
        idempotency_key="bundle-test",
        payload={"resource_id": resource.id, "idml_artifact_id": artifact.id},
    )
    db.add(job)
    db.flush()
    if monkeypatch is not None:
        run = DeterministicPipeline.run

        def revoke(pipeline, *args, **kwargs):
            output = run(pipeline, *args, **kwargs)
            path = (
                settings.enrichment_root / "authorizations" / f"{manifest['authorization_id']}.json"
            )
            decision = json.loads(path.read_bytes())
            decision["status"] = "revoked"
            path.write_text(json.dumps(decision))
            return output

        monkeypatch.setattr(DeterministicPipeline, "run", revoke)
        with pytest.raises(ValueError, match="enrichment_bundle_invalid"):
            _process_idml_job(db, job, settings)
        return
    result = _process_idml_job(db, job, settings)
    expected = DeterministicPipeline(formula_catalog=catalog).run(
        source, logical_name=artifact.original_name
    )
    assert result["xml_sha256"] == hashlib.sha256(expected.xml).hexdigest()
    assert result["enrichment"]["status"] == "selected"


def test_disabled_enrichment_preserves_default(settings):
    result = select_enrichment(
        settings, organization_id="", resource_id="", source_sha256="", profile_id=""
    )
    assert result.provenance == {"status": "not_configured"}


@pytest.mark.parametrize(
    "mutation",
    [
        "organization",
        "resource",
        "input",
        "profile",
        "destination",
        "revoked",
        "expired",
        "future",
        "lifetime",
        "catalog_hash",
        "source",
        "stale",
        "timezone",
        "missing",
        "identity",
        "unknown_kind",
    ],
)
def test_authorization_rejections_and_revocation_not_cached(settings, bundle, mutation):
    _, _, _, manifest = bundle
    assert select(settings, manifest).catalogs
    path = settings.enrichment_root / "authorizations" / f"{manifest['authorization_id']}.json"
    grant = json.loads(path.read_text())
    now = datetime.now(UTC)
    changes = {
        "organization": ("organization_id", str(uuid4())),
        "resource": ("resource_id", str(uuid4())),
        "input": ("source_idml_sha256", "c" * 64),
        "profile": ("profile_id", "other"),
        "destination": ("destination", "vps"),
        "revoked": ("status", "revoked"),
        "expired": ("expires_at", now.isoformat()),
        "future": ("issued_at", (now + timedelta(days=1)).isoformat()),
        "lifetime": ("expires_at", (now + timedelta(days=31)).isoformat()),
        "timezone": ("issued_at", "2026-10-01T00:00:00"),
        "identity": ("authorization_id", str(uuid4())),
    }
    if mutation in changes:
        key, value = changes[mutation]
        grant[key] = value
    elif mutation == "catalog_hash":
        grant["catalogs"]["formula_catalog"]["catalog_sha256"] = "c" * 64
    elif mutation == "source":
        grant["catalogs"]["formula_catalog"]["source"] = "crossref_public_record"
    elif mutation == "stale":
        grant["catalogs"]["formula_catalog"]["collected_at"] = (
            now - timedelta(days=31)
        ).isoformat()
    elif mutation == "unknown_kind":
        grant["catalogs"]["unknown"] = grant["catalogs"]["formula_catalog"]
    path.write_text(json.dumps(grant))
    if mutation == "missing":
        path.unlink()
    with pytest.raises(ValueError, match=r"^enrichment_bundle_invalid$"):
        select(settings, manifest)


def test_legacy_bundle_cannot_bypass_consent(settings, bundle):
    _, _, folder, manifest = bundle
    manifest["version"] = "enrichment-bundle-1.0"
    manifest.pop("authorization_id")
    (folder / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match=r"^enrichment_bundle_invalid$"):
        select(settings, manifest)


def test_location_must_be_explicit(settings, bundle):
    settings.enrichment_location = None
    with pytest.raises(ValueError, match=r"^enrichment_bundle_invalid$"):
        select(settings, bundle[3])


def test_provision_is_atomic_and_cannot_create_consent(settings, bundle, tmp_path):
    from ops.provision_enrichment import provision

    _, _, folder, manifest = bundle
    incoming = tmp_path / "incoming"
    folder.rename(incoming)
    result = provision(settings, incoming)
    assert result["status"] == "provisioned"
    assert select(settings, manifest).catalogs
    assert not list(settings.enrichment_root.glob(".provision-*"))
    with pytest.raises(ValueError, match=r"^enrichment_provision_invalid$"):
        provision(settings, incoming)


def test_provision_rejected_grant_leaves_no_bundle(settings, bundle, tmp_path):
    from ops.provision_enrichment import provision

    _, _, folder, manifest = bundle
    incoming = tmp_path / "incoming"
    folder.rename(incoming)
    grant = settings.enrichment_root / "authorizations" / f"{manifest['authorization_id']}.json"
    grant.unlink()
    with pytest.raises(ValueError, match=r"^enrichment_provision_invalid$"):
        provision(settings, incoming)
    assert not folder.exists()
    assert not list(settings.enrichment_root.glob(".provision-*"))
