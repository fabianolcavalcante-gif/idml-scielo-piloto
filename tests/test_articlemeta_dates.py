import hashlib
import json
from datetime import UTC, datetime, timedelta
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from lxml import etree

from idml_foundation.ingest.scanner import PolicyOnlyScanner
from idml_foundation.models import Job, Organization, Resource
from idml_foundation.pipeline.service import DeterministicPipeline
from idml_foundation.release.articlemeta_dates import (
    MAX_RESPONSE,
    ArticleMetaDateCatalog,
    build_articlemeta_date_catalog,
    source_url,
)
from idml_foundation.services.artifacts import store_idml_artifact
from idml_foundation.worker import _process_idml_job
from tests.phase3_helpers import synthetic_idml
from tests.test_enrichment_bundles import bundle, select  # noqa: F401 - pytest fixture

PID = "S1234-56782024000100001"
DOI = "10.1234/synthetic"


def source():
    output = BytesIO()
    with (
        ZipFile(BytesIO(synthetic_idml(include_correspondence=True))) as archive,
        ZipFile(output, "w", ZIP_DEFLATED) as target,
    ):
        for name in archive.namelist():
            data = archive.read(name)
            if name == "Stories/Story_u1.xml":
                paragraph = (
                    '<ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/0.1.doi">'
                    '<CharacterStyleRange AppliedCharacterStyle="CharacterStyle/none">'
                    f"<Content>{DOI}</Content></CharacterStyleRange></ParagraphStyleRange>"
                ).encode()
                data = data.replace(b"</Story>", paragraph + b"</Story>")
            target.writestr(name, data)
    return output.getvalue()


def record():
    return {
        "code": PID,
        "collection": "scl",
        "doi": DOI,
        "article": {
            "code": PID,
            "v880": [{"_": PID}],
            "v237": [{"_": DOI}],
            "v223": [{"_": "20240707"}],
            "v112": [{"_": "20240102"}],
            "v114": [{"_": "20240304"}],
            "v65": [{"_": "20240000"}],
        },
    }


def build(*, article=None, data=None, response=None, collected=None):
    data = data or source()
    article = (
        article or DeterministicPipeline().run(data, logical_name="ESA_2024001_AOP.idml").canonical
    )
    return build_articlemeta_date_catalog(
        article=article,
        source_idml_sha256=hashlib.sha256(data).hexdigest(),
        response=json.dumps(record() if response is None else response).encode(),
        pid=PID,
        collected_at=collected or (datetime.now(UTC) - timedelta(minutes=2)).isoformat(),
        corpus_id="synthetic-dates",
    )


def test_complete_pipeline_dates_use_authority_without_scientific_changes():
    data = source()
    original = DeterministicPipeline().run(data, logical_name="ESA_2024001_AOP.idml")
    catalog = build(data=data, article=original.canonical)
    actual = DeterministicPipeline(articlemeta_date_catalog=catalog).run(
        data, logical_name="ESA_2024001_AOP.idml"
    )
    repeated = DeterministicPipeline(articlemeta_date_catalog=catalog).run(
        data, logical_name="ESA_2024001_AOP.idml"
    )
    assert actual.xml == repeated.xml and actual.validation.valid
    assert actual.canonical.front.publication_date.value == "2024-07-07"
    assert [(h.date_type, h.date.value) for h in actual.canonical.front.history_dates] == [
        ("received", "2024-01-02"),
        ("accepted", "2024-03-04"),
    ]
    assert actual.canonical.body == original.canonical.body
    assert actual.canonical.back == original.canonical.back
    assert actual.canonical.front.model_dump(
        exclude={"publication_date", "history_dates"}
    ) == original.canonical.front.model_dump(exclude={"publication_date", "history_dates"})
    for old, new in zip(
        original.canonical.front.history_dates, actual.canonical.front.history_dates, strict=True
    ):
        assert set(old.date.evidence_ids) < set(new.date.evidence_ids)
    assert len(actual.canonical.evidence) == len(original.canonical.evidence) + 3
    assert any(
        r.startswith("articlemeta_dates_pending_human:") for r in actual.canonical.review_reasons
    )
    assert (
        catalog.apply(actual.canonical, source_idml_sha256=hashlib.sha256(data).hexdigest())
        == actual.canonical
    )
    root = etree.fromstring(actual.xml)
    assert root.xpath("front/article-meta/history/date/@date-type") == [
        "received",
        "accepted",
        "pub",
    ]
    assert root.findtext('front/article-meta/pub-date[@date-type="pub"]/day') == "07"
    assert root.findtext('front/article-meta/pub-date[@date-type="collection"]/year') == "2024"


@pytest.mark.parametrize(
    "change",
    [
        "root_pid",
        "inner_pid",
        "v880",
        "doi",
        "collection",
        "inner_doi",
        "missing_date",
        "partial_date",
        "invalid_day",
        "multiple_dates",
        "nonliteral_change",
        "chronology",
        "wrong_type",
        "incomplete_history",
    ],
)
def test_bad_articlemeta_records_are_not_authorities(change):
    response = record()
    inner = response["article"]
    if change == "root_pid":
        response["code"] = PID + "0"
    elif change == "inner_pid":
        inner["code"] = PID + "0"
    elif change == "v880":
        inner["v880"][0]["_"] = PID + "0"
    elif change == "doi":
        response["doi"] = "10.999/other"
    elif change == "inner_doi":
        inner["v237"][0]["_"] = "10.999/other"
    elif change == "collection":
        response["collection"] = "other"
    elif change == "missing_date":
        inner.pop("v223")
    elif change == "partial_date":
        inner["v223"][0]["_"] = "20240000"
    elif change == "invalid_day":
        inner["v223"][0]["_"] = "20240230"
    elif change == "multiple_dates":
        inner["v223"].append({"_": "20240708"})
    elif change == "nonliteral_change":
        inner["v114"][0]["_"] = "20240305"
    elif change == "chronology":
        inner["v223"][0]["_"] = "20240101"
    elif change == "wrong_type":
        inner["v223"][0]["_"] = 20240707
    else:
        inner.pop("v114")
    with pytest.raises(ValueError):
        build(response=response)


def test_processing_or_collection_date_cannot_replace_publication():
    response = record()
    response["article"].pop("v223")
    response.update(publication_date="2024-07-07", processing_date="2024-07-07")
    with pytest.raises(ValueError):
        build(response=response)


@pytest.mark.parametrize(
    "change", ["hash", "profile", "doi", "publication", "history", "manual_date", "partial_apply"]
)
def test_catalog_rejects_scope_changes_and_stale_preconditions(change):
    data = source()
    original = DeterministicPipeline().run(data, logical_name="ESA_2024001_AOP.idml").canonical
    catalog = build(data=data, article=original)
    article = original
    source_hash = hashlib.sha256(data).hexdigest()
    if change == "hash":
        source_hash = "0" * 64
    elif change == "profile":
        article = article.model_copy(update={"journal_profile_id": "other"})
    elif change == "doi":
        article = article.model_copy(
            update={"front": article.front.model_copy(update={"article_identifiers": ()})}
        )
    elif change == "publication":
        article = article.model_copy(
            update={
                "front": article.front.model_copy(
                    update={
                        "publication_date": article.front.publication_date.model_copy(
                            update={"value": "2023"}
                        )
                    }
                )
            }
        )
    elif change in {"history", "manual_date"}:
        h = article.front.history_dates[0]
        update = (
            {"value": "2024-05-01"}
            if change == "history"
            else {"transformation": "human-editorial-decision"}
        )
        h = h.model_copy(update={"date": h.date.model_copy(update=update)})
        article = article.model_copy(
            update={
                "front": article.front.model_copy(
                    update={"history_dates": (h, article.front.history_dates[1])}
                )
            }
        )
    else:
        enriched = catalog.apply(article, source_idml_sha256=source_hash)
        article = article.model_copy(update={"evidence": enriched.evidence})
    with pytest.raises(ValueError):
        catalog.apply(article, source_idml_sha256=source_hash)


def test_catalog_tampering_is_rejected_even_for_valid_dates():
    catalog = build()
    body = catalog.model_dump(mode="json")
    body["publication_date"] = "2024-07-08"
    with pytest.raises(ValueError, match="digest"):
        ArticleMetaDateCatalog.model_validate(body)


@pytest.mark.parametrize(
    "pid", ["../file", "https://other.example/", PID + "&x=1", "S1234-5678202400010000X"]
)
def test_source_url_rejects_noncanonical_identifiers(pid):
    with pytest.raises(ValueError):
        source_url(pid)


@pytest.mark.parametrize("response", [b"", b"x" * (MAX_RESPONSE + 1)], ids=["empty", "oversize"])
def test_snapshot_budget(response):
    article = DeterministicPipeline().run(source(), logical_name="ESA_2024001_AOP.idml").canonical
    with pytest.raises(ValueError, match="budget"):
        build_articlemeta_date_catalog(
            article=article,
            source_idml_sha256="a" * 64,
            response=response,
            pid=PID,
            collected_at=datetime.now(UTC).isoformat(),
            corpus_id="synthetic",
        )


@pytest.fixture
def date_bundle(settings, bundle):  # noqa: F811 - imported pytest fixture
    _, _, old_folder, manifest = bundle
    data = source()
    catalog = build(data=data)
    content = catalog.model_dump_json().encode()
    manifest["source_idml_sha256"] = hashlib.sha256(data).hexdigest()
    manifest["catalogs"] = {"articlemeta_date_catalog": hashlib.sha256(content).hexdigest()}
    from idml_foundation.services.enrichment import bundle_path

    folder = settings.enrichment_root / bundle_path(
        manifest["organization_id"], manifest["resource_id"], manifest["source_idml_sha256"]
    )
    old_folder.rename(folder)
    (folder / "articlemeta_date_catalog.json").write_bytes(content)
    (folder / "manifest.json").write_text(json.dumps(manifest))
    path = settings.enrichment_root / "authorizations" / f"{manifest['authorization_id']}.json"
    grant = json.loads(path.read_text())
    grant["source_idml_sha256"] = manifest["source_idml_sha256"]
    grant["catalogs"] = {
        "articlemeta_date_catalog": {
            "source": "scielo_articlemeta_record",
            "catalog_sha256": hashlib.sha256(content).hexdigest(),
            "evidence_sha256": catalog.response_sha256,
            "collected_at": catalog.collected_at.isoformat(),
        }
    }
    path.write_text(json.dumps(grant))
    return data, catalog, folder, manifest, path


def test_date_bundle_reaches_worker_with_audited_provenance(db, settings, date_bundle):
    data, catalog, _, manifest, _ = date_bundle
    chosen = select(settings, manifest)
    assert set(chosen.catalogs) == {"articlemeta_date_catalog"}
    org = Organization(id=manifest["organization_id"], slug="date-bundle", name="Date bundle")
    db.add(org)
    db.flush()
    resource = Resource(id=manifest["resource_id"], organization_id=org.id, title="Dates")
    db.add(resource)
    db.flush()
    artifact, _ = store_idml_artifact(
        db,
        organization_id=org.id,
        original_name="ESA_2024001_AOP.idml",
        data=data,
        scanner=PolicyOnlyScanner(),
        settings=settings,
    )
    job = Job(
        organization_id=org.id,
        kind="idml.process",
        idempotency_key="dates",
        payload={"resource_id": resource.id, "idml_artifact_id": artifact.id},
    )
    db.add(job)
    db.flush()
    result = _process_idml_job(db, job, settings)
    expected = DeterministicPipeline(articlemeta_date_catalog=catalog).run(
        data, logical_name=artifact.original_name
    )
    assert result["xml_sha256"] == hashlib.sha256(expected.xml).hexdigest()
    assert result["enrichment"]["human_review_required"] is True


@pytest.mark.parametrize("change", ["source", "hash", "timestamp", "stale", "revoked"])
def test_date_catalog_grants_bind_actual_evidence_and_age(settings, date_bundle, change):
    _, _, _, manifest, path = date_bundle
    assert select(settings, manifest).catalogs
    grant = json.loads(path.read_text())
    permission = grant["catalogs"]["articlemeta_date_catalog"]
    if change == "source":
        permission["source"] = "editorial_record"
    elif change == "hash":
        permission["evidence_sha256"] = "0" * 64
    elif change == "timestamp":
        permission["collected_at"] = (datetime.now(UTC) - timedelta(minutes=4)).isoformat()
    elif change == "stale":
        permission["collected_at"] = (datetime.now(UTC) - timedelta(days=8)).isoformat()
    else:
        grant["status"] = "revoked"
    path.write_text(json.dumps(grant))
    with pytest.raises(ValueError, match=r"^enrichment_bundle_invalid$"):
        select(settings, manifest)
