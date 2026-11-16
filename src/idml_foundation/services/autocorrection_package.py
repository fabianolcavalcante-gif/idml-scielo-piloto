"""Private package revalidation, not promotion, publication or editorial acceptance.

Only the intent is agent input. Context, clock, PDF selection, profile and validators
are trusted server dependencies. No route or worker is activated by this module.
The caller owns the transaction and persistence of returned private evidence.
"""

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Any

from lxml import etree
from sqlalchemy import select
from sqlalchemy.orm import Session

from idml_foundation.ai.autocorrection_contracts import (
    AutomationContext,
    AutomationIntent,
    intent_digest,
)
from idml_foundation.ai.autocorrection_policy import evaluate_autocorrection, policy_digest
from idml_foundation.autocorrection_models import (
    AutomationAttempt,
    AutomationDiscard,
    AutomationGrantRecord,
    AutomationGrantRevocation,
)
from idml_foundation.database import ensure_write_transaction as _ensure_transaction
from idml_foundation.domain.canonical import Asset, CanonicalArticle
from idml_foundation.domain.common import content_digest
from idml_foundation.models import Artifact, Resource
from idml_foundation.pipeline.jats_builder import JatsBuilder
from idml_foundation.pipeline.profile import JournalProfile
from idml_foundation.pipeline.validation import OfflineJatsValidator, ValidationReport
from idml_foundation.release.package_builder import (
    AssetPayload,
    PackageBuild,
    PackageBuilder,
    PackageInput,
    PackageRole,
)
from idml_foundation.services.autocorrection_authorization import verify_parent_authorization
from idml_foundation.services.autocorrection_executor import (
    _artifact,
    _candidate,
    _human_state,
    _verified_attempt,
)
from idml_foundation.services.autocorrection_sources import ExtractionGrant, resolve_idml_evidence
from idml_foundation.services.canonical_heads import current_canonical_snapshot
from idml_foundation.services.package_validation import Executor, assess_rebuilt_package
from idml_foundation.services.xpm_execution import XpmExecutor
from idml_foundation.settings import Settings

_HREF = "{http://www.w3.org/1999/xlink}href"


@dataclass(frozen=True)
class RevalidatedAutomationPackage:
    """Private bytes/reports; only receipt is suitable for redacted diagnostics."""

    package: PackageBuild
    xml: bytes
    offline: ValidationReport | None
    formal: dict[str, Any]
    receipt: dict[str, Any]


def _current_candidate(
    db: Session,
    *,
    organization_id: str,
    attempt_id: str,
    intent: AutomationIntent,
    context: AutomationContext,
    profile: JournalProfile,
    settings: Settings,
    now: datetime,
) -> tuple[AutomationAttempt, CanonicalArticle]:
    """Re-derive all replacements from live bytes/grants, never trust stored values."""
    if now.utcoffset() is None:
        raise ValueError("clock_timezone_required")
    scope = context.scope
    if str(scope.organization_id) != organization_id or intent.scope != scope:
        raise PermissionError("automation_scope_mismatch")
    resource = db.scalar(
        select(Resource)
        .where(Resource.id == str(scope.resource_id), Resource.organization_id == organization_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    attempt = db.scalar(
        select(AutomationAttempt)
        .where(
            AutomationAttempt.id == attempt_id,
            AutomationAttempt.organization_id == organization_id,
            AutomationAttempt.resource_id == str(scope.resource_id),
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if resource is None or attempt is None:
        raise LookupError("automation_attempt_not_found")
    _verified_attempt(attempt)
    if (
        attempt.intent_sha256 != intent_digest(intent)
        or attempt.receipt["scope"] != scope.model_dump(mode="json")
        or attempt.receipt["policy_sha256"] != policy_digest()
        or attempt.receipt["state"] != "staged"
        or attempt.candidate is None
        or not attempt.xml_content
        or db.get(AutomationDiscard, attempt_id) is not None
    ):
        raise ValueError("automation_candidate_unavailable")
    snapshot = current_canonical_snapshot(
        db, organization_id=organization_id, resource_id=resource.id
    )
    if (
        snapshot is None
        or snapshot.id != str(scope.snapshot_id)
        or snapshot.content_sha256 != scope.snapshot_sha256
        or content_digest(snapshot.payload) != scope.snapshot_sha256
        or resource.version != scope.review_version
    ):
        raise ValueError("automation_stale_snapshot_or_revision")
    source = db.scalar(
        select(Artifact).where(
            Artifact.id == snapshot.source_artifact_id,
            Artifact.organization_id == organization_id,
            Artifact.sha256 == scope.source_idml_sha256,
        )
    )
    if source is None:
        raise ValueError("automation_source_mismatch")
    paths, human_hash = _human_state(db, organization_id, resource.id)
    if human_hash != attempt.receipt["human_state_sha256"]:
        raise ValueError("automation_human_state_changed")
    context = AutomationContext.model_validate(
        context.model_dump(mode="python")
        | {"protected_paths": tuple(sorted(set(context.protected_paths + paths)))}
    )
    article = CanonicalArticle.model_validate(snapshot.payload)
    idml = _artifact(db, organization_id, scope.source_idml_sha256, settings)
    asset_bytes = {}
    source_size = len(idml)
    for asset in article.assets:
        if asset.state == "present" and asset.sha256:
            data = _artifact(db, organization_id, asset.sha256, settings)
            source_size += len(data)
            if source_size > settings.upload_max_bytes:
                raise ValueError("automation_package_too_large")
            asset_bytes[asset.id] = data
    evidence = []
    for operation in attempt.receipt["operations"]:
        record = db.scalar(
            select(AutomationGrantRecord)
            .where(
                AutomationGrantRecord.id == operation["authorization_id"],
                AutomationGrantRecord.organization_id == organization_id,
                AutomationGrantRecord.resource_id == resource.id,
                AutomationGrantRecord.base_snapshot_id == snapshot.id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if (
            record is None
            or content_digest(record.payload) != record.payload_sha256
            or db.get(AutomationGrantRevocation, record.id) is not None
        ):
            raise ValueError("automation_grant_unavailable")
        grant = ExtractionGrant.model_validate(record.payload)
        if str(grant.authorization_id) != record.id or grant.scope != scope:
            raise ValueError("automation_grant_scope_mismatch")
        verify_parent_authorization(grant, settings, now)
        matches = [
            op
            for op in intent.operations
            if (op.operation, op.subject_id, op.evidence_id)
            == (grant.operation, grant.subject_id, grant.evidence_id)
        ]
        if len(matches) != 1:
            raise ValueError("automation_grant_operation_mismatch")
        evidence.append(
            resolve_idml_evidence(
                article=article,
                operation=matches[0],
                scope=scope,
                grant=grant,
                idml=idml,
                assets=asset_bytes,
                settings=settings,
                now=now,
            )
        )
    decision = evaluate_autocorrection(
        intent=intent,
        article=article,
        context=context,
        evidence=tuple(evidence),
        profile=profile,
        now=now,
    )
    if (
        decision.disposition != "eligible_for_candidate"
        or content_digest(decision) != attempt.receipt["decision_sha256"]
        or [op.model_dump(mode="json", exclude={"value"}) for op in decision.operations]
        != attempt.receipt["operations"]
    ):
        raise ValueError("automation_policy_recheck_failed")
    candidate = _candidate(article, decision)
    xml = JatsBuilder(sps_version=profile.sps_version).build(candidate)
    if (
        candidate.model_dump(mode="json") != attempt.candidate
        or xml != attempt.xml_content.encode()
    ):
        raise ValueError("automation_candidate_reconstruction_mismatch")
    return attempt, candidate


def _root(xml: bytes) -> Any:
    return etree.fromstring(
        xml,
        parser=etree.XMLParser(
            resolve_entities=False, load_dtd=False, no_network=True, recover=False, huge_tree=False
        ),
    )


def _graphics(root: Any) -> list[Any]:
    return [
        node
        for node in root.iter()
        if isinstance(node.tag, str)
        and etree.QName(node).localname in {"graphic", "inline-graphic"}
    ]


def _package_assets(article: CanonicalArticle, xml: bytes) -> tuple[Asset, ...]:
    root = _root(xml)
    if any(not _graphics(fig) for fig in root.iter("fig")):
        raise ValueError("automation_package_requires_exact_asset_mapping")
    hrefs = {node.get(_HREF, "") for node in _graphics(root)}
    # The IDML inventory also contains layout files and source PDFs of formulas
    # rendered as MathML. Only unverified, unreferenced entries may be omitted.
    return tuple(
        a for a in article.assets if a.logical_name in hrefs or a.sha256 or a.state == "present"
    )


def _verify_packaging(
    xml: bytes,
    files: tuple[PackageInput, ...],
    assets: tuple[AssetPayload, ...],
    *,
    package_stem: str,
    pdf: bytes,
) -> bytes:
    """Only exact graphic href renaming is permitted; all text/structure stays equal."""
    before = _root(xml)
    graphics = _graphics(before)
    expected_names = [node.get(_HREF, "") for node in graphics]
    by_name = {asset.source_name: asset for asset in assets}
    if len(set(expected_names)) != len(expected_names) or set(expected_names) != set(by_name):
        raise ValueError("automation_package_requires_exact_asset_mapping")
    expected: dict[str, tuple[PackageRole, str, bytes | None]] = {
        f"{package_stem}.xml": (PackageRole.XML, "application/xml", None),
        f"{package_stem}.pdf": (PackageRole.PDF, "application/pdf", pdf),
    }
    for index, node in enumerate(graphics, start=1):
        asset = by_name[node.get(_HREF)]
        name = f"{package_stem}-gf{index:02}{PurePosixPath(asset.source_name).suffix.casefold()}"
        node.set(_HREF, name)
        expected[name] = (PackageRole.ASSET, asset.media_type or "", asset.data)
    if len(files) != len(expected) or {item.name for item in files} != set(expected):
        raise ValueError("automation_package_manifest_mismatch")
    for item in files:
        role, media_type, data = expected[item.name]
        if (
            item.role != role
            or item.media_type != media_type
            or (data is not None and item.data != data)
        ):
            raise ValueError("automation_package_payload_changed")
    packaged_xml = next(item.data for item in files if item.role == PackageRole.XML)
    after = _root(packaged_xml)
    if (
        before.getroottree().docinfo.doctype != after.getroottree().docinfo.doctype
        or etree.tostring(before.getroottree(), method="c14n")
        != etree.tostring(after.getroottree(), method="c14n")
    ):
        raise ValueError("automation_package_xml_invariant_failure")
    return packaged_xml


def revalidate_candidate_package(
    db: Session,
    *,
    organization_id: str,
    attempt_id: str,
    intent: AutomationIntent,
    context: AutomationContext,
    pdf_artifact_id: str,
    pdf_sha256: str,
    profile: JournalProfile,
    settings: Settings,
    validator: OfflineJatsValidator,
    executor: Executor | None = None,
    xpm_executor: XpmExecutor | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> RevalidatedAutomationPackage:
    """Build and freshly assess private bytes. Does not store artifacts or change heads."""
    intent = AutomationIntent.model_validate(intent.model_dump(mode="python"))
    context = AutomationContext.model_validate(context.model_dump(mode="python"))
    started = clock()
    _ensure_transaction(db)
    with db.begin_nested():
        attempt, candidate = _current_candidate(
            db,
            organization_id=organization_id,
            attempt_id=attempt_id,
            intent=intent,
            context=context,
            profile=profile,
            settings=settings,
            now=started,
        )
        receipt_sha = attempt.receipt_sha256
        pdf_record = db.scalar(
            select(Artifact)
            .where(
                Artifact.id == pdf_artifact_id,
                Artifact.organization_id == organization_id,
                Artifact.sha256 == pdf_sha256,
                Artifact.media_type == "application/pdf",
            )
            .execution_options(populate_existing=True)
        )
        if pdf_record is None:
            raise ValueError("automation_pdf_unavailable")
        pdf = _artifact(db, organization_id, pdf_sha256, settings)
        if not pdf.startswith(b"%PDF-"):
            raise ValueError("automation_pdf_invalid")
        assets = []
        payload_size = len(pdf)
        xml = JatsBuilder(sps_version=profile.sps_version).build(candidate)
        for asset in _package_assets(candidate, xml):
            if (
                asset.state != "present"
                or not asset.sha256
                or asset.media_type not in {"image/jpeg", "image/png", "image/tiff"}
                or PurePosixPath(asset.logical_name).suffix.casefold()
                not in {".jpg", ".jpeg", ".png", ".tif", ".tiff"}
                or any(c in asset.logical_name for c in ("/", "\\", ":"))
            ):
                raise ValueError("automation_package_asset_unavailable")
            assets.append(
                AssetPayload(
                    source_name=asset.logical_name,
                    media_type=asset.media_type,
                    data=_artifact(db, organization_id, asset.sha256, settings),
                )
            )
            payload_size += len(assets[-1].data)
            if payload_size > settings.upload_max_bytes:
                raise ValueError("automation_package_too_large")
        # No figure-number heuristic is allowed in this automation path.
        hrefs = [node.get(_HREF, "") for node in _graphics(_root(xml))]
        if (
            len(hrefs) != len(set(hrefs))
            or len(assets) != len(set(a.source_name for a in assets))
            or set(hrefs) != {a.source_name for a in assets}
        ):
            raise ValueError("automation_package_requires_exact_asset_mapping")
        if len(xml) + len(pdf) + sum(len(a.data) for a in assets) > settings.upload_max_bytes:
            raise ValueError("automation_package_too_large")
        stem = profile.package_stem(candidate.article_id)
        builder = PackageBuilder()
        files = builder.scielo_files(package_stem=stem, xml=xml, pdf=pdf, assets=tuple(assets))
        packaged_xml = _verify_packaging(xml, files, tuple(assets), package_stem=stem, pdf=pdf)
        offline = None
        try:
            report = validator.validate(
                packaged_xml, asset_names={f.name for f in files if f.role == PackageRole.ASSET}
            )
            report = ValidationReport.model_validate(report.model_dump(mode="python"))
            if report.xml_sha256 != hashlib.sha256(packaged_xml).hexdigest():
                raise ValueError("offline_report_hash_mismatch")
            if report.valid == any(issue.severity == "error" for issue in report.issues):
                raise ValueError("offline_report_result_inconsistent")
            offline = report
        except Exception:
            offline = None  # Report exceptions can contain private XML or credentials.
        package = builder.build(
            article_id=candidate.article_id,
            profile_id=profile.profile_id,
            source_idml_sha256=context.scope.source_idml_sha256,
            files=files,
            validator_versions={"offline": offline.validator_profile if offline else "unavailable"},
        )
        if package.package_size_bytes > settings.upload_max_bytes:
            raise ValueError("automation_package_too_large")
        # Failed offline validation must not dispatch work to external executors.
        formal = assess_rebuilt_package(
            xml=packaged_xml,
            package=package.archive,
            executor=executor,
            settings=settings,
            offline_valid=offline is not None and offline.valid,
            xpm_executor=xpm_executor,
            scope={
                "organization_id": organization_id,
                "resource_id": str(context.scope.resource_id),
                "source_idml_sha256": context.scope.source_idml_sha256,
                "journal_profile_id": profile.profile_id,
                "xml_sha256": hashlib.sha256(packaged_xml).hexdigest(),
                "package_sha256": hashlib.sha256(package.archive).hexdigest(),
            },
        )
        ended = clock()
        if ended.utcoffset() is None:
            raise ValueError("clock_timezone_required")
        if ended < started:
            raise ValueError("automation_clock_regressed")
        current, _ = _current_candidate(
            db,
            organization_id=organization_id,
            attempt_id=attempt_id,
            intent=intent,
            context=context,
            profile=profile,
            settings=settings,
            now=ended,
        )
        if (
            current.receipt_sha256 != receipt_sha
            or _artifact(db, organization_id, pdf_sha256, settings) != pdf
        ):
            raise ValueError("automation_package_inputs_changed")
        reasons = list(formal["reasons"])
        if offline is None:
            reasons.append("offline-validation-unavailable")
        elif not offline.valid:
            reasons.append("offline-validation-failed")
        receipt = {
            "version": "autocorrection-package-receipt-1.0",
            "attempt_id": attempt_id,
            "scope": context.scope.model_dump(mode="json"),
            "previous_receipt_sha256": receipt_sha,
            "candidate_sha256": content_digest(candidate),
            "pdf_artifact_id": pdf_artifact_id,
            "pdf_sha256": pdf_sha256,
            "xml_sha256": hashlib.sha256(packaged_xml).hexdigest(),
            "package_sha256": package.package_sha256,
            "manifest_sha256": content_digest(package.manifest),
            "offline_report_sha256": content_digest(offline) if offline else None,
            "formal_assessment_sha256": content_digest(formal),
            "state": "blocked" if offline is not None and not offline.valid else formal["state"],
            "reasons": sorted(set(reasons)),
            "started_at": started.isoformat(),
            "checked_at": ended.isoformat(),
            "active_snapshot_changed": False,
            "promotion_authorized": False,
            "release_approved": False,
        }
        return RevalidatedAutomationPackage(package, packaged_xml, offline, formal, receipt)
