import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from functools import cache
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from lxml import etree

from idml_foundation.ai.security import payload_digest
from idml_foundation.domain.canonical import SourcedText
from idml_foundation.pipeline.profile import load_profile
from idml_foundation.pipeline.service import DeterministicPipeline
from idml_foundation.release.institution_locations import (
    RULES,
    SOURCES,
    InstitutionLocationCatalog,
    build_institution_location_catalog,
    sha,
    verify_snapshot,
)
from tests.test_articlemeta_orcids import source as base_source
from tests.test_enrichment_bundles import bundle, select  # noqa: F401 - pytest fixture


@cache
def source():
    output = BytesIO()
    with ZipFile(BytesIO(base_source())) as archive, ZipFile(output, "w", ZIP_DEFLATED) as target:
        for name in archive.namelist():
            data = archive.read(name)
            if name == "Stories/Story_u1.xml":
                paragraph = (
                    '<ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/03.4.aff">'
                    '<CharacterStyleRange AppliedCharacterStyle="CharacterStyle/none">'
                    "<Content>1University of Tokyo, Graduate School of Arts and Sciences, "
                    "Department of General Systems Studies \u2013 Tokyo, Japan.</Content>"
                    "</CharacterStyleRange></ParagraphStyleRange>"
                ).encode()
                data = data.replace(b"</Story>", paragraph + b"</Story>")
            target.writestr(name, data)
    return output.getvalue()


def original():
    return DeterministicPipeline(profile=load_profile(Path("profiles/esa-aop-1.1.json"))).run(
        source(), logical_name="ESA_2024001_AOP.idml"
    )


@pytest.fixture
def snapshots(monkeypatch):
    """Synthetic address fragments; no private article/source download in the test suite."""
    instant = (datetime.now(UTC) - timedelta(minutes=2)).isoformat()
    data = {}
    for key, spec in SOURCES.items():
        text = f"Synthetic reviewed fragment {key}"
        monkeypatch.setitem(
            SOURCES,
            key,
            replace(
                spec, xpath="//p", nodes=1, fragment_sha256=sha(text.encode()), document_sha256=None
            ),
        )
        data[key] = (f"<html><p>{text}</p></html>".encode(), spec.url, instant)
    return data


def build(snapshots, article=None, rule="tokyo_gss"):
    article = article or original().canonical
    return build_institution_location_catalog(
        article=article,
        source_idml_sha256=sha(source()),
        corpus_id="synthetic",
        assignments={article.front.affiliations[0].id: rule},
        snapshots={key: snapshots[key] for key in RULES[rule].sources},
    )


def test_pipeline_changes_only_state_with_evidence_and_is_idempotent(snapshots):
    before = original()
    catalog = build(snapshots)
    pipeline = DeterministicPipeline(
        profile=load_profile(Path("profiles/esa-aop-1.1.json")),
        institution_location_catalog=catalog,
    )
    actual = pipeline.run(source(), logical_name="ESA_2024001_AOP.idml")
    assert actual.xml == pipeline.run(source(), logical_name="ESA_2024001_AOP.idml").xml
    assert actual.validation.valid
    assert actual.canonical.body == before.canonical.body
    assert actual.canonical.back == before.canonical.back
    aff = actual.canonical.front.affiliations[0]
    assert aff.model_dump(exclude={"state_or_province"}) == (
        before.canonical.front.affiliations[0].model_dump(exclude={"state_or_province"})
    )
    assert actual.canonical.front.model_dump(exclude={"affiliations"}) == (
        before.canonical.front.model_dump(exclude={"affiliations"})
    )
    assert aff.state_or_province.value == "Tokyo"
    assert len(aff.state_or_province.evidence_ids) == 2
    assert catalog.apply(actual.canonical, source_idml_sha256=sha(source())) == actual.canonical
    root = etree.fromstring(actual.xml)
    state = root.find('.//aff/addr-line/named-content[@content-type="state"]')
    state.getparent().remove(state)
    assert etree.tostring(root, method="c14n") == etree.tostring(
        etree.fromstring(before.xml), method="c14n"
    )


@pytest.mark.parametrize("rule_id", list(RULES))
def test_all_curated_rules_preserve_affiliation_fields(snapshots, rule_id):
    article = original().canonical
    aff = article.front.affiliations[0]
    rule = RULES[rule_id]
    fields = {
        k: aff.institution.model_copy(update={"value": getattr(rule, k)})
        for k in ("institution", "department", "city", "country", "country_code")
    }
    aff = aff.model_copy(update=fields)
    article = article.model_copy(
        update={"front": article.front.model_copy(update={"affiliations": (aff,)})}
    )
    catalog = build(snapshots, article, rule_id)
    result = catalog.apply(article, source_idml_sha256=sha(source()))
    assert result.front.affiliations[0].state_or_province.value == rule.state


@pytest.mark.parametrize("field", ["institution", "department", "city", "country", "country_code"])
def test_near_match_or_different_campus_is_rejected(snapshots, field):
    article = original().canonical
    aff = article.front.affiliations[0]
    aff = aff.model_copy(update={field: getattr(aff, field).model_copy(update={"value": "Other"})})
    article = article.model_copy(
        update={"front": article.front.model_copy(update={"affiliations": (aff,)})}
    )
    with pytest.raises(ValueError, match="affiliation_changed"):
        build(snapshots, article)


@pytest.mark.parametrize(
    "change",
    [
        "source",
        "profile",
        "doi",
        "affiliation",
        "missing",
        "existing",
        "explicit_missing",
        "partial",
        "reason",
    ],
)
def test_scope_decisions_and_partial_application_fail_closed(snapshots, change):
    article = original().canonical
    catalog = build(snapshots)
    source_hash = sha(source())
    if change == "source":
        source_hash = "0" * 64
    elif change == "profile":
        article = article.model_copy(update={"journal_profile_id": "other"})
    elif change == "doi":
        article = article.model_copy(
            update={"front": article.front.model_copy(update={"article_identifiers": ()})}
        )
    elif change in {"partial", "reason"}:
        article = catalog.apply(article, source_idml_sha256=source_hash)
        article = article.model_copy(
            update={"evidence": article.evidence[:-1]}
            if change == "partial"
            else {"review_reasons": ()}
        )
    else:
        aff = article.front.affiliations[0]
        if change == "affiliation":
            aff = aff.model_copy(update={"evidence_ids": ()})
        elif change in {"existing", "explicit_missing"}:
            value = (
                aff.city.model_copy(update={"value": "Kanto"})
                if change == "existing"
                else SourcedText(value=None, state="missing")
            )
            aff = aff.model_copy(update={"state_or_province": value})
        article = article.model_copy(
            update={
                "front": article.front.model_copy(
                    update={"affiliations": () if change == "missing" else (aff,)}
                )
            }
        )
    with pytest.raises(ValueError, match="institution_location_"):
        catalog.apply(article, source_idml_sha256=source_hash)


@pytest.mark.parametrize("change", ["url", "unknown", "empty", "oversize", "fragment", "duplicate"])
def test_snapshots_cannot_supply_arbitrary_locations(snapshots, change):
    raw, url, instant = snapshots["easwari"]
    key = "easwari"
    if change == "url":
        url += "?redirect=evil"
    elif change == "unknown":
        key = "other"
    elif change == "empty":
        raw = b""
    elif change == "oversize":
        raw = b"x" * (4 * 1024**2 + 1)
    elif change == "fragment":
        raw = raw.replace(b"reviewed", b"changed")
    else:
        raw = raw.replace(b"</html>", b"<p>Duplicate campus</p></html>")
    with pytest.raises(ValueError):
        verify_snapshot(key, raw, url, instant)


def test_real_easwari_rule_accepts_only_the_reviewed_table_row():
    raw = (
        b"<table><tr><td>Easwari Engineering College</td><td>Chennai</td>"
        b"<td>Tamil Nadu</td></tr></table>"
    )
    now = datetime.now(UTC).isoformat()
    snapshot = verify_snapshot("easwari", raw, SOURCES["easwari"].url, now)
    assert snapshot.sha256 == sha(raw)
    with pytest.raises(ValueError):
        verify_snapshot(
            "easwari", raw.replace(b"Tamil Nadu", b"Other State"), SOURCES["easwari"].url, now
        )


@pytest.mark.parametrize(
    "change",
    [
        "digest",
        "duplicate",
        "unknown_rule",
        "missing_source",
        "extra_source",
        "unreviewed_fragment",
    ],
)
def test_catalog_contract_cannot_omit_or_replace_sources(snapshots, change):
    body = build(snapshots).model_dump(mode="json", exclude={"catalog_id"})
    if change == "duplicate":
        body["additions"].append(body["additions"][0])
    elif change == "unknown_rule":
        body["additions"][0]["rule_id"] = "other"
    elif change == "missing_source":
        body["snapshots"].pop()
    elif change == "extra_source":
        body["snapshots"].append(body["snapshots"][0])
    elif change == "unreviewed_fragment":
        body["snapshots"][0]["fragment_sha256"] = "0" * 64
    digest = "0" * 64 if change == "digest" else payload_digest(body)
    with pytest.raises(ValueError):
        InstitutionLocationCatalog.model_validate({**body, "catalog_id": digest})


@pytest.fixture
def location_bundle(settings, bundle, snapshots):  # noqa: F811 - imported fixture
    from idml_foundation.services.enrichment import bundle_path

    _, _, old_folder, manifest = bundle
    data, catalog = source(), build(snapshots)
    content = catalog.model_dump_json().encode()
    manifest["source_idml_sha256"] = sha(data)
    manifest["profile_id"] = catalog.journal_profile_id
    settings.journal_profile_path = Path("profiles/esa-aop-1.1.json")
    manifest["catalogs"] = {"institution_location_catalog": sha(content)}
    folder = settings.enrichment_root / bundle_path(
        manifest["organization_id"], manifest["resource_id"], sha(data)
    )
    old_folder.rename(folder)
    (folder / "institution_location_catalog.json").write_bytes(content)
    (folder / "manifest.json").write_text(json.dumps(manifest))
    path = settings.enrichment_root / "authorizations" / f"{manifest['authorization_id']}.json"
    grant = json.loads(path.read_text())
    grant["source_idml_sha256"] = sha(data)
    grant["profile_id"] = catalog.journal_profile_id
    grant["catalogs"] = {
        "institution_location_catalog": {
            "source": "institutional_location_records",
            "catalog_sha256": sha(content),
            "evidence_sha256": catalog.evidence_sha256,
            "collected_at": catalog.collected_at.isoformat(),
        }
    }
    path.write_text(json.dumps(grant))
    return data, catalog, folder, manifest, path


def test_location_bundle_reaches_real_scoped_worker(db, settings, location_bundle, monkeypatch):
    import tests.test_enrichment_bundles as harness

    data, _, _, manifest, _ = location_bundle
    actual = (
        select(settings, manifest).pipeline(settings).run(data, logical_name="ESA_2024001_AOP.idml")
    )
    assert actual.canonical.front.affiliations[0].state_or_province.value == "Tokyo"
    monkeypatch.setattr(
        harness,
        "DeterministicPipeline",
        lambda **kw: DeterministicPipeline(
            institution_location_catalog=kw["formula_catalog"],
            profile=load_profile(Path("profiles/esa-aop-1.1.json")),
        ),
    )
    harness.test_worker_uses_bound_catalog_and_records_provenance(db, settings, location_bundle[:4])


@pytest.mark.parametrize("change", ["source", "hash", "timestamp", "stale", "revoked", "future"])
def test_grant_enforces_all_source_dates_and_hashes(settings, location_bundle, change):
    _, catalog, folder, manifest, path = location_bundle
    assert select(settings, manifest).catalogs
    grant = json.loads(path.read_text())
    permission = grant["catalogs"]["institution_location_catalog"]
    if change == "source":
        permission["source"] = "editorial_record"
    elif change == "hash":
        permission["evidence_sha256"] = "0" * 64
    elif change in {"timestamp", "stale"}:
        permission["collected_at"] = (
            datetime.now(UTC) - (timedelta(days=8) if change == "stale" else timedelta(minutes=3))
        ).isoformat()
    elif change == "revoked":
        grant["status"] = "revoked"
    else:
        body = catalog.model_dump(mode="json", exclude={"catalog_id"})
        body["snapshots"][0]["collected_at"] = (
            (datetime.now(UTC) + timedelta(days=1)).isoformat().replace("+00:00", "Z")
        )
        changed = InstitutionLocationCatalog.model_validate(
            {**body, "catalog_id": payload_digest(body)}
        )
        content = changed.model_dump_json().encode()
        (folder / "institution_location_catalog.json").write_bytes(content)
        permission["catalog_sha256"] = manifest["catalogs"]["institution_location_catalog"] = sha(
            content
        )
        permission["evidence_sha256"] = changed.evidence_sha256
        (folder / "manifest.json").write_text(json.dumps(manifest))
    path.write_text(json.dumps(grant))
    with pytest.raises(ValueError, match=r"^enrichment_bundle_invalid$"):
        select(settings, manifest)


def test_disclosure_binds_whole_document_and_reviewed_fragment(monkeypatch):
    key = "easwari_disclosure"
    document = b"reviewed institution disclosure"
    rule = replace(SOURCES[key], document_sha256=sha(document))
    monkeypatch.setitem(SOURCES, key, rule)
    now = datetime.now(UTC).isoformat()
    result = verify_snapshot(key, document, rule.url, now)
    assert result.fragment_sha256 == rule.fragment_sha256 and result.sha256 == sha(document)
    with pytest.raises(ValueError, match="document_changed"):
        verify_snapshot(key, document + b" changed", rule.url, now)
