import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from functools import cache
from io import BytesIO
from uuid import uuid4
from zipfile import ZipFile

import pytest
from lxml import etree

from idml_foundation.ai.security import payload_digest
from idml_foundation.pipeline.service import DeterministicPipeline
from idml_foundation.release.reference_types import (
    RULES,
    ReferenceTypeCatalog,
    build_reference_type_catalog,
    sha,
)
from tests.test_enrichment_bundles import bundle, select  # noqa: F401 - fixture
from tests.test_reference_boundaries import reference_idml

CITATION = (
    "DOE, Ana. Example title. Example Institute, 2020. "
    "Available at: https://example.org/old. Accessed on: May 5, 2020."
)
DOCUMENT = b"synthetic reviewed institutional record"
RULE = "synthetic-reference"


@cache
def source():
    output = BytesIO()
    with ZipFile(BytesIO(reference_idml(CITATION))) as archive, ZipFile(output, "w") as target:
        for name in archive.namelist():
            data = archive.read(name)
            if name == "Stories/Story_u1.xml":
                paragraph = (
                    b'<ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/0.1.doi">'
                    b'<CharacterStyleRange AppliedCharacterStyle="CharacterStyle/none">'
                    b"<Content>10.1234/synthetic</Content></CharacterStyleRange>"
                    b"</ParagraphStyleRange>"
                )
                data = data.replace(b"</Story>", paragraph + b"</Story>")
            target.writestr(name, data)
    return output.getvalue()


def original():
    return DeterministicPipeline().run(source(), logical_name="ESA_2024001_AOP.idml")


@pytest.fixture(autouse=True)
def synthetic_rule(monkeypatch):
    rule = replace(
        RULES["saae-mananciais"],
        citation_sha256=sha(CITATION.encode()),
        source_sha256=sha(DOCUMENT),
        quote="synthetic record",
    )
    monkeypatch.setitem(RULES, RULE, rule)
    return rule


def build(article=None, **overrides):
    article = article or original().canonical
    args = dict(
        article=article,
        source_idml_sha256=sha(source()),
        corpus_id="synthetic",
        selections={article.back.references[0].id: RULE},
        responses={RULE: DOCUMENT},
        collected_at=(datetime.now(UTC) - timedelta(minutes=2)).isoformat(),
    )
    args.update(overrides)
    return build_reference_type_catalog(**args)


@pytest.mark.parametrize("kind", ["webpage", "report"])
@pytest.mark.parametrize("locator_review", [False, True])
def test_pipeline_preserves_literal_fields_and_only_reassigns_roles(
    monkeypatch, synthetic_rule, kind, locator_review
):
    monkeypatch.setitem(
        RULES,
        RULE,
        replace(synthetic_rule, publication_type=kind, locator_review_required=locator_review),
    )
    before = original()
    catalog = build()
    pipeline = DeterministicPipeline(reference_type_catalog=catalog)
    actual = pipeline.run(source(), logical_name="ESA_2024001_AOP.idml")
    assert actual.xml == pipeline.run(source(), logical_name="ESA_2024001_AOP.idml").xml
    assert actual.validation.valid
    assert actual.canonical.front == before.canonical.front
    assert actual.canonical.body == before.canonical.body
    ref, old = actual.canonical.back.references[0], before.canonical.back.references[0]
    changed = {
        "title",
        "source",
        "publisher_name",
        "publication_type",
        "evidence_ids",
        "review_reasons",
    }
    assert ref.model_dump(exclude=changed) == old.model_dump(exclude=changed)
    assert ref.title is None
    assert ref.source == old.title
    assert ref.publisher_name == old.source
    assert ref.publication_type == kind
    assert ref.mixed_citation.plain.value == CITATION
    assert f"reference_type_unresolved:{ref.id}" not in actual.canonical.review_reasons
    assert any(
        r.startswith("verified_reference_type_pending_human:")
        for r in actual.canonical.review_reasons
    )
    assert bool(ref.review_reasons) == locator_review
    assert catalog.apply(actual.canonical, source_idml_sha256=sha(source())) == actual.canonical
    trees = [etree.fromstring(r.xml) for r in (before, actual)]
    left, right = [t.find(".//element-citation") for t in trees]
    assert right.get("publication-type") == kind
    assert right.findtext("source") == "Example title"
    assert right.findtext("publisher-name") == "Example Institute"
    assert right.findtext("year") == "2020"
    right.getparent().replace(right, left)
    # The source tree lost its element during replacement; parse it afresh.
    assert etree.tostring(trees[1], method="c14n") == etree.tostring(
        etree.fromstring(before.xml), method="c14n"
    )


@pytest.mark.parametrize("change", ["document", "empty", "oversize", "rule", "id", "date"])
def test_builder_rejects_unverified_sources(change):
    kwargs = {
        "document": {"responses": {RULE: DOCUMENT + b"edited"}},
        "empty": {"responses": {}},
        "oversize": {"responses": {RULE: b"x" * (8 * 1024**2 + 1)}},
        "rule": {"selections": {original().canonical.back.references[0].id: "missing"}},
        "id": {"selections": {"missing": RULE}},
        "date": {"collected_at": "2026-10-13"},
    }
    with pytest.raises(ValueError):
        build(**kwargs[change])


@pytest.mark.parametrize(
    "change", ["digest", "rule", "snapshot", "review", "evidence", "duplicate"]
)
def test_catalog_rejects_tampering_with_recomputed_hash(change):
    body = build().model_dump(mode="json", exclude={"catalog_id"})
    if change in {"rule", "snapshot"}:
        body["entries"][0]["rule_id" if change == "rule" else "response_sha256"] = (
            "missing" if change == "rule" else "0" * 64
        )
    elif change == "review":
        body["human_review_required"] = False
    elif change == "evidence":
        body["evidence_sha256"] = "0" * 64
    elif change == "duplicate":
        body["entries"].append(body["entries"][0])
    digest = "0" * 64 if change == "digest" else payload_digest(body)
    with pytest.raises(ValueError):
        ReferenceTypeCatalog.model_validate({**body, "catalog_id": digest})


@pytest.mark.parametrize(
    "change",
    [
        "source",
        "doi",
        "profile",
        "missing",
        "citation",
        "title",
        "publisher",
        "type",
        "reason",
        "partial",
        "pending",
        "locator",
        "evidence",
        "applied_title",
        "duplicate",
    ],
)
def test_binding_rejects_changes_and_partial_application(change):
    article = original().canonical
    catalog = build(article)
    digest = sha(source())
    if change in {"partial", "pending", "locator", "evidence", "applied_title"}:
        article = catalog.apply(article, source_idml_sha256=digest)
    ref = article.back.references[0]
    if change == "source":
        digest = "0" * 64
    elif change == "doi":
        article = article.model_copy(
            update={"front": article.front.model_copy(update={"article_identifiers": ()})}
        )
    elif change == "profile":
        article = article.model_copy(update={"journal_profile_id": "other"})
    elif change in {"reason", "pending", "locator"}:
        prefix = {
            "reason": "reference_type_unresolved:",
            "pending": "verified_reference_type_pending_human:",
            "locator": "reference_source_locator_review:",
        }[change]
        article = article.model_copy(
            update={
                "review_reasons": tuple(
                    r for r in article.review_reasons if not r.startswith(prefix)
                )
            }
        )
    elif change in {"partial", "evidence"}:
        evidence = list(article.evidence)
        if change == "partial":
            evidence.pop()
        else:
            evidence[-1] = evidence[-1].model_copy(update={"description": "changed"})
        article = article.model_copy(update={"evidence": tuple(evidence)})
    else:
        if change == "citation":
            ref = ref.model_copy(
                update={
                    "mixed_citation": ref.mixed_citation.model_copy(
                        update={
                            "plain": ref.mixed_citation.plain.model_copy(update={"value": "edited"})
                        }
                    )
                }
            )
        elif change in {"title", "applied_title"}:
            field = "source" if change == "applied_title" else "title"
            ref = ref.model_copy(
                update={field: getattr(ref, field).model_copy(update={"value": "changed"})}
            )
        elif change == "publisher":
            ref = ref.model_copy(update={"publisher_name": ref.source})
        elif change == "type":
            ref = ref.model_copy(update={"publication_type": "book"})
        article = article.model_copy(
            update={
                "back": article.back.model_copy(
                    update={
                        "references": ()
                        if change == "missing"
                        else (ref, ref)
                        if change == "duplicate"
                        else (ref,)
                    }
                )
            }
        )
    with pytest.raises(ValueError, match="reference_type_"):
        catalog.apply(article, source_idml_sha256=digest)


@pytest.mark.parametrize("field", ["title", "source"])
@pytest.mark.parametrize("mutation", ["transformation", "state", "value"])
def test_even_a_new_catalog_must_not_overwrite_human_decisions(field, mutation):
    article = original().canonical
    ref = article.back.references[0]
    altered = getattr(ref, field).model_copy(
        update={
            mutation: {
                "transformation": "human-reviewed",
                "state": "needs_review",
                "value": "not in IDML",
            }[mutation]
        }
    )
    ref = ref.model_copy(update={field: altered})
    article = article.model_copy(
        update={"back": article.back.model_copy(update={"references": (ref,)})}
    )
    with pytest.raises(ValueError, match="existing_decision_or_changed_target"):
        build(article)


def test_builder_requires_single_doi():
    article = original().canonical
    article = article.model_copy(
        update={"front": article.front.model_copy(update={"article_identifiers": ()})}
    )
    with pytest.raises(ValueError, match="doi_required"):
        build(article)


def test_migration_adds_no_reference_classification_or_metadata():
    from idml_foundation.domain.schema_migrations import migrate_payload

    old = original().canonical.model_dump(mode="json")
    old["schema_version"] = "1.5.0"
    migrated = migrate_payload("canonical", old)
    assert old["schema_version"] == "1.5.0"
    assert migrated == {**old, "schema_version": "1.7.0"}
    assert migrated["back"]["references"][0]["publication_type"] == "other"


def test_multiple_entries_are_atomic_on_failure():
    article = original().canonical
    first = article.back.references[0]
    second = first.model_copy(update={"id": "other-reference"})
    article = article.model_copy(
        update={
            "back": article.back.model_copy(update={"references": (first, second)}),
            "review_reasons": (
                *article.review_reasons,
                "reference_type_unresolved:other-reference",
            ),
        }
    )
    catalog = build(article, selections={first.id: RULE, second.id: RULE})
    broken = second.model_copy(update={"publication_type": "journal"})
    target = article.model_copy(
        update={"back": article.back.model_copy(update={"references": (first, broken)})}
    )
    before = payload_digest(target)
    with pytest.raises(ValueError):
        catalog.apply(target, source_idml_sha256=sha(source()))
    assert payload_digest(target) == before
    actual = catalog.apply(article, source_idml_sha256=sha(source()))
    assert all(r.publication_type == "webpage" for r in actual.back.references)
    assert catalog.apply(actual, source_idml_sha256=sha(source())) == actual


@pytest.fixture
def reference_bundle(settings, bundle):  # noqa: F811 - imported fixture
    from idml_foundation.services.enrichment import bundle_path

    _, _, old_folder, manifest = bundle
    data, catalog = source(), build()
    content = catalog.model_dump_json().encode()
    manifest["source_idml_sha256"] = sha(data)
    manifest["catalogs"] = {"reference_type_catalog": sha(content)}
    folder = settings.enrichment_root / bundle_path(
        manifest["organization_id"], manifest["resource_id"], sha(data)
    )
    old_folder.rename(folder)
    (folder / "reference_type_catalog.json").write_bytes(content)
    (folder / "manifest.json").write_text(json.dumps(manifest))
    path = settings.enrichment_root / "authorizations" / f"{manifest['authorization_id']}.json"
    grant = json.loads(path.read_text())
    grant["source_idml_sha256"] = sha(data)
    grant["catalogs"] = {
        "reference_type_catalog": {
            "source": "institutional_bibliographic_records",
            "catalog_sha256": sha(content),
            "evidence_sha256": catalog.evidence_sha256,
            "collected_at": catalog.collected_at.isoformat(),
        }
    }
    path.write_text(json.dumps(grant))
    return data, catalog, folder, manifest, path


def test_reference_catalog_reaches_scoped_worker(db, settings, reference_bundle, monkeypatch):
    import tests.test_enrichment_bundles as harness

    data, _, _, manifest, _ = reference_bundle
    actual = (
        select(settings, manifest).pipeline(settings).run(data, logical_name="ESA_2024001_AOP.idml")
    )
    assert actual.canonical.back.references[0].publication_type == "webpage"
    monkeypatch.setattr(
        harness,
        "DeterministicPipeline",
        lambda **kw: DeterministicPipeline(reference_type_catalog=kw["formula_catalog"]),
    )
    harness.test_worker_uses_bound_catalog_and_records_provenance(
        db, settings, reference_bundle[:4]
    )


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
def test_grants_enforce_scope_authority_and_freshness(settings, reference_bundle, change):
    _, _, _, manifest, path = reference_bundle
    assert select(settings, manifest).catalogs
    grant = json.loads(path.read_text())
    permission = grant["catalogs"]["reference_type_catalog"]
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
    with pytest.raises(ValueError, match=r"^enrichment_bundle_invalid$"):
        select(settings, manifest)


@pytest.mark.parametrize("field", ["organization_id", "resource_id", "source_sha256"])
def test_other_scope_cannot_load_reference_catalog(settings, reference_bundle, field):
    value = "a" * 64 if field == "source_sha256" else str(uuid4())
    result = select(settings, reference_bundle[3], **{field: value})
    assert not result.catalogs
    assert result.provenance["status"] == "no_matching_bundle"


def test_renewed_reference_keeps_the_hash_of_the_read_document(monkeypatch, synthetic_rule):
    revised = b"same reviewed citation on a renewed page"
    monkeypatch.setitem(RULES, RULE, replace(synthetic_rule, renewed_sha256=(sha(revised),)))
    catalog = build(responses={RULE: revised})
    article = catalog.apply(original().canonical, source_idml_sha256=sha(source()))
    assert any(item.locator.artifact_sha256 == sha(revised) for item in article.evidence)
    with pytest.raises(ValueError, match="snapshot_mismatch"):
        build(responses={RULE: revised + b" unreviewed"})
