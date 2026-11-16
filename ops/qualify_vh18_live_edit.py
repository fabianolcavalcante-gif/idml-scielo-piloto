"""Controlled live regression on a separate ESA resource, using its qualified published figures."""

import hashlib
import json
import sys
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5
from zipfile import ZipFile

from lxml import etree
from sqlalchemy import select

from idml_foundation.autocorrection_models import AutomationRevalidation
from idml_foundation.database import SessionLocal
from idml_foundation.domain.canonical import CanonicalArticle, FieldState
from idml_foundation.domain.common import content_digest
from idml_foundation.models import Artifact, DomainSnapshot, Job, Resource, utcnow
from idml_foundation.pipeline.autocorrection_evidence import qualify_fields
from idml_foundation.pipeline.jats_builder import JatsBuilder
from idml_foundation.pipeline.profile import load_profile
from idml_foundation.pipeline.validation import OfflineJatsValidator
from idml_foundation.release.package_builder import AssetPayload, PackageBuilder
from idml_foundation.services.artifacts import read_artifact_bytes
from idml_foundation.services.autocorrection_authorization import RevisionEditAuthorization
from idml_foundation.services.canonical_heads import current_canonical_snapshot
from idml_foundation.services.restored_package_validation import restore_and_revalidate_package
from idml_foundation.services.snapshots import store_snapshot
from idml_foundation.services.web_edit_cycle import WebEditDecision
from idml_foundation.settings import get_settings

ORG = "1e47534c-4bff-4ec3-85fe-ed71f2742050"
SOURCE = "21e01b58-4820-4881-af1f-e05795f2645a"
PACKAGE_JOB = "47f44312-89ca-46b5-b188-a4c0d59cdace"
BASE_HEAD = "d302cc84-b182-4667-9fff-525f789af107"
REFERENCE = "7c0d7052ff7c84d15cb077d2b7cbf736f5045ee167cb7902f2a63d331da4b07f"
TITLE = "ESA · Ensaio de correção e restauração · e20240086"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def head(db, article):
    return current_canonical_snapshot(db, organization_id=ORG, resource_id=article)


def prepare(db, resource, settings, profile, validator):
    original = head(db, SOURCE)
    job = db.get(Job, PACKAGE_JOB)
    assert original.id == BASE_HEAD and job.state == "succeeded" and job.organization_id == ORG
    assert job.payload["resource_id"] == SOURCE and job.result["snapshot_id"] == BASE_HEAD
    assert head(db, resource.id) is None
    article = CanonicalArticle.model_validate(original.payload)
    source = db.get(Artifact, original.source_artifact_id)
    pdf = db.get(Artifact, job.payload["pdf_artifact_id"])
    package = db.get(Artifact, job.result["package_artifact_id"])
    assert source.organization_id == pdf.organization_id == package.organization_id == ORG
    assert pdf.scanner_status == source.scanner_status == "clamav_clean"
    archive = read_artifact_bytes(package, settings)
    assert digest(archive) == REFERENCE
    idml = read_artifact_bytes(source, settings)
    figures = job.result["figure_bindings"]["figures"]
    assert len(figures) == 5
    selected, payloads = {}, []
    with ZipFile(BytesIO(archive)) as z:
        for fig in figures:
            (asset_id,) = fig["canonical_asset_ids"]
            (item,) = [a for a in article.assets if a.id == asset_id]
            artifact = db.get(Artifact, fig["artifact_id"])
            assert artifact.organization_id == ORG and artifact.scanner_status == "clamav_clean"
            data = read_artifact_bytes(artifact, settings)
            assert digest(data) == fig["sha256"] and data == z.read(fig["package_name"])
            assert item.logical_name == fig["xml_href"]
            selected[item.id] = item.model_copy(
                update=dict(sha256=digest(data), state=FieldState.PRESENT)
            )
            payloads.append(
                AssetPayload(
                    source_name=item.logical_name, data=data, media_type=artifact.media_type
                )
            )
        stem = profile.package_stem(article.article_id)
        assert read_artifact_bytes(pdf, settings) == z.read(stem + ".pdf")
        reference_xml = z.read(stem + ".xml")
    working = article.model_copy(
        update=dict(assets=tuple(selected.get(a.id, a) for a in article.assets))
    )

    def build(document):
        files = PackageBuilder().scielo_files(
            package_stem=stem,
            xml=JatsBuilder(sps_version=profile.sps_version).build(document),
            pdf=read_artifact_bytes(pdf, settings),
            assets=tuple(payloads),
        )
        xml = next(f.data for f in files if f.role.value == "xml")
        offline = validator.validate(xml, asset_names={f["package_name"] for f in figures})
        assert offline.valid
        result = PackageBuilder().build(
            article_id=article.article_id,
            profile_id=profile.profile_id,
            source_idml_sha256=source.sha256,
            files=files,
            validator_versions={"offline": offline.validator_profile},
        )
        return xml, result.package_sha256

    xml, qualified_sha = build(working)
    assert xml == reference_xml and qualified_sha == REFERENCE
    raw = working.model_dump(mode="json")
    (target,) = [
        a
        for a in raw["front"]["affiliations"]
        if a["institution"]["value"] == "University of Tokyo"
    ]
    literal = target["original_text"]["value"]
    target["original_text"] = None
    qualified = qualify_fields(
        CanonicalArticle.model_validate(raw), idml=idml, profile=profile, settings=settings
    )
    (binding,) = qualified.catalog.bindings
    assert (
        binding.operation == "affiliation-original-literal" and binding.subject_id == target["id"]
    )
    incomplete, masked_sha = build(qualified.article)
    parser = etree.XMLParser(resolve_entities=False, no_network=True, remove_blank_text=True)
    tree = etree.fromstring(reference_xml, parser)
    (node,) = [
        n
        for n in tree.findall("front/article-meta/aff/institution[@content-type='original']")
        if n.text == literal
    ]
    # The ESA hierarchy rule uses the literal to split these two recorded subdivisions.
    # Verify the exact fallback representation when that evidence is absent.
    affiliation = node.getparent()
    (division,) = affiliation.findall("institution[@content-type='orgdiv1']")
    (department,) = affiliation.findall("institution[@content-type='orgdiv2']")
    assert division.text == "Graduate School of Arts and Sciences"
    assert department.text == "Department of General Systems Studies"
    division.text += ", " + department.text
    affiliation.remove(department)
    affiliation.remove(node)
    assert etree.tostring(tree, method="c14n") == etree.tostring(
        etree.fromstring(incomplete, parser), method="c14n"
    )
    snap, created = store_snapshot(
        db,
        organization_id=ORG,
        resource_id=resource.id,
        source_artifact_id=source.id,
        revision=1,
        document=qualified.article,
    )
    assert created
    now = utcnow()
    decision = RevisionEditAuthorization(
        authorization_id=uuid5(NAMESPACE_URL, "vh18-edit:" + snap.id),
        organization_id=ORG,
        resource_id=resource.id,
        snapshot_id=snap.id,
        review_version=resource.version,
        source_idml_sha256=source.sha256,
        canonical_sha256=snap.content_sha256,
        catalog_sha256=content_digest(qualified.catalog),
        decision_sha256=content_digest(
            dict(resource=resource.id, snapshot=snap.id, field=target["id"], reference=REFERENCE)
        ),
        destination="vps",
        status="active",
        collected_at=now,
        issued_at=now,
        expires_at=now + timedelta(hours=2),
    )
    scope = dict(
        resource_id=resource.id, canonical_snapshot_id=snap.id, review_version=resource.version
    )
    permit = WebEditDecision(
        purpose="review-and-promote-affiliation-v1",
        model="openai/gpt-5.4-mini",
        scope=scope,
        organization_id=ORG,
        authorization_id=decision.authorization_id,
        allowed_literal_sha256=digest(literal.encode()),
        pdf_artifact_id=pdf.id,
        pdf_sha256=pdf.sha256,
    )
    return dict(
        resource=resource.id,
        snapshot=snap.id,
        version=resource.version,
        decision=decision.model_dump(mode="json"),
        permit=permit.model_dump(mode="json"),
        pdf=pdf.id,
        reference_xml=digest(xml),
        reference_zip=REFERENCE,
        masked_xml=digest(incomplete),
        masked_zip=masked_sha,
        one_literal_difference=True,
        hierarchy_fallback_verified=True,
        figures=5,
    )


def revalidate(db, resource, job_id, action, settings, profile, validator):
    job = db.get(Job, job_id)
    assert job.organization_id == ORG and job.kind == "autocorrection.evaluate"
    assert (
        job.payload["resource_id"] == resource.id
        and job.state == "succeeded"
        and job.result["state"] == "applied"
    )
    record = db.get(AutomationRevalidation, job.result["revalidation_id"])
    assert record.resource_id == resource.id and record.organization_id == ORG
    applied = db.scalars(
        select(DomainSnapshot).where(
            DomainSnapshot.resource_id == resource.id,
            DomainSnapshot.revision == 2,
            DomainSnapshot.model_kind == "canonical",
        )
    ).one()
    masked = job.payload["canonical_snapshot_id"]
    before, target = (applied.id, masked) if action == "undo" else (masked, applied.id)
    pdf = db.get(Artifact, db.get(Job, PACKAGE_JOB).payload["pdf_artifact_id"])
    assert head(db, SOURCE).id == BASE_HEAD and head(db, resource.id).id == before
    result = restore_and_revalidate_package(
        db,
        organization_id=ORG,
        resource_id=resource.id,
        target_snapshot_id=target,
        expected_snapshot_id=before,
        expected_resource_version=resource.version,
        request_id=uuid5(NAMESPACE_URL, job.id + ":" + action),
        pdf_artifact_id=pdf.id,
        pdf_sha256=pdf.sha256,
        profile=profile,
        settings=settings,
        validator=validator,
    )
    assert result.receipt["state"] == (
        "blocked" if action == "undo" else "revalidated-working-draft"
    )
    assert head(db, resource.id).id == target and head(db, SOURCE).id == BASE_HEAD
    return dict(
        state=result.receipt["state"],
        revision=target,
        formal=result.reports["formal"],
        offline=result.reports["offline"],
        xml=result.xml_artifact_id,
        zip=result.package_artifact_id,
        id=result.id,
    )


if __name__ == "__main__":
    settings = get_settings()
    profile = load_profile(settings.journal_profile_path)
    validator = OfflineJatsValidator(Path("/app/vendor/jats/1.3"))
    action, resource_id = sys.argv[1:3]
    with SessionLocal.begin() as db:
        resource = db.get(Resource, str(UUID(resource_id)))
        assert resource.organization_id == ORG and resource.title == TITLE and resource.id != SOURCE
        if action == "prepare":
            result = prepare(db, resource, settings, profile, validator)
        elif action in {"undo", "recover"}:
            result = revalidate(
                db, resource, str(UUID(sys.argv[3])), action, settings, profile, validator
            )
        else:
            raise ValueError("unknown qualification action")
    print(json.dumps(result))
