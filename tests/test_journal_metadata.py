import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from idml_foundation.ai.security import payload_digest
from idml_foundation.domain.canonical import CanonicalArticle
from idml_foundation.pipeline.profile import load_profile
from idml_foundation.pipeline.service import DeterministicPipeline
from idml_foundation.release import journal_metadata as module
from tests.phase3_helpers import synthetic_idml
from tests.test_enrichment_bundles import bundle, select  # noqa: F401 - fixture

PROFILE = Path(__file__).resolve().parents[1] / "profiles/esa-aop-1.1.json"


@pytest.fixture
def prepared(monkeypatch):
    # Public synthetic registry fixture; real pinned registry is exercised in native qualification.
    registry = (
        "scl\t1413-4152\t1413-4152\t1809-4457\tBrasil\tesa\tEng. Sanit. Ambient.\t"
        + module.TITLE
        + "\t\t"
        + module.PUBLISHER
        + "\turl\tby/4.0\n"
    ).encode()
    monkeypatch.setattr(module, "REGISTRY_SHA256", hashlib.sha256(registry).hexdigest())
    source = synthetic_idml()
    result = DeterministicPipeline(profile=load_profile(PROFILE)).run(
        source, logical_name="ESA_2024001_AOP.idml"
    )
    catalog = module.build_journal_metadata_catalog(
        result.canonical,
        source_idml_sha256=hashlib.sha256(source).hexdigest(),
        registry=registry,
        collected_at=datetime.now(UTC) - timedelta(minutes=2),
        corpus_id="synthetic",
    )
    return source, result, catalog, registry


def test_pipeline_changes_only_two_journal_fields_and_adds_provenance(prepared):
    source, before, catalog, _ = prepared
    result = DeterministicPipeline(
        profile=load_profile(PROFILE), journal_metadata_catalog=catalog
    ).run(source, logical_name="ESA_2024001_AOP.idml")
    old = before.canonical.model_dump(mode="json")
    new = result.canonical.model_dump(mode="json")
    assert new["front"]["journal"]["title"]["value"] == module.TITLE
    assert new["front"]["journal"]["publisher_name"]["value"] == module.PUBLISHER
    assert len(new["evidence"]) == len(old["evidence"]) + 1
    assert len(new["review_reasons"]) == len(old["review_reasons"]) + 1
    for name in ("title", "publisher_name"):
        assert set(old["front"]["journal"][name]["evidence_ids"]) <= set(
            new["front"]["journal"][name]["evidence_ids"]
        )
        new["front"]["journal"][name] = old["front"]["journal"][name]
    new["evidence"], new["review_reasons"] = old["evidence"], old["review_reasons"]
    assert new == old and result.validation.valid
    assert (
        catalog.apply(result.canonical, source_idml_sha256=catalog.source_idml_sha256)
        == result.canonical
    )


@pytest.mark.parametrize("field", ["title", "publisher_name", "abbreviated_title"])
def test_changed_or_human_edited_journal_refused(prepared, field):
    _, before, catalog, _ = prepared
    data = before.canonical.model_dump(mode="json")
    data["front"]["journal"][field]["value"] = "Operator decision"
    with pytest.raises(ValueError):
        catalog.apply(
            CanonicalArticle.model_validate(data), source_idml_sha256=catalog.source_idml_sha256
        )


def test_idempotence_cannot_hide_other_journal_change(prepared):
    _, before, catalog, _ = prepared
    result = catalog.apply(before.canonical, source_idml_sha256=catalog.source_idml_sha256)
    data = result.model_dump(mode="json")
    data["front"]["journal"]["abbreviated_title"]["value"] = "Changed"
    with pytest.raises(ValueError, match="stale_or_changed"):
        catalog.apply(
            CanonicalArticle.model_validate(data), source_idml_sha256=catalog.source_idml_sha256
        )


@pytest.mark.parametrize(
    "change", ["hash", "source", "profile", "identity", "ambiguous", "registry"]
)
def test_wrong_bindings_refused(prepared, change):
    _, before, catalog, registry = prepared
    article = before.canonical.model_dump(mode="json")
    with pytest.raises(ValueError):
        if change == "registry":
            module.verify_registry(registry + b"tampered")
        elif change == "hash":
            module.JournalMetadataCatalog.model_validate(
                {**catalog.model_dump(), "catalog_id": "a" * 64}
            )
        else:
            if change == "profile":
                article["journal_profile_id"] = "esa-aop-1.0.0"
            elif change == "identity":
                article["front"]["journal"]["identifiers"][0]["value"]["value"] = "other"
            elif change == "ambiguous":
                article["front"]["journal"]["title"]["alternatives"] = ["a", "b"]
            catalog.apply(
                CanonicalArticle.model_validate(article),
                source_idml_sha256="b" * 64 if change == "source" else catalog.source_idml_sha256,
            )


def test_catalog_cannot_claim_unreviewed_registry_even_with_new_id(prepared):
    value = prepared[2].model_dump(mode="json", exclude={"catalog_id"})
    value["response_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="unqualified_snapshot"):
        module.JournalMetadataCatalog.model_validate({**value, "catalog_id": payload_digest(value)})


@pytest.fixture
def journal_bundle(settings, bundle, prepared):  # noqa: F811
    from idml_foundation.services.enrichment import bundle_path

    _, _, old_folder, manifest = bundle
    source, _, catalog, _ = prepared
    settings.journal_profile_path = PROFILE
    content = catalog.model_dump_json().encode()
    manifest.update(
        source_idml_sha256=catalog.source_idml_sha256, profile_id=catalog.journal_profile_id
    )
    manifest["catalogs"] = {"journal_metadata_catalog": hashlib.sha256(content).hexdigest()}
    folder = settings.enrichment_root / bundle_path(
        manifest["organization_id"], manifest["resource_id"], catalog.source_idml_sha256
    )
    old_folder.rename(folder)
    (folder / "journal_metadata_catalog.json").write_bytes(content)
    (folder / "manifest.json").write_text(json.dumps(manifest))
    path = settings.enrichment_root / "authorizations" / f"{manifest['authorization_id']}.json"
    grant = json.loads(path.read_text())
    grant.update(
        source_idml_sha256=catalog.source_idml_sha256, profile_id=catalog.journal_profile_id
    )
    grant["catalogs"] = {
        "journal_metadata_catalog": {
            "source": "scielo_journal_registry",
            "catalog_sha256": hashlib.sha256(content).hexdigest(),
            "evidence_sha256": catalog.response_sha256,
            "collected_at": catalog.collected_at.isoformat(),
        }
    }
    path.write_text(json.dumps(grant))
    return source, catalog, folder, manifest, path


def test_registry_catalog_reaches_worker(db, settings, journal_bundle, monkeypatch):
    import tests.test_enrichment_bundles as harness

    monkeypatch.setattr(
        harness,
        "DeterministicPipeline",
        lambda **kw: DeterministicPipeline(
            profile=load_profile(PROFILE), journal_metadata_catalog=kw["formula_catalog"]
        ),
    )
    harness.test_worker_uses_bound_catalog_and_records_provenance(db, settings, journal_bundle[:4])


@pytest.mark.parametrize(
    "change",
    [
        "source",
        "hash",
        "date",
        "stale",
        "future",
        "revoked",
        "organization_id",
        "resource_id",
        "destination",
        "expired",
    ],
)
def test_registry_grants_enforce_authority_scope_and_freshness(settings, journal_bundle, change):
    _, _, _, manifest, path = journal_bundle
    assert select(settings, manifest).catalogs
    grant = json.loads(path.read_text())
    permission = grant["catalogs"]["journal_metadata_catalog"]
    if change == "source":
        permission["source"] = "authorized_article"
    elif change == "hash":
        permission["evidence_sha256"] = "0" * 64
    elif change == "revoked":
        grant["status"] = "revoked"
    elif change in {"organization_id", "resource_id"}:
        grant[change] = str(uuid4())
    elif change == "destination":
        grant["destination"] = "vps"
    elif change == "expired":
        grant["expires_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    else:
        delta = {
            "date": timedelta(minutes=-3),
            "stale": timedelta(days=-8),
            "future": timedelta(days=1),
        }
        permission["collected_at"] = (datetime.now(UTC) + delta[change]).isoformat()
    path.write_text(json.dumps(grant))
    with pytest.raises(ValueError, match="enrichment_bundle_invalid"):
        select(settings, manifest)
