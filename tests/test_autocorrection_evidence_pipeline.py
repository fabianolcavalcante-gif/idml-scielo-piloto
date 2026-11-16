import copy
import hashlib
from datetime import timedelta
from io import BytesIO
from uuid import UUID, uuid4
from zipfile import ZipFile

import pytest
from lxml import etree
from sqlalchemy import func, select

from idml_foundation.autocorrection_models import AutomationAttempt, AutomationGrantRecord
from idml_foundation.domain.canonical import CanonicalArticle
from idml_foundation.domain.common import content_digest
from idml_foundation.models import Resource
from idml_foundation.pipeline.autocorrection_evidence import (
    qualify_fields,
    run_evidence_ready_pipeline,
)
from idml_foundation.pipeline.jats_builder import JatsBuilder
from idml_foundation.pipeline.service import DeterministicPipeline
from idml_foundation.services.autocorrection_authorization import (
    AutomationBatchAuthorization,
    load_batch_authorization,
    provision_field_grants,
)
from idml_foundation.services.autocorrection_executor import stage_autocorrection
from idml_foundation.services.autocorrection_sources import SourceResolutionError, source_element
from idml_foundation.services.snapshots import store_snapshot
from tests.autocorrection_helpers import persisted_data, source_data, stage_kwargs
from tests.phase3_helpers import synthetic_idml


def test_preparation_is_idempotent_additive_and_byte_identical_xml(settings):
    data = source_data()
    article = data["article"]
    before = article.model_dump(mode="json")
    result = qualify_fields(article, idml=data["idml"], profile=data["profile"], settings=settings)
    assert len(result.catalog.bindings) == 3 and not result.refused
    assert article.model_dump(mode="json") == before
    assert result.article.evidence[: len(article.evidence)] == article.evidence
    assert JatsBuilder().build(result.article) == JatsBuilder().build(article)
    stripped = result.article.model_dump(mode="json")
    new_ids = {b.evidence_id for b in result.catalog.bindings}

    def remove_evidence(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "evidence_ids":
                    value[key] = [e for e in item if e not in new_ids]
                elif key == "evidence":
                    value[key] = [e for e in item if e["id"] not in new_ids]
                else:
                    remove_evidence(item)
        elif isinstance(value, list):
            for item in value:
                remove_evidence(item)

    remove_evidence(stripped)
    assert stripped == before
    again = qualify_fields(
        result.article, idml=data["idml"], profile=data["profile"], settings=settings
    )
    assert again.article == result.article and again.catalog == result.catalog


@pytest.mark.parametrize(
    "id_value,code",
    [
        ("u1:paragraph:4", "extraction_element_not_unique"),
        ("u1:paragraph:01", "extraction_element_not_unique"),
        ("missing:paragraph:0", "extraction_element_not_unique"),
        (None, "extraction_element_required"),
    ],
)
def test_invalid_virtual_paragraphs_refused(id_value, code):
    root = etree.fromstring(b'<Story Self="u1"><ParagraphStyleRange/></Story>')
    with pytest.raises(SourceResolutionError, match=code):
        source_element(root, id_value)


@pytest.mark.parametrize(
    "xml",
    [
        b'<Root><Story Self="u1"><ParagraphStyleRange/></Story><X Self="u1:paragraph:0"/></Root>',
        b'<Root><Story Self="u1"/><Story Self="u1"/></Root>',
        b'<X Self="u1"><ParagraphStyleRange/></X>',
    ],
)
def test_virtual_selector_collision_is_not_resolved_by_preference(xml):
    with pytest.raises(SourceResolutionError):
        source_element(etree.fromstring(xml), "u1:paragraph:0")


def pipeline_idml():
    source = synthetic_idml()
    output = BytesIO()
    with ZipFile(BytesIO(source)) as src, ZipFile(output, "w") as dest:
        for name in src.namelist():
            data = src.read(name)
            if name == "Stories/Story_u1.xml":
                data = data.replace(
                    b"</Story>",
                    b'<ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/03.4.affiliation">'
                    b"<CharacterStyleRange><Content>Example University</Content>"
                    b"</CharacterStyleRange></ParagraphStyleRange></Story>",
                )
            dest.writestr(name, data)
    return output.getvalue()


def test_real_parser_virtual_locator_is_qualified_in_ingestion(settings):
    data = source_data()
    idml = pipeline_idml()
    pipeline = DeterministicPipeline(profile=data["profile"], settings=settings)
    baseline = pipeline.run(idml, logical_name="ESA_2024001_AOP.idml")
    result, prepared = run_evidence_ready_pipeline(
        pipeline,
        idml=idml,
        logical_name="ESA_2024001_AOP.idml",
        profile=data["profile"],
        settings=settings,
    )
    assert result.xml == baseline.xml and result.validation == baseline.validation
    assert result.raw == baseline.raw
    binding = next(
        b for b in prepared.catalog.bindings if b.operation == "affiliation-original-literal"
    )
    evidence = next(e for e in result.canonical.evidence if e.id == binding.evidence_id)
    assert ":paragraph:" in evidence.locator.element_id
    assert evidence.content_sha256 == hashlib.sha256(b"Example University").hexdigest()


@pytest.mark.parametrize("change", ["profile", "wrong_source", "human", "ambiguous", "existing"])
def test_unqualified_provenance_or_existing_values_never_get_permission(settings, change):
    data = source_data()
    raw = data["article"].model_dump(mode="json")
    if change == "profile":
        profile = data["profile"].model_copy(update={"country_codes": {"Brazil": "XX"}})
        with pytest.raises(ValueError, match="profile_not_qualified"):
            qualify_fields(data["article"], idml=data["idml"], profile=profile, settings=settings)
        return
    if change == "wrong_source":
        for evidence in raw["evidence"]:
            evidence["locator"]["artifact_sha256"] = "f" * 64
    elif change == "human":
        raw["evidence"][1]["source_kind"] = "human"
    elif change == "ambiguous":
        # The same institution in two candidate source selections cannot be voted away.
        extra = copy.deepcopy(raw["evidence"][3])
        extra["id"] = "ambiguous-source"
        extra["locator"]["element_id"] = "story:paragraph:1"
        raw["evidence"].append(extra)
        raw["front"]["affiliations"][0]["evidence_ids"].append(extra["id"])
    else:
        raw["front"]["affiliations"][0]["original_text"] = {
            "state": "present",
            "value": "Existing human value",
            "evidence_ids": ["ev-2"],
        }
    result = qualify_fields(
        CanonicalArticle.model_validate(raw),
        idml=data["idml"],
        profile=data["profile"],
        settings=settings,
    )
    if change == "wrong_source":
        assert not result.catalog.bindings
    elif change in {"human", "ambiguous"}:
        assert all(b.operation == "figure-asset-exact" for b in result.catalog.bindings)
    else:
        assert all(b.operation != "affiliation-original-literal" for b in result.catalog.bindings)


@pytest.mark.parametrize("change", ["partial_institution", "human_figure"])
def test_field_qualifier_protects_exact_institution_and_human_figure(settings, change):
    data = source_data()
    raw = data["article"].model_dump(mode="json")
    if change == "partial_institution":
        raw["front"]["affiliations"][0]["institution"]["value"] = "xample University"
    else:
        raw["evidence"][2]["source_kind"] = "human"
    result = qualify_fields(
        CanonicalArticle.model_validate(raw),
        idml=data["idml"],
        profile=data["profile"],
        settings=settings,
    )
    if change == "partial_institution":
        assert all(b.operation == "figure-asset-exact" for b in result.catalog.bindings)
    else:
        assert all(b.operation != "figure-asset-exact" for b in result.catalog.bindings)


@pytest.fixture
def prepared(db, settings, tmp_path):
    data = persisted_data(db, settings)
    qualified = qualify_fields(
        data["article"], idml=data["idml"], profile=data["profile"], settings=settings
    )
    snapshot, _ = store_snapshot(
        db,
        organization_id=str(data["context"].scope.organization_id),
        resource_id=str(data["context"].scope.resource_id),
        document=qualified.article,
        revision=2,
        source_artifact_id=data["snapshot"].source_artifact_id,
        parent_snapshot_id=data["snapshot"].id,
    )
    scope = data["context"].scope.model_copy(
        update={
            "snapshot_id": UUID(snapshot.id),
            "snapshot_sha256": snapshot.content_sha256,
            "review_version": db.get(Resource, snapshot.resource_id).version,
        }
    )
    data["context"] = data["context"].model_copy(update={"scope": scope})
    data["settings"] = settings.model_copy(
        update={"enrichment_root": tmp_path / "authorities", "enrichment_location": "local"}
    )
    root = data["settings"].enrichment_root / "autocorrection-authorizations"
    root.mkdir(parents=True)
    auth = AutomationBatchAuthorization(
        authorization_id=uuid4(),
        organization_id=scope.organization_id,
        resource_id=scope.resource_id,
        source_idml_sha256=scope.source_idml_sha256,
        canonical_sha256=scope.snapshot_sha256,
        catalog_sha256=content_digest(qualified.catalog),
        destination="local",
        status="active",
        decision_sha256="d" * 64,
        collected_at=data["now"] - timedelta(days=1),
        issued_at=data["now"] - timedelta(hours=1),
        expires_at=data["now"] + timedelta(days=1),
    )
    data["authorization"] = auth
    data["authorization_file"] = root / f"{auth.authorization_id}.json"
    data["authorization_file"].write_text(auth.model_dump_json(), encoding="utf-8")
    db.commit()
    return data


def provision(db, data):
    return provision_field_grants(
        db,
        organization_id=str(data["context"].scope.organization_id),
        scope=data["context"].scope,
        authorization_id=data["authorization"].authorization_id,
        settings=data["settings"],
        profile=data["profile"],
        now=data["now"],
    )


def test_batch_authorizes_three_operations_once_and_executor_reextracts_bytes(db, prepared):
    issued = provision(db, prepared)
    assert len(issued.intent.operations) == 3
    repeated = provision(db, prepared)
    assert issued.intent.operations == repeated.intent.operations
    db.commit()
    rows = list(
        db.scalars(
            select(AutomationGrantRecord).where(
                AutomationGrantRecord.base_snapshot_id == str(prepared["context"].scope.snapshot_id)
            )
        )
    )
    assert len(rows) == 3
    assert {row.payload["parent_authorization_id"] for row in rows} == {
        str(prepared["authorization"].authorization_id)
    }
    kwargs = stage_kwargs(prepared) | {
        "intent": issued.intent,
        "context": prepared["context"].model_copy(update={"findings": issued.findings}),
    }
    attempt = stage_autocorrection(db, **kwargs)
    assert attempt.receipt["state"] == "staged"
    assert not attempt.receipt["release_approved"]


@pytest.mark.parametrize(
    "change",
    ["revoked", "missing", "changed", "expired", "tenant", "catalog", "location", "oversized"],
)
def test_parent_authorization_is_reloaded_at_execution(db, prepared, change):
    issued = provision(db, prepared)
    db.commit()
    auth = prepared["authorization"].model_dump(mode="json")
    if change == "missing":
        prepared["authorization_file"].unlink()
    elif change == "oversized":
        prepared["authorization_file"].write_text("x" * 17000)
    else:
        if change == "revoked":
            auth["status"] = "revoked"
        elif change == "changed":
            auth["decision_sha256"] = "f" * 64
        elif change == "expired":
            prepared["now"] = prepared["authorization"].expires_at
        elif change == "tenant":
            auth["organization_id"] = str(uuid4())
        elif change == "catalog":
            auth["catalog_sha256"] = "f" * 64
        else:
            auth["destination"] = "vps"
        import json

        prepared["authorization_file"].write_text(json.dumps(auth))
    attempt = stage_autocorrection(
        db,
        **(
            stage_kwargs(prepared)
            | {
                "intent": issued.intent,
                "context": prepared["context"].model_copy(update={"findings": issued.findings}),
            }
        ),
    )
    assert attempt.receipt["state"] == "refused" and attempt.candidate is None


def test_no_parent_authorization_means_no_partial_grants(db, prepared):
    prepared["authorization_file"].unlink()
    before = db.scalar(select(func.count()).select_from(AutomationGrantRecord))
    with pytest.raises(SourceResolutionError):
        provision(db, prepared)
    assert db.scalar(select(func.count()).select_from(AutomationGrantRecord)) == before


def test_revocation_during_validation_rolls_back_staging(db, prepared, monkeypatch):
    issued = provision(db, prepared)
    db.commit()
    original = prepared["validator"].validate

    def revoke(xml, **kwargs):
        auth = prepared["authorization"].model_copy(update={"status": "revoked"})
        prepared["authorization_file"].write_text(auth.model_dump_json())
        return original(xml, **kwargs)

    monkeypatch.setattr(prepared["validator"], "validate", revoke)
    with pytest.raises(SourceResolutionError):
        stage_autocorrection(
            db,
            **(
                stage_kwargs(prepared)
                | {
                    "intent": issued.intent,
                    "context": prepared["context"].model_copy(update={"findings": issued.findings}),
                }
            ),
        )
    assert db.scalar(select(func.count()).select_from(AutomationAttempt)) == 0


def test_batch_scope_and_clock_fail_closed(db, prepared):
    auth = prepared["authorization"]
    kwargs = dict(
        authorization_id=auth.authorization_id,
        scope=prepared["context"].scope,
        catalog_sha256=auth.catalog_sha256,
        now=prepared["now"].replace(tzinfo=None),
    )
    with pytest.raises(SourceResolutionError):
        load_batch_authorization(prepared["settings"], **kwargs)
    with pytest.raises(PermissionError):
        provision_field_grants(
            db,
            organization_id=str(uuid4()),
            scope=prepared["context"].scope,
            authorization_id=auth.authorization_id,
            profile=prepared["profile"],
            settings=prepared["settings"],
            now=prepared["now"],
        )
