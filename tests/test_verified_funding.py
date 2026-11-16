import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from functools import cache
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from lxml import etree

from idml_foundation.ai.security import payload_digest
from idml_foundation.domain.canonical import SourcedText
from idml_foundation.pipeline.service import DeterministicPipeline
from idml_foundation.release.verified_funding import (
    RULES,
    VerifiedFundingCatalog,
    build_verified_funding_catalog,
    sha,
)
from tests.test_articlemeta_orcids import source as base_source
from tests.test_enrichment_bundles import bundle, select  # noqa: F401 - pytest fixture

STATEMENT = "Sponsor Alpha and Sponsor Beta, project One, #AB-123."
DOCUMENT = b"%PDF-synthetic-reviewed-institutional-record"
RULE_ID = "synthetic"


@cache
def source():
    output = BytesIO()
    with ZipFile(BytesIO(base_source())) as archive, ZipFile(output, "w", ZIP_DEFLATED) as target:
        for name in archive.namelist():
            data = archive.read(name)
            if name == "Stories/Story_u1.xml":
                data = data.replace(b"Foundation Alpha, grant 123.", STATEMENT.encode())
            target.writestr(name, data)
    return output.getvalue()


def original():
    return DeterministicPipeline().run(source(), logical_name="ESA_2024001_AOP.idml")


@pytest.fixture(autouse=True)
def synthetic_rule(monkeypatch):
    rule = replace(
        next(iter(RULES.values())),
        agency="Sponsor Beta",
        award_id="AB-123",
        statement_sha256=sha(STATEMENT.encode()),
        source_sha256=sha(DOCUMENT),
        quote="Sponsor Beta awarded AB-123",
    )
    monkeypatch.setitem(RULES, RULE_ID, rule)
    return rule


def build(article=None, **overrides):
    kwargs = dict(
        article=article or original().canonical,
        source_idml_sha256=sha(source()),
        corpus_id="synthetic",
        funding_index=0,
        rule_id=RULE_ID,
        response=DOCUMENT,
        source_url=RULES[RULE_ID].source_url,
        collected_at=(datetime.now(UTC) - timedelta(minutes=2)).isoformat(),
    )
    kwargs.update(overrides)
    return build_verified_funding_catalog(**kwargs)


def test_pipeline_preserves_all_text_and_adds_only_verified_pair():
    before = original()
    catalog = build()
    pipeline = DeterministicPipeline(verified_funding_catalog=catalog)
    actual = pipeline.run(source(), logical_name="ESA_2024001_AOP.idml")
    assert actual.xml == pipeline.run(source(), logical_name="ESA_2024001_AOP.idml").xml
    assert actual.validation.valid
    assert actual.canonical.body == before.canonical.body
    assert actual.canonical.back == before.canonical.back
    assert actual.canonical.front.model_dump(exclude={"funding"}) == (
        before.canonical.front.model_dump(exclude={"funding"})
    )
    funding = actual.canonical.front.funding[0]
    assert funding.agency.value == "Sponsor Beta"
    assert funding.award_id.value == "AB-123"
    assert funding.statement == before.canonical.front.funding[0].statement
    assert len(funding.agency.evidence_ids) == len(funding.statement.evidence_ids) + 1
    assert "funding_structure_requires_authority" not in actual.canonical.review_reasons
    assert actual.canonical.review_reasons[-1].startswith("verified_funding_pending_human:")
    assert catalog.apply(actual.canonical, source_idml_sha256=sha(source())) == actual.canonical
    tree = etree.fromstring(actual.xml)
    assert tree.findtext(".//funding-statement") == STATEMENT
    assert "Sponsor Alpha" in tree.findtext('.//fn[@fn-type="financial-disclosure"]/p')
    award = tree.find(".//award-group")
    assert award.findtext("funding-source") == "Sponsor Beta"
    award.getparent().remove(award)
    assert etree.tostring(tree, method="c14n") == etree.tostring(
        etree.fromstring(before.xml), method="c14n"
    )


@pytest.mark.parametrize(
    "change", ["url", "document", "empty", "oversize", "rule", "index", "date"]
)
def test_builder_rejects_unverified_sources(change):
    updates = {
        "url": {"source_url": "https://example.com/unrelated"},
        "document": {"response": DOCUMENT + b"edited"},
        "empty": {"response": b""},
        "oversize": {"response": b"x" * (4 * 1024**2 + 1)},
        "rule": {"rule_id": "missing"},
        "index": {"funding_index": 1},
        "date": {"collected_at": "2026-10-06"},
    }
    with pytest.raises(ValueError):
        build(**updates[change])


@pytest.mark.parametrize(
    "change",
    [
        "source",
        "doi",
        "profile",
        "missing",
        "statement",
        "evidence",
        "agency",
        "award",
        "decision",
        "reason",
        "partial",
        "human",
    ],
)
def test_binding_never_overwrites_decisions_or_changes_the_source(change):
    article = original().canonical
    catalog = build()
    digest = sha(source())
    if change == "source":
        digest = "0" * 64
    elif change == "doi":
        article = article.model_copy(
            update={"front": article.front.model_copy(update={"article_identifiers": ()})}
        )
    elif change == "profile":
        article = article.model_copy(update={"journal_profile_id": "other"})
    elif change == "reason":
        article = article.model_copy(update={"review_reasons": ()})
    else:
        if change in {"partial", "human"}:
            article = catalog.apply(article, source_idml_sha256=digest)
        f = article.front.funding[0]
        if change in {"agency", "human"}:
            f = f.model_copy(
                update={"agency": f.statement.model_copy(update={"value": "Sponsor Alpha"})}
            )
        elif change == "award":
            f = f.model_copy(update={"award_id": SourcedText(value=None, state="missing")})
        elif change == "decision":
            f = f.model_copy(
                update={"agency": f.agency.model_copy(update={"transformation": "human"})}
            )
        elif change in {"statement", "evidence"}:
            f = f.model_copy(
                update={
                    "statement": f.statement.model_copy(
                        update=(
                            {"value": STATEMENT + " edited"}
                            if change == "statement"
                            else {"evidence_ids": ()}
                        )
                    )
                }
            )
        elif change == "partial":
            article = article.model_copy(update={"evidence": article.evidence[:-1]})
        article = article.model_copy(
            update={
                "front": article.front.model_copy(
                    update={"funding": () if change == "missing" else (f,)}
                )
            }
        )
    with pytest.raises(ValueError, match="verified_funding_"):
        catalog.apply(article, source_idml_sha256=digest)


def test_other_unresolved_funding_keeps_its_review_reason():
    article = original().canonical
    article = article.model_copy(
        update={"front": article.front.model_copy(update={"funding": article.front.funding * 2})}
    )
    catalog = build(article)
    actual = catalog.apply(article, source_idml_sha256=sha(source()))
    assert actual.front.funding[1] == article.front.funding[1]
    assert "funding_structure_requires_authority" in actual.review_reasons


@pytest.mark.parametrize("change", ["digest", "rule", "snapshot", "review"])
def test_catalog_rejects_tampering_even_with_recomputed_digest(change):
    body = build().model_dump(mode="json", exclude={"catalog_id"})
    if change == "rule":
        body["rule_id"] = "missing"
    elif change == "snapshot":
        body["response_sha256"] = "0" * 64
    elif change == "review":
        body["human_review_required"] = False
    digest = "0" * 64 if change == "digest" else payload_digest(body)
    with pytest.raises(ValueError):
        VerifiedFundingCatalog.model_validate({**body, "catalog_id": digest})


def test_builder_requires_article_doi():
    article = original().canonical
    article = article.model_copy(
        update={"front": article.front.model_copy(update={"article_identifiers": ()})}
    )
    with pytest.raises(ValueError, match="doi_required"):
        build(article)


@pytest.fixture
def funding_bundle(settings, bundle):  # noqa: F811 - imported fixture
    from idml_foundation.services.enrichment import bundle_path

    _, _, old_folder, manifest = bundle
    data, catalog = source(), build()
    content = catalog.model_dump_json().encode()
    manifest["source_idml_sha256"] = sha(data)
    manifest["catalogs"] = {"verified_funding_catalog": sha(content)}
    folder = settings.enrichment_root / bundle_path(
        manifest["organization_id"], manifest["resource_id"], sha(data)
    )
    old_folder.rename(folder)
    (folder / "verified_funding_catalog.json").write_bytes(content)
    (folder / "manifest.json").write_text(json.dumps(manifest))
    path = settings.enrichment_root / "authorizations" / f"{manifest['authorization_id']}.json"
    grant = json.loads(path.read_text())
    grant["source_idml_sha256"] = sha(data)
    grant["catalogs"] = {
        "verified_funding_catalog": {
            "source": "institutional_funding_record",
            "catalog_sha256": sha(content),
            "evidence_sha256": catalog.response_sha256,
            "collected_at": catalog.collected_at.isoformat(),
        }
    }
    path.write_text(json.dumps(grant))
    return data, catalog, folder, manifest, path


def test_funding_bundle_reaches_scoped_worker(db, settings, funding_bundle, monkeypatch):
    import tests.test_enrichment_bundles as harness

    data, _, _, manifest, _ = funding_bundle
    actual = (
        select(settings, manifest).pipeline(settings).run(data, logical_name="ESA_2024001_AOP.idml")
    )
    assert actual.canonical.front.funding[0].agency.value == "Sponsor Beta"
    monkeypatch.setattr(
        harness,
        "DeterministicPipeline",
        lambda **kw: DeterministicPipeline(verified_funding_catalog=kw["formula_catalog"]),
    )
    harness.test_worker_uses_bound_catalog_and_records_provenance(db, settings, funding_bundle[:4])


@pytest.mark.parametrize("change", ["source", "hash", "date", "stale", "future", "revoked"])
def test_grants_enforce_source_authority_and_freshness(settings, funding_bundle, change):
    _, _, _, manifest, path = funding_bundle
    assert select(settings, manifest).catalogs
    grant = json.loads(path.read_text())
    permission = grant["catalogs"]["verified_funding_catalog"]
    if change == "source":
        permission["source"] = "authorized_article"
    elif change == "hash":
        permission["evidence_sha256"] = "0" * 64
    elif change == "revoked":
        grant["status"] = "revoked"
    else:
        delta = {
            "date": timedelta(minutes=-3),
            "stale": timedelta(days=-8),
            "future": timedelta(days=1),
        }
        permission["collected_at"] = (datetime.now(UTC) + delta[change]).isoformat()
    path.write_text(json.dumps(grant))
    with pytest.raises(ValueError, match=r"^enrichment_bundle_invalid$"):
        select(settings, manifest)
