"""Tenant-scoped read model for the web editorial evaluation workspace."""

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException
from lxml import etree
from sqlalchemy import select

from idml_foundation.autocorrection_models import AutomationAttempt, AutomationRevalidation
from idml_foundation.dependencies import Configuration, Database, require_permission
from idml_foundation.domain.canonical import CanonicalArticle
from idml_foundation.domain.common import content_digest
from idml_foundation.models import Artifact, CanonicalHeadEvent, DomainSnapshot, Job
from idml_foundation.pipeline.jats_builder import JatsBuilder
from idml_foundation.pipeline.profile import load_profile
from idml_foundation.rbac import Permission, TenantContext
from idml_foundation.restoration_models import RestoredPackageValidation
from idml_foundation.routers.resources import get_resource
from idml_foundation.services.autocorrection_executor import _verified_attempt
from idml_foundation.services.autocorrection_history import read_revalidation
from idml_foundation.services.canonical_heads import _verified, current_canonical_snapshot
from idml_foundation.services.restored_package_validation import read_restored_validation
from idml_foundation.services.validation_diagnosis import describe_validation
from idml_foundation.services.web_restore import restore_choice

router = APIRouter(prefix="/v1/resources", tags=["editorial-evaluations"])
Reader = Annotated[TenantContext, require_permission(Permission.JOB_READ)]


@router.get("/{resource_id}/edit-revisions")
def revisions(resource_id: str, db: Database, context: Reader) -> dict[str, Any]:
    resource = get_resource(resource_id, db, context)
    org = context.organization_id
    head = current_canonical_snapshot(db, organization_id=org, resource_id=resource_id)
    rows = db.execute(
        select(
            DomainSnapshot.id,
            DomainSnapshot.revision,
            DomainSnapshot.content_sha256,
            DomainSnapshot.source_artifact_id,
        )
        .where(
            DomainSnapshot.organization_id == org,
            DomainSnapshot.resource_id == resource_id,
            DomainSnapshot.model_kind == "canonical",
        )
        .order_by(DomainSnapshot.revision.desc())
    ).all()
    choice = restore_choice(db, org, resource_id) if context.allows(Permission.JOB_CREATE) else None
    return dict(
        restore_action=choice[0] if choice else None,
        review_version=resource.version,
        current=head.id if head else None,
        can_start=context.allows(Permission.JOB_CREATE),
        revisions=[
            dict(
                id=r.id,
                revision=r.revision,
                sha256=r.content_sha256,
                source_artifact_id=r.source_artifact_id,
            )
            for r in rows
        ],
    )


def _formal(record: AutomationRevalidation | RestoredPackageValidation) -> dict[str, Any]:
    f = record.reports["formal"]
    diagnosis = describe_validation(
        dict(
            package_sha256=f["package_sha256"],
            formal_validation=f,
            validation=record.reports["offline"],
        )
    )
    return dict(
        id=record.id,
        time=record.created_at,
        xml_sha256=f["xml_sha256"],
        package_sha256=f["package_sha256"],
        items=diagnosis["items"],
        xml_id=record.xml_artifact_id,
        zip_id=record.package_artifact_id,
    )


def _affiliation_diff(
    snapshot: DomainSnapshot, attempt: AutomationAttempt, settings: Configuration
) -> list[dict[str, str]]:
    ops = attempt.receipt["operations"]
    if not attempt.xml_content or not ops:
        return []
    article = CanonicalArticle.model_validate(snapshot.payload)
    before = JatsBuilder(sps_version=load_profile(settings.journal_profile_path).sps_version).build(
        article
    )
    roots = [
        etree.fromstring(data, etree.XMLParser(resolve_entities=False, no_network=True))
        for data in (before, attempt.xml_content.encode())
    ]
    rows = []
    for op in ops:
        if op["operation"] not in {"affiliation-original-literal", "country-code-exact"}:
            continue
        index = next(
            i for i, a in enumerate(article.front.affiliations) if a.id == op["subject_id"]
        )
        fragments = [
            etree.tostring(
                root.findall("front/article-meta/aff")[index], encoding="unicode", with_tail=False
            )
            for root in roots
        ]
        rows.append(dict(operation=op["operation"], before=fragments[0], after=fragments[1]))
    return rows


@router.get("/{resource_id}/edit-revisions/{snapshot_id}")
def evaluation(
    resource_id: str, snapshot_id: str, db: Database, settings: Configuration, context: Reader
) -> dict[str, Any]:
    get_resource(resource_id, db, context)
    org = context.organization_id
    snapshot = db.scalar(
        select(DomainSnapshot).where(
            DomainSnapshot.id == snapshot_id,
            DomainSnapshot.resource_id == resource_id,
            DomainSnapshot.organization_id == org,
            DomainSnapshot.model_kind == "canonical",
        )
    )
    if snapshot is None:
        raise HTTPException(404, "Revisão não encontrada")
    if content_digest(snapshot.payload) != snapshot.content_sha256:
        raise HTTPException(409, "Integridade da revisão não confirmada")
    jobs = db.scalars(
        select(Job)
        .where(
            Job.organization_id == org,
            Job.kind.in_(
                ("autocorrection.evaluate", "autocorrection.preflight", "autocorrection.authorize")
            ),
            Job.payload["resource_id"].as_string() == resource_id,
            Job.payload["canonical_snapshot_id"].as_string() == snapshot_id,
        )
        .order_by(Job.created_at.desc())
        .limit(20)
    ).all()
    attempts = db.scalars(
        select(AutomationAttempt)
        .where(
            AutomationAttempt.organization_id == org,
            AutomationAttempt.resource_id == resource_id,
            AutomationAttempt.base_snapshot_id == snapshot_id,
        )
        .order_by(AutomationAttempt.created_at.desc())
        .limit(10)
    ).all()
    events = db.scalars(
        select(CanonicalHeadEvent)
        .where(
            CanonicalHeadEvent.organization_id == org,
            CanonicalHeadEvent.resource_id == resource_id,
            (CanonicalHeadEvent.snapshot_id == snapshot_id)
            | (CanonicalHeadEvent.previous_snapshot_id == snapshot_id),
        )
        .order_by(CanonicalHeadEvent.sequence.desc())
        .limit(30)
    ).all()
    try:
        transitions = [
            dict(
                sequence=e.sequence,
                action=_verified(e).receipt["action"],
                to=e.snapshot_id,
                previous=e.previous_snapshot_id,
                pending_review=e.receipt.get("draft_admission", {}).get("pending_review", []),
            )
            for e in events
        ]
        candidates = []
        for a in attempts:
            _verified_attempt(a)
            ids = db.scalars(
                select(AutomationRevalidation.id)
                .where(
                    AutomationRevalidation.organization_id == org,
                    AutomationRevalidation.resource_id == resource_id,
                    AutomationRevalidation.attempt_id == a.id,
                )
                .order_by(AutomationRevalidation.created_at.desc())
                .limit(5)
            )
            candidates.append(
                dict(
                    state=a.receipt["state"],
                    xml_sha256=a.receipt["xml_sha256"],
                    diff=_affiliation_diff(snapshot, a, settings),
                    validations=[
                        _formal(
                            read_revalidation(
                                db, organization_id=org, record_id=i, settings=settings
                            )
                        )
                        for i in ids
                    ],
                )
            )
        restored_ids = db.scalars(
            select(RestoredPackageValidation.id)
            .where(
                RestoredPackageValidation.organization_id == org,
                RestoredPackageValidation.resource_id == resource_id,
                RestoredPackageValidation.snapshot_id == snapshot_id,
            )
            .order_by(RestoredPackageValidation.created_at.desc())
            .limit(10)
        )
        restores = []
        for i in restored_ids:
            record = read_restored_validation(
                db, organization_id=org, record_id=i, settings=settings
            )
            restores.append(
                dict(
                    _formal(record),
                    state=record.receipt["state"],
                    pending_review=record.receipt["draft_admission"]["pending_review"],
                )
            )
    except (ValueError, LookupError, KeyError, IndexError, StopIteration):
        raise HTTPException(409, "Integridade do histórico não confirmada") from None
    return dict(
        jobs=[
            dict(
                id=j.id,
                state=j.state,
                result=(j.result or {}).get("state"),
                reason=(j.result or {}).get("reason") or j.error_code,
                provider_calls=(j.result or {}).get("provider_calls"),
                cost_microusd=((j.result or {}).get("review") or {}).get("cost_microusd"),
            )
            for j in jobs
        ],
        candidates=candidates,
        transitions=transitions,
        restorations=restores,
    )


@router.get("/{resource_id}/input-workspace")
def input_workspace(
    resource_id: str, db: Database, context: Reader, snapshot_id: str | None = None
) -> dict[str, Any]:
    """Resolve package inputs from this tenant and the exact canonical revision."""
    workspace = revisions(resource_id, db, context)
    selected = snapshot_id or workspace["current"]
    revision = next((r for r in workspace["revisions"] if r["id"] == selected), None)
    if snapshot_id and revision is None:
        raise HTTPException(404, "Revisão não encontrada")
    org = context.organization_id
    source = revision["source_artifact_id"] if revision else None
    package = None
    if source:
        package = db.execute(
            select(Job.id, Job.payload, Job.result["package_artifact_id"].as_string())
            .where(
                Job.organization_id == org,
                Job.kind == "scielo.package",
                Job.state == "succeeded",
                Job.payload["resource_id"].as_string() == resource_id,
                Job.payload["canonical_snapshot_id"].as_string() == selected,
                Job.payload["idml_artifact_id"].as_string() == source,
            )
            .order_by(Job.created_at.desc(), Job.id.desc())
            .limit(1)
        ).first()
    pdf = package.payload.get("pdf_artifact_id") if package else None
    images = package.payload.get("asset_artifact_ids", []) if package else []
    files = select(Artifact.id, Artifact.original_name, Artifact.media_type, Artifact.sha256).where(
        Artifact.organization_id == org,
        Artifact.media_type.in_(
            (
                "application/vnd.adobe.indesign-idml-package",
                "application/pdf",
                "image/png",
                "image/jpeg",
            )
        ),
        Artifact.scanner_status == "clamav_clean",
    )
    if not workspace["can_start"]:
        files = files.where(Artifact.id.in_([i for i in [source, pdf, *images] if i]))
    choices = db.execute(files.order_by(Artifact.original_name, Artifact.sha256)).mappings().all()
    return dict(
        **workspace,
        selected=selected,
        files=[dict(row) for row in choices],
        pdf=pdf,
        images=images,
        package_job=package.id if package else None,
        package_artifact=package[2] if package else None,
    )
