import copy
import json
from datetime import UTC, datetime, timedelta
from functools import cache

import pytest
from lxml import etree

from idml_foundation.ai.security import payload_digest
from idml_foundation.domain.canonical import SourcedText
from idml_foundation.pipeline.service import DeterministicPipeline
from idml_foundation.release.articlemeta_orcids import (
    ArticleMetaOrcidCatalog,
    build_articlemeta_orcid_catalog,
    person_url,
    public_name_matches,
    sha,
)
from tests.test_articlemeta_dates import PID, record
from tests.test_articlemeta_dates import source as date_source
from tests.test_enrichment_bundles import bundle, select  # noqa: F401 - pytest fixture

ORCID = "0000-0002-1825-0097"


@cache
def source():
    # Reuse exact ZIP bytes; ZIP member timestamps must not invalidate source binding.
    return date_source()


def inputs():
    article = DeterministicPipeline().run(source(), logical_name="ESA_2024001_AOP.idml").canonical
    response = record()
    response["article"]["v10"] = [{"n": "Ana", "s": "Silva", "k": ORCID}]
    person = {
        "path": f"/{ORCID}/person",
        "name": {
            "visibility": "public",
            "given-names": {"value": "Ana"},
            "family-name": {"value": "Silva"},
            "credit-name": None,
        },
    }
    return article, response, person


def build(article=None, response=None, person=None, collected=None):
    original, default, public = inputs()
    instant = collected or (datetime.now(UTC) - timedelta(minutes=2)).isoformat()
    return build_articlemeta_orcid_catalog(
        article=article or original,
        source_idml_sha256=sha(source()),
        response=json.dumps(response or default).encode(),
        pid=PID,
        collected_at=instant,
        persons={ORCID: (json.dumps(person or public).encode(), instant)},
        corpus_id="synthetic",
    )


def test_pipeline_adds_only_identifier_and_reproducible_evidence():
    data = source()
    before = DeterministicPipeline().run(data, logical_name="ESA_2024001_AOP.idml")
    catalog = build()
    pipeline = DeterministicPipeline(articlemeta_orcid_catalog=catalog)
    actual = pipeline.run(data, logical_name="ESA_2024001_AOP.idml")
    assert actual.xml == pipeline.run(data, logical_name="ESA_2024001_AOP.idml").xml
    assert actual.validation.valid
    assert actual.canonical.body == before.canonical.body
    assert actual.canonical.back == before.canonical.back
    assert actual.canonical.front.model_dump(exclude={"contributors"}) == (
        before.canonical.front.model_dump(exclude={"contributors"})
    )
    old, new = before.canonical.front.contributors[0], actual.canonical.front.contributors[0]
    assert old.model_dump(exclude={"orcid"}) == new.model_dump(exclude={"orcid"})
    assert new.orcid.value == ORCID and len(new.orcid.evidence_ids) == 2
    assert len(actual.canonical.evidence) == len(before.canonical.evidence) + 2
    assert actual.canonical.review_reasons[-1].startswith("articlemeta_orcids_pending_human:")
    assert catalog.apply(actual.canonical, source_idml_sha256=sha(data)) == actual.canonical
    root = etree.fromstring(actual.xml)
    node = root.find('.//contrib-id[@contrib-id-type="orcid"]')
    assert node.text == ORCID and node.get("authenticated") == "false"
    node.getparent().remove(node)
    assert etree.tostring(root, method="c14n") == etree.tostring(
        etree.fromstring(before.xml), method="c14n"
    )


@pytest.mark.parametrize(
    "change",
    [
        "root_pid",
        "inner_pid",
        "v880",
        "doi",
        "collection",
        "missing_author",
        "extra_author",
        "initials",
        "wrong_name",
        "wrong_orcid",
        "wrong_path",
        "private_name",
        "no_name",
        "empty_name",
        "wrong_person",
        "duplicate_author",
        "duplicate_orcid",
        "missing_record",
    ],
)
def test_builder_rejects_unbound_or_ambiguous_records(change):
    article, response, person = inputs()
    author = response["article"]["v10"][0]
    if change == "root_pid":
        response["code"] = "other"
    elif change == "inner_pid":
        response["article"]["code"] = "other"
    elif change == "v880":
        response["article"]["v880"][0]["_"] = "other"
    elif change == "doi":
        response["doi"] = response["article"]["v237"][0]["_"] = "10.1234/wrong"
    elif change == "collection":
        response["collection"] = "other"
    elif change == "missing_author":
        response["article"]["v10"] = []
    elif change == "extra_author":
        response["article"]["v10"].append(copy.deepcopy(author))
    elif change == "initials":
        author["n"] = "A."
    elif change == "wrong_name":
        author["s"] = "Other"
    elif change == "wrong_orcid":
        author["k"] = ORCID[:-1] + "0"
    elif change == "wrong_path":
        person["path"] = "/different/person"
    elif change == "private_name":
        person["name"]["visibility"] = "limited"
    elif change == "no_name":
        person["name"] = None
    elif change == "empty_name":
        person["name"]["given-names"] = person["name"]["family-name"] = None
    elif change == "wrong_person":
        person["name"]["family-name"]["value"] = "Other"
    elif change == "missing_record":
        author["k"] = "0000-0001-5109-3700"
    else:
        clone = article.front.contributors[0].model_copy(update={"id": "duplicate"})
        article = article.model_copy(
            update={
                "front": article.front.model_copy(
                    update={"contributors": (*article.front.contributors, clone)}
                )
            }
        )
        extra = copy.deepcopy(author)
        if change == "duplicate_orcid":
            extra["n"] = "Another"
        response["article"]["v10"].append(extra)
    with pytest.raises(ValueError):
        build(article, response, person)


@pytest.mark.parametrize(
    "change",
    [
        "source",
        "profile",
        "author",
        "existing",
        "explicit_missing",
        "partial",
        "hidden_review",
        "evidence_removed",
    ],
)
def test_apply_never_overwrites_decisions_or_stale_targets(change):
    article, _, _ = inputs()
    catalog = build()
    source_hash = sha(source())
    if change == "source":
        source_hash = "0" * 64
    elif change == "profile":
        article = article.model_copy(update={"journal_profile_id": "other"})
    elif change in {"partial", "hidden_review", "evidence_removed"}:
        article = catalog.apply(article, source_idml_sha256=source_hash)
        if change == "partial":
            article = article.model_copy(update={"evidence": article.evidence[:-1]})
        elif change == "evidence_removed":
            article = article.model_copy(update={"evidence": article.evidence[:-2]})
        else:
            article = article.model_copy(update={"review_reasons": ()})
    else:
        c = article.front.contributors[0]
        changes = (
            {"roles": ("Changed",)}
            if change == "author"
            else {
                "orcid": SourcedText(
                    state="missing" if change == "explicit_missing" else "present",
                    value=None if change == "explicit_missing" else ORCID,
                    transformation="human-decision",
                )
            }
        )
        article = article.model_copy(
            update={
                "front": article.front.model_copy(
                    update={"contributors": (c.model_copy(update=changes),)}
                )
            }
        )
    with pytest.raises(ValueError):
        catalog.apply(article, source_idml_sha256=source_hash)


@pytest.mark.parametrize("kind", ["case", "split", "credit", "full_given", "initials", "accent"])
def test_public_name_comparison_is_exact_without_fuzzy_expansion(kind):
    _, _, person = inputs()
    name = person["name"]
    if kind == "case":
        name["given-names"]["value"] = " ANA "
    elif kind == "split":
        name["given-names"]["value"] = "Ana S"
        name["family-name"]["value"] = "ilva"
    elif kind == "credit":
        name["given-names"]["value"] = "Other"
        name["credit-name"] = {"value": "Ana Silva"}
    elif kind == "full_given":
        name["given-names"]["value"] = "Ana Silva"
        name["family-name"] = None
    elif kind == "initials":
        name["given-names"]["value"] = "A."
    else:
        name["given-names"]["value"] = "Aná"
    assert public_name_matches(json.dumps(person).encode(), ORCID, "Ana Silva") is (
        kind in {"case", "credit", "full_given"}
    )


def test_catalog_digest_and_checksum_are_enforced():
    body = build().model_dump(mode="json")
    body["additions"][0]["contributor_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        ArticleMetaOrcidCatalog.model_validate(body)
    for identifier in ("https://orcid.org/" + ORCID, "../person", ORCID[:-1] + "0"):
        with pytest.raises(ValueError):
            person_url(identifier)


@pytest.fixture
def orcid_bundle(settings, bundle):  # noqa: F811 - imported fixture
    from idml_foundation.services.enrichment import bundle_path

    _, _, old_folder, manifest = bundle
    data, catalog = source(), build()
    content = catalog.model_dump_json().encode()
    manifest["source_idml_sha256"] = sha(data)
    manifest["catalogs"] = {"articlemeta_orcid_catalog": sha(content)}
    folder = settings.enrichment_root / bundle_path(
        manifest["organization_id"], manifest["resource_id"], sha(data)
    )
    old_folder.rename(folder)
    (folder / "articlemeta_orcid_catalog.json").write_bytes(content)
    (folder / "manifest.json").write_text(json.dumps(manifest))
    path = settings.enrichment_root / "authorizations" / f"{manifest['authorization_id']}.json"
    grant = json.loads(path.read_text())
    grant["source_idml_sha256"] = sha(data)
    grant["catalogs"] = {
        "articlemeta_orcid_catalog": {
            "source": "scielo_articlemeta_orcid_records",
            "catalog_sha256": sha(content),
            "evidence_sha256": catalog.evidence_sha256,
            "collected_at": catalog.collected_at.isoformat(),
        }
    }
    path.write_text(json.dumps(grant))
    return data, catalog, folder, manifest, path


def test_orcid_bundle_reaches_scoped_worker(db, settings, orcid_bundle, monkeypatch):
    # Reuse the real worker harness with this catalog instead of its formula fixture.
    original = DeterministicPipeline
    data, catalog, _, manifest, _ = orcid_bundle
    assert (
        select(settings, manifest)
        .pipeline(settings)
        .run(data, logical_name="ESA_2024001_AOP.idml")
        .canonical.front.contributors[0]
        .orcid.value
        == catalog.additions[0].identifier
    )
    import tests.test_enrichment_bundles as worker_harness
    from tests.test_enrichment_bundles import test_worker_uses_bound_catalog_and_records_provenance

    monkeypatch.setattr(
        worker_harness,
        "DeterministicPipeline",
        lambda **kw: original(articlemeta_orcid_catalog=kw["formula_catalog"]),
    )
    test_worker_uses_bound_catalog_and_records_provenance(db, settings, orcid_bundle[:4])


@pytest.mark.parametrize(
    "change", ["source", "hash", "timestamp", "stale", "revoked", "future_person"]
)
def test_grant_requires_both_evidence_sources_current_and_authorized(
    settings, orcid_bundle, change
):
    _, catalog, folder, manifest, path = orcid_bundle
    assert select(settings, manifest).catalogs
    grant = json.loads(path.read_text())
    permission = grant["catalogs"]["articlemeta_orcid_catalog"]
    if change == "source":
        permission["source"] = "scielo_articlemeta_record"
    elif change == "hash":
        permission["evidence_sha256"] = "0" * 64
    elif change == "timestamp":
        permission["collected_at"] = (datetime.now(UTC) - timedelta(minutes=3)).isoformat()
    elif change == "stale":
        permission["collected_at"] = (datetime.now(UTC) - timedelta(days=8)).isoformat()
    elif change == "revoked":
        grant["status"] = "revoked"
    else:
        body = catalog.model_dump(mode="json", exclude={"catalog_id"})
        body["additions"][0]["person"]["collected_at"] = (
            (datetime.now(UTC) + timedelta(days=1)).isoformat().replace("+00:00", "Z")
        )
        changed = ArticleMetaOrcidCatalog.model_validate(
            {**body, "catalog_id": payload_digest(body)}
        )
        content = changed.model_dump_json().encode()
        (folder / "articlemeta_orcid_catalog.json").write_bytes(content)
        permission["catalog_sha256"] = manifest["catalogs"]["articlemeta_orcid_catalog"] = sha(
            content
        )
        permission["evidence_sha256"] = changed.evidence_sha256
        (folder / "manifest.json").write_text(json.dumps(manifest))
    path.write_text(json.dumps(grant))
    with pytest.raises(ValueError, match=r"^enrichment_bundle_invalid$"):
        select(settings, manifest)
