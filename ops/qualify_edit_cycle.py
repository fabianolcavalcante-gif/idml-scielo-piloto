"""Isolated, synthetic-only VH-10 cycle. No entry point to an application database."""

import argparse
import asyncio
import hashlib
import json
import os
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4
from zipfile import ZipFile

from lxml import etree
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from idml_foundation import source_access_models  # noqa: F401
from idml_foundation.ai.autocorrection_contracts import (
    POLICY_VERSION,
    AutomationContext,
    AutomationScope,
)
from idml_foundation.ai.autocorrection_policy import policy_digest
from idml_foundation.ai.openclaw_client import OpenClawResponsesClient
from idml_foundation.autocorrection_models import (
    AutomationAttempt,
    AutomationGrantRecord,
    AutomationRevalidation,
)
from idml_foundation.domain.canonical import CanonicalArticle
from idml_foundation.ingest.scanner import build_scanner
from idml_foundation.models import (
    Artifact,
    CanonicalHeadEvent,
    DomainSnapshot,
    Job,
    Resource,
    utcnow,
)
from idml_foundation.pipeline.profile import load_profile
from idml_foundation.pipeline.validation import OfflineJatsValidator
from idml_foundation.services.artifacts import read_artifact_bytes, store_supporting_artifact
from idml_foundation.services.autocorrection_authorization import provision_field_grants
from idml_foundation.services.autocorrection_promotion import promote_revalidated_candidate
from idml_foundation.services.autocorrection_sources import ExtractionGrant, resolve_idml_evidence
from idml_foundation.services.canonical_heads import current_canonical_snapshot
from idml_foundation.services.restored_package_validation import restore_and_revalidate_package
from idml_foundation.settings import Settings
from ops.edit_cycle_lab import MODEL, review_candidate
from ops.qualify_edit_preflight import qualify
from tests.test_autocorrection_evidence_pipeline import pipeline_idml


def text_only_fixture():
    # The positive case tests affiliation only. Remove the synthetic illustration
    # from this test input before ingestion; never rewrite a submitted article.
    out = BytesIO()
    with ZipFile(BytesIO(pipeline_idml())) as src, ZipFile(out, "w") as dst:
        for name in src.namelist():
            data = src.read(name)
            if name == "Stories/Story_u4.xml":
                tree = etree.fromstring(data)
                for node in tree.xpath("//Rectangle|//ParagraphStyleRange"):
                    node.getparent().remove(node)
                data = etree.tostring(tree)
            dst.writestr(name, data)
    return out.getvalue()


def config(root):
    return Settings(
        environment="test",
        artifact_root=root / "artifacts",
        artifact_disk_reserve_bytes=1,
        database_url=f"sqlite+pysqlite:///{root / 'qualification.sqlite'}",
        automation_authorization_root=root / "decisions",
        enrichment_location="vps",
        feature_clamav=True,
        clamav_socket=Path("/run/idml-clamav-vh1/scan.sock"),
        journal_profile_path=Path("profiles/esa-aop-1.1.json"),
        validator_registry_path=Path("config/validator-registry-vh1-composed.json"),
    )


def save(path, value):
    tmp = path.with_suffix(".writing")
    tmp.write_text(json.dumps(value, indent=2))
    os.replace(tmp, path)


def prepare(root, scanner):
    settings = config(root)
    baseline = qualify(root, [], settings, scanner, positive_idml=text_only_fixture())
    engine = create_engine(settings.database_url)
    with Session(engine, expire_on_commit=False) as db:
        jobs = db.scalars(select(Job).where(Job.kind == "autocorrection.preflight")).all()
        job = max(
            (j for j in jobs if j.result.get("state") == "staged"),
            key=lambda j: j.result["scope"]["review_version"],
        )
        pdf = store_supporting_artifact(
            db,
            organization_id=job.organization_id,
            original_name="fixture.pdf",
            data=b"%PDF-1.4\nsynthetic cycle evidence\n%%EOF",
            settings=settings,
            scanner=scanner,
        )
        db.commit()
        save(
            root / "case.json",
            dict(job_id=job.id, pdf_id=pdf.id, synthetic=True, baseline=baseline),
        )
    from ops.qualify_source_access_http import authorize

    authorize(
        sessionmaker(engine, expire_on_commit=False),
        settings,
        {"organization_id": job.organization_id, "resource_id": job.payload["resource_id"]},
    )
    engine.dispose()


def material(db, root):
    case = json.loads((root / "case.json").read_bytes())
    reference = case.get("published_reference")
    assert case["synthetic"] is True or (reference and reference["article"] == "esa-e20240086")
    settings = config(root)
    job = db.get(Job, case["job_id"])
    scope = AutomationScope.model_validate(job.result["scope"])
    batch = provision_field_grants(
        db,
        organization_id=job.organization_id,
        scope=scope,
        authorization_id=UUID(job.payload["authorization_id"]),
        profile=load_profile(settings.journal_profile_path),
        settings=settings,
        now=utcnow(),
        require_revision_decision=True,
    )
    attempt = db.get(AutomationAttempt, job.result["attempt_id"])
    snapshot = db.get(DomainSnapshot, str(scope.snapshot_id))
    article = CanonicalArticle.model_validate(snapshot.payload)
    (op,) = batch.intent.operations
    assert op.operation == "affiliation-original-literal"
    if reference:
        assert scope.source_idml_sha256 == reference["source_sha256"]
        assert job.result["xml_sha256"] == reference["expected_candidate_xml_sha256"]
    else:
        assert not article.assets
    records = db.scalars(
        select(AutomationGrantRecord).where(AutomationGrantRecord.base_snapshot_id == snapshot.id)
    ).all()
    (grant,) = [
        g for row in records if (g := ExtractionGrant.model_validate(row.payload)).scope == scope
    ]
    evidence = resolve_idml_evidence(
        article=article,
        operation=op,
        scope=scope,
        grant=grant,
        idml=read_artifact_bytes(db.get(Artifact, snapshot.source_artifact_id), settings),
        assets={},
        settings=settings,
        now=utcnow(),
    )
    xml = attempt.xml_content.encode()
    assert hashlib.sha256(xml).hexdigest() == job.result["xml_sha256"]
    (position,) = [i for i, aff in enumerate(article.front.affiliations) if aff.id == op.subject_id]
    aff = etree.fromstring(xml, etree.XMLParser(resolve_entities=False, no_network=True)).xpath(
        "//article-meta/aff"
    )[position]
    (literal,) = aff.xpath("institution[@content-type='original']/text()")
    if reference:
        assert (
            hashlib.sha256(literal.encode()).hexdigest() == reference["authorized_literal_sha256"]
        )
    original = article.front.affiliations[position].original_text
    assert literal == evidence.source_text and (original is None or not original.value)
    packet = dict(
        xml_sha256=job.result["xml_sha256"],
        operation=op.operation,
        source_literal=evidence.source_text,
        original_field="missing",
        candidate_element="article-meta/aff/institution[@content-type='original']",
        candidate_value=literal,
        evidence_sha256=evidence.source_text_sha256,
    )
    context = AutomationContext(
        scope=scope,
        enabled=True,
        policy_version=POLICY_VERSION,
        policy_sha256=policy_digest(),
        cycle=1,
        started_at=utcnow(),
        consumed_tokens=0,
        consumed_cost_usd=0,
        other_active_executions=0,
        findings=batch.findings,
    )
    return job, packet, batch, context, db.get(Artifact, case["pdf_id"])


def review(root, client):
    receipt_path = root / "votes.json"
    with receipt_path.open("x") as f:
        json.dump(dict(state="started"), f)
    engine = create_engine(config(root).database_url)

    def current():
        with Session(engine) as db:
            job, packet, *_ = material(db, root)
            return job.result, packet

    preflight, evidence = current()

    def valid():
        try:
            return current() == (preflight, evidence)
        except (ValueError, LookupError):
            return False

    try:
        return asyncio.run(
            review_candidate(
                preflight,
                evidence,
                client,
                still_authorized=valid,
                interrupted=lambda: (root / "STOP").exists(),
                checkpoint=lambda r: save(receipt_path, r),
            )
        )
    finally:
        engine.dispose()


def validate(root, *, controlled=False):
    receipt = json.loads((root / "votes.json").read_bytes())
    if receipt["state"] != "supported_for_revalidation":
        return dict(state="no_application", review=receipt["state"])
    settings = config(root)
    engine = create_engine(settings.database_url)
    try:
        with Session(engine) as db:
            job, packet, batch, context, pdf = material(db, root)
            assert receipt["xml_sha256"] == packet["xml_sha256"] and not (root / "STOP").exists()
            if controlled:
                from tests.test_package_formal_validation import completed
                from tests.test_xpm_execution import execution

                executors = dict(executor=completed, xpm_executor=execution)
            else:
                settings.validator_scoped_authorities = True
                settings.validator_socket = Path("/socket/modern.sock")
                settings.xpm_socket = Path("/socket/xpm.sock")
                executors = {}
            args = dict(
                organization_id=job.organization_id,
                pdf_artifact_id=pdf.id,
                pdf_sha256=pdf.sha256,
                profile=load_profile(settings.journal_profile_path),
                settings=settings,
                validator=OfflineJatsValidator(Path("vendor/jats/1.3")),
                **executors,
            )
            result = promote_revalidated_candidate(
                db,
                request_id=uuid4(),
                attempt_id=job.result["attempt_id"],
                intent=batch.intent,
                context=context,
                **args,
            )
            record = db.get(AutomationRevalidation, result["revalidation_id"])
            formal = record.reports["formal"]
            output = dict(
                applied=result["applied_now"],
                controlled=controlled,
                offline_valid=record.reports["offline"]["valid"],
                formal_runs=[
                    dict(name=r["name"], status=r["status"], counts=r.get("counts"))
                    for r in formal["external_runs"]
                ],
                xpm=dict(status=formal["xpm"]["status"], counts=formal["xpm"].get("counts")),
                reasons=result["decision"]["reasons"],
                xml_sha256=formal["xml_sha256"],
                package_sha256=formal["package_sha256"],
            )
            reference = json.loads((root / "case.json").read_bytes()).get("published_reference")
            if reference:
                assert output["xml_sha256"] == reference["package_xml_sha256"]
                assert output["package_sha256"] == reference["package_sha256"]
                output["pending_review"] = result["decision"]["pending_review"]
            org, resource = job.organization_id, str(context.scope.resource_id)
            head = current_canonical_snapshot(db, organization_id=org, resource_id=resource)
            if result["applied_now"]:
                restore = restore_and_revalidate_package(
                    db,
                    resource_id=resource,
                    target_snapshot_id=str(context.scope.snapshot_id),
                    expected_snapshot_id=head.id,
                    expected_resource_version=db.get(Resource, resource).version,
                    request_id=uuid4(),
                    **args,
                )
                output.update(
                    restore_state=restore.receipt["state"],
                    restored_xml_sha256=restore.receipt["scope"]["xml_sha256"],
                    restored_package_sha256=restore.receipt["scope"]["package_sha256"],
                )
                assert (
                    output["restored_xml_sha256"]
                    == json.loads((root / "case.json").read_bytes())["baseline"]["cases"][0][
                        "xml_input_sha256"
                    ]
                )
                assert output["restored_package_sha256"] != output["package_sha256"]
                if reference:
                    assert output["restored_package_sha256"] == reference["masked_package_sha256"]
                    restored = restore.reports["formal"]
                    output["restore_modern"] = [
                        dict(name=r["name"], status=r["status"], counts=r["counts"])
                        for r in restored["external_runs"]
                    ]
                    output["restore_xpm"] = dict(
                        status=restored["xpm"]["status"], counts=restored["xpm"]["counts"]
                    )
                    output["restore_pending_review"] = restore.receipt["draft_admission"][
                        "pending_review"
                    ]
                    output["restore_xpm_derived"] = (
                        restored["xpm"].get("compatibility") or {}
                    ).get("unresolved_counts")
                    output["xpm_derived"] = (formal["xpm"].get("compatibility") or {}).get(
                        "unresolved_counts"
                    )
            head = current_canonical_snapshot(db, organization_id=org, resource_id=resource)
            assert head.id == str(context.scope.snapshot_id) and not result["release_approved"]
            if controlled:
                db.rollback()
            else:
                db.commit()
            return output
    finally:
        engine.dispose()


def recover_reference(root: Path) -> dict:
    """Restore the last admitted head after the intentionally incomplete control."""
    settings = config(root)
    settings.validator_scoped_authorities = True
    settings.validator_socket = Path("/socket/modern.sock")
    settings.xpm_socket = Path("/socket/xpm.sock")
    case = json.loads((root / "case.json").read_bytes())
    reference = case["published_reference"]
    engine = create_engine(settings.database_url)
    try:
        with Session(engine) as db:
            job = db.get(Job, case["job_id"])
            org, resource = job.organization_id, job.payload["resource_id"]
            events = db.scalars(
                select(CanonicalHeadEvent)
                .where(
                    CanonicalHeadEvent.organization_id == org,
                    CanonicalHeadEvent.resource_id == resource,
                )
                .order_by(CanonicalHeadEvent.sequence)
            ).all()
            initial, promoted, undone = events
            assert (
                initial.receipt["action"] == "snapshot"
                and initial.snapshot_id == undone.snapshot_id
            )
            assert (
                promoted.receipt["action"] == "autocorrection-promotion"
                and promoted.receipt["draft_admission"]["eligible"]
            )
            assert (
                undone.receipt["action"] == "restore"
                and undone.previous_snapshot_id == promoted.snapshot_id
            )
            assert undone.snapshot_id == job.payload["canonical_snapshot_id"]
            pdf = db.get(Artifact, case["pdf_id"])
            restored = restore_and_revalidate_package(
                db,
                organization_id=org,
                resource_id=resource,
                target_snapshot_id=promoted.snapshot_id,
                expected_snapshot_id=undone.snapshot_id,
                expected_resource_version=db.get(Resource, resource).version,
                request_id=uuid4(),
                profile=load_profile(settings.journal_profile_path),
                settings=settings,
                validator=OfflineJatsValidator(Path("vendor/jats/1.3")),
                pdf_artifact_id=pdf.id,
                pdf_sha256=pdf.sha256,
            )
            scope = restored.receipt["scope"]
            assert (scope["xml_sha256"], scope["package_sha256"]) == (
                reference["package_xml_sha256"],
                reference["package_sha256"],
            )
            formal = restored.reports["formal"]
            output = dict(
                state=restored.receipt["state"],
                xml_sha256=scope["xml_sha256"],
                package_sha256=scope["package_sha256"],
                modern=[
                    dict(name=r["name"], status=r["status"], counts=r["counts"])
                    for r in formal["external_runs"]
                ],
                xpm=dict(status=formal["xpm"]["status"], counts=formal["xpm"].get("counts")),
                xpm_derived=(formal["xpm"].get("compatibility") or {}).get("unresolved_counts"),
                pending_review=restored.receipt["draft_admission"]["pending_review"],
                approval_inherited=restored.receipt["approval_inherited"],
                release_approved=restored.receipt["release_approved"],
            )
            assert (
                output["state"] == "revalidated-working-draft"
                and not output["approval_inherited"]
                and not output["release_approved"]
            )
            db.commit()
            return output
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action", choices=["prepare", "review", "validate", "controlled", "recover"]
    )
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    if args.action == "prepare":
        prepare(root, build_scanner(config(root)))
    elif args.action == "review":
        client = OpenClawResponsesClient(
            base_url="http://openclaw-idml:47716",
            token=os.environ["IDML_OPENCLAW_GATEWAY_TOKEN"],
            expected_model_key=MODEL,
        )
        print(json.dumps(review(root, client)))
    elif args.action == "recover":
        print(json.dumps(recover_reference(root)))
    else:
        print(json.dumps(validate(root, controlled=args.action == "controlled")))
