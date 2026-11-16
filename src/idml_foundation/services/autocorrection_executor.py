"""VH-09 staging transaction. Never promotes a candidate or approves a release.

The caller owns commit/rollback. Runtime context/validator/profile are trusted
server dependencies; only AutomationIntent may come from an agent. No public route
is installed here. Source proofs are resolved from tenant storage inside staging.
"""

import hashlib
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from idml_foundation.ai.autocorrection_contracts import (
    AutomationContext,
    AutomationDecision,
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
from idml_foundation.domain.canonical import CanonicalArticle
from idml_foundation.domain.common import canonical_bytes, content_digest
from idml_foundation.models import Artifact, DomainSnapshot, Resource, ReviewDecision, ReviewItem
from idml_foundation.pipeline.jats_builder import JatsBuilder
from idml_foundation.pipeline.profile import JournalProfile
from idml_foundation.pipeline.validation import OfflineJatsValidator, ValidationReport
from idml_foundation.services.artifacts import read_artifact_bytes
from idml_foundation.services.autocorrection_sources import (
    ExtractionGrant,
    SourceResolutionError,
    resolve_idml_evidence,
)
from idml_foundation.services.canonical_heads import current_canonical_snapshot
from idml_foundation.settings import Settings


def register_extraction_grant(
    db: Session, *, organization_id: str, grant: ExtractionGrant
) -> AutomationGrantRecord:
    """Trusted operator provisioning only; not a consent endpoint for clients/agents."""
    grant = ExtractionGrant.model_validate(grant.model_dump(mode="python"))
    snapshot = db.scalar(
        select(DomainSnapshot).where(
            DomainSnapshot.id == str(grant.scope.snapshot_id),
            DomainSnapshot.organization_id == organization_id,
            DomainSnapshot.resource_id == str(grant.scope.resource_id),
        )
    )
    if (
        str(grant.scope.organization_id) != organization_id
        or snapshot is None
        or snapshot.content_sha256 != grant.scope.snapshot_sha256
    ):
        raise ValueError("grant_scope_mismatch")
    record = AutomationGrantRecord(
        id=str(grant.authorization_id),
        organization_id=organization_id,
        resource_id=str(grant.scope.resource_id),
        base_snapshot_id=str(grant.scope.snapshot_id),
        payload=grant.model_dump(mode="json"),
        payload_sha256=content_digest(grant),
    )
    db.add(record)
    db.flush()
    return record


def revoke_extraction_grant(
    db: Session, *, organization_id: str, authorization_id: str, decision_sha256: str
) -> AutomationGrantRevocation:
    _ensure_transaction(db)
    record = db.scalar(
        select(AutomationGrantRecord)
        .where(
            AutomationGrantRecord.id == authorization_id,
            AutomationGrantRecord.organization_id == organization_id,
        )
        .with_for_update()
    )
    if record is None:
        raise LookupError("grant_not_found")
    if len(decision_sha256) != 64 or any(c not in "0123456789abcdef" for c in decision_sha256):
        raise ValueError("invalid_revocation_decision_hash")
    existing = db.get(AutomationGrantRevocation, authorization_id)
    if existing is not None:
        if existing.organization_id != organization_id:
            raise ValueError("revocation_scope_mismatch")
        return existing
    revocation = AutomationGrantRevocation(
        grant_id=authorization_id,
        organization_id=organization_id,
        decision_sha256=decision_sha256,
    )
    db.add(revocation)
    db.flush()
    return revocation


def _verified_attempt(record: AutomationAttempt) -> AutomationAttempt:
    if content_digest(record.receipt) != record.receipt_sha256:
        raise ValueError("attempt_integrity_failure")
    receipt = record.receipt
    if (
        receipt["intent_sha256"] != record.intent_sha256
        or receipt["scope"]["organization_id"] != record.organization_id
        or receipt["scope"]["resource_id"] != record.resource_id
        or receipt["scope"]["snapshot_id"] != record.base_snapshot_id
        or receipt["candidate_sha256"]
        != (content_digest(record.candidate) if record.candidate is not None else None)
        or receipt["xml_sha256"]
        != (hashlib.sha256(record.xml_content.encode()).hexdigest() if record.xml_content else None)
        or receipt["validation_sha256"]
        != (content_digest(record.validation) if record.validation is not None else None)
    ):
        raise ValueError("attempt_integrity_failure")
    return record


def _existing(
    db: Session, organization_id: str, resource_id: str, digest: str
) -> AutomationAttempt | None:
    record = db.scalar(
        select(AutomationAttempt)
        .where(
            AutomationAttempt.organization_id == organization_id,
            AutomationAttempt.resource_id == resource_id,
            AutomationAttempt.intent_sha256 == digest,
        )
        .execution_options(populate_existing=True)
    )
    return _verified_attempt(record) if record is not None else None


def _artifact(db: Session, organization_id: str, digest: str, settings: Settings) -> bytes:
    record = db.scalar(
        select(Artifact)
        .where(Artifact.organization_id == organization_id, Artifact.sha256 == digest)
        .execution_options(populate_existing=True)
    )
    if record is None or record.scanner_status != "clamav_clean":
        raise SourceResolutionError("source_artifact_unavailable")
    # Enforce the tenant/content-addressed key, even if a DB row was corrupted.
    if record.storage_key != f"{organization_id}/{digest[:2]}/{digest}":
        raise SourceResolutionError("source_artifact_integrity_failure")
    try:
        return read_artifact_bytes(record, settings)
    except (OSError, ValueError) as exc:
        raise SourceResolutionError("source_artifact_integrity_failure") from exc


def _human_state(
    db: Session, organization_id: str, resource_id: str
) -> tuple[tuple[str, ...], str]:
    items = list(
        db.scalars(
            select(ReviewItem)
            .where(
                ReviewItem.organization_id == organization_id, ReviewItem.resource_id == resource_id
            )
            .order_by(ReviewItem.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    )
    decisions = list(
        db.scalars(
            select(ReviewDecision)
            .join(ReviewItem, ReviewItem.id == ReviewDecision.review_item_id)
            .where(
                ReviewDecision.organization_id == organization_id,
                ReviewItem.organization_id == organization_id,
                ReviewItem.resource_id == resource_id,
            )
            .order_by(ReviewDecision.id)
        )
    )
    # Conservative: current review paths AND all historical human paths are protected.
    paths = [item.field_path or "/" for item in items]
    paths.extend(op.get("path", "/") for decision in decisions for op in decision.patch)
    fingerprint = content_digest(
        {
            "items": [
                [i.id, i.version, i.state, i.base_snapshot_id, i.assigned_user_id, i.field_path]
                for i in items
            ],
            "decisions": [[d.id, d.patch_sha256, d.action] for d in decisions],
        }
    )
    return tuple(sorted(set(paths))), fingerprint


def _candidate(article: CanonicalArticle, decision: AutomationDecision) -> CanonicalArticle:
    original = article.model_dump(mode="json")
    payload = article.model_dump(mode="json")
    for op in decision.operations:
        parent: Any = payload
        parts = op.path.split("/")[1:]
        for part in parts[:-1]:
            parent = parent[int(part)] if isinstance(parent, list) else parent[part]
        leaf = parts[-1]
        if content_digest({"value": parent[leaf]}) != op.before_sha256:
            raise ValueError("candidate_before_hash_mismatch")
        value = op.value if isinstance(op.value, str) else op.value.model_dump(mode="json")
        if content_digest({"value": value}) != op.after_sha256:
            raise ValueError("candidate_after_hash_mismatch")
        parent[leaf] = value
    candidate = CanonicalArticle.model_validate(payload)
    # Pydantic normalization must not make any change beyond the prepared replacements.
    if candidate.model_dump(mode="json") != payload or article.model_dump(mode="json") != original:
        raise ValueError("candidate_content_invariant_failure")
    return candidate


def stage_autocorrection(
    db: Session,
    *,
    organization_id: str,
    intent: AutomationIntent,
    context: AutomationContext,
    profile: JournalProfile,
    settings: Settings,
    validator: OfflineJatsValidator,
    now: datetime,
) -> AutomationAttempt:
    """Idempotent private staging with fresh source/policy checks and a savepoint.

    No network calls or active snapshot writes. Repetition returns the historical
    attempt, NOT fresh eligibility; promotion must recheck grants/human state later.
    """
    intent = AutomationIntent.model_validate(intent.model_dump(mode="python"))
    context = AutomationContext.model_validate(context.model_dump(mode="python"))
    scope = context.scope
    if str(scope.organization_id) != organization_id or intent.scope != scope:
        raise PermissionError("automation_scope_mismatch")
    if now.utcoffset() is None:
        raise ValueError("clock_timezone_required")
    resource_id = str(scope.resource_id)
    digest = intent_digest(intent)
    _ensure_transaction(db)
    try:
        with db.begin_nested():
            resource = db.scalar(
                select(Resource)
                .where(Resource.id == resource_id, Resource.organization_id == organization_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if resource is None:
                raise LookupError("automation_resource_not_found")
            previous = _existing(db, organization_id, resource_id, digest)
            if previous is not None:
                return previous
            snapshot = current_canonical_snapshot(
                db, organization_id=organization_id, resource_id=resource_id
            )
            if (
                snapshot is None
                or snapshot.id != str(scope.snapshot_id)
                or snapshot.content_sha256 != scope.snapshot_sha256
                or content_digest(snapshot.payload) != scope.snapshot_sha256
                or resource.version != scope.review_version
            ):
                raise ValueError("automation_stale_snapshot_or_revision")
            article = CanonicalArticle.model_validate(snapshot.payload)
            paths, human_hash = _human_state(db, organization_id, resource_id)
            # Validate again so malformed historical pointers cannot escape protection.
            context_data = context.model_dump(mode="python")
            context_data["protected_paths"] = tuple(sorted(set(context.protected_paths + paths)))
            context = AutomationContext.model_validate(context_data)
            evidence = []
            source_error = None
            try:
                source = db.scalar(
                    select(Artifact).where(
                        Artifact.id == snapshot.source_artifact_id,
                        Artifact.organization_id == organization_id,
                        Artifact.sha256 == scope.source_idml_sha256,
                    )
                )
                if source is None:
                    raise SourceResolutionError("snapshot_source_mismatch")
                idml = _artifact(db, organization_id, scope.source_idml_sha256, settings)
                records = list(
                    db.scalars(
                        select(AutomationGrantRecord)
                        .where(
                            AutomationGrantRecord.organization_id == organization_id,
                            AutomationGrantRecord.resource_id == resource_id,
                            AutomationGrantRecord.base_snapshot_id == snapshot.id,
                        )
                        .order_by(AutomationGrantRecord.id)
                        .with_for_update()
                        .execution_options(populate_existing=True)
                    )
                )
                grants = []
                for record in records:
                    if content_digest(record.payload) != record.payload_sha256:
                        raise SourceResolutionError("grant_integrity_failure")
                    grant = ExtractionGrant.model_validate(record.payload)
                    if str(grant.authorization_id) != record.id:
                        raise SourceResolutionError("grant_scope_mismatch")
                    if grant.scope != scope:
                        # A review can advance without changing the canonical bytes.
                        # Grants for an older review are history, never authority for this one.
                        old_review = grant.scope.review_version
                        if old_review < scope.review_version and grant.scope == scope.model_copy(
                            update={"review_version": old_review}
                        ):
                            continue
                        raise SourceResolutionError("grant_scope_mismatch")
                    if db.get(AutomationGrantRevocation, record.id) is None:
                        from idml_foundation.services.autocorrection_authorization import (
                            verify_parent_authorization,
                        )

                        verify_parent_authorization(grant, settings, now)
                        grants.append(grant)
                for op in intent.operations:
                    matches = [
                        g
                        for g in grants
                        if (g.operation, g.subject_id, g.evidence_id)
                        == (op.operation, op.subject_id, op.evidence_id)
                    ]
                    if len(matches) != 1:
                        raise SourceResolutionError("grant_missing_revoked_or_ambiguous")
                    assets = {}
                    if op.operation == "figure-asset-exact":
                        # Read only present image artifacts; the resolver selects the exact name.
                        for asset in article.assets:
                            if asset.state == "present" and asset.sha256:
                                assets[asset.id] = _artifact(
                                    db, organization_id, asset.sha256, settings
                                )
                    evidence.append(
                        resolve_idml_evidence(
                            article=article,
                            operation=op,
                            scope=scope,
                            grant=matches[0],
                            idml=idml,
                            assets=assets,
                            settings=settings,
                            now=now,
                        )
                    )
            except SourceResolutionError as exc:
                source_error = str(exc)
            except ValueError:
                source_error = "invalid_stored_source_grant"
            decision = (
                AutomationDecision(
                    scope=scope, intent_sha256=digest, disposition="refused", reason=source_error
                )
                if source_error
                else evaluate_autocorrection(
                    intent=intent,
                    article=article,
                    context=context,
                    evidence=tuple(evidence),
                    profile=profile,
                    now=now,
                )
            )
            candidate = None
            xml = None
            validation = None
            if decision.disposition == "eligible_for_candidate":
                candidate = _candidate(article, decision)
                xml = JatsBuilder(sps_version=profile.sps_version).build(candidate)
                if max(len(xml), len(canonical_bytes(candidate))) > settings.upload_max_bytes:
                    raise ValueError("automation_candidate_too_large")
                try:
                    report = validator.validate(
                        xml, asset_names={a.logical_name for a in candidate.assets}
                    )
                    report = ValidationReport.model_validate(report.model_dump(mode="python"))
                    if report.xml_sha256 != hashlib.sha256(xml).hexdigest():
                        raise ValueError("offline_report_hash_mismatch")
                    validation = {"state": "completed", "report": report.model_dump(mode="json")}
                except Exception:
                    # Validator errors may contain private XML. Never persist exception text.
                    validation = {"state": "unavailable", "code": "offline_validation_unavailable"}
                latest = current_canonical_snapshot(
                    db, organization_id=organization_id, resource_id=resource_id
                )
                latest_id = latest.id if latest else None
                current_version = db.scalar(
                    select(Resource.version).where(Resource.id == resource_id)
                )
                _, current_human_hash = _human_state(db, organization_id, resource_id)
                revoked = db.scalar(
                    select(AutomationGrantRevocation.grant_id)
                    .where(
                        AutomationGrantRevocation.grant_id.in_(
                            [str(e.authorization_id) for e in evidence]
                        )
                    )
                    .limit(1)
                )
                if (
                    latest_id != snapshot.id
                    or current_version != scope.review_version
                    or current_human_hash != human_hash
                    or revoked is not None
                ):
                    raise ValueError("automation_concurrent_state_change")
                # Source authorization files are outside DB row locks; re-read after
                # construction too. An earlier consent hash is not current consent.
                for item in evidence:
                    current_grant = next(
                        g for g in grants if g.authorization_id == item.authorization_id
                    )
                    verify_parent_authorization(current_grant, settings, now)
            receipt = {
                "version": "autocorrection-staging-receipt-1.0",
                "actor": "service:idml-autocorrection",
                "scope": scope.model_dump(mode="json"),
                "policy_sha256": policy_digest(),
                "intent_sha256": digest,
                "decision_sha256": content_digest(decision),
                "human_state_sha256": human_hash,
                "state": "staged" if candidate else decision.disposition,
                "reason": "candidate_requires_full_revalidation" if candidate else decision.reason,
                "operations": [
                    op.model_dump(mode="json", exclude={"value"}) for op in decision.operations
                ],
                "candidate_sha256": content_digest(candidate) if candidate else None,
                "xml_sha256": hashlib.sha256(xml).hexdigest() if xml else None,
                "validation_sha256": content_digest(validation) if validation else None,
                "recorded_at": now.isoformat(),
                "active_snapshot_changed": False,
                "requires_revalidation": True,
                "release_approved": False,
            }
            attempt = AutomationAttempt(
                organization_id=organization_id,
                resource_id=resource_id,
                base_snapshot_id=snapshot.id,
                intent_sha256=digest,
                receipt=receipt,
                receipt_sha256=content_digest(receipt),
                candidate=candidate.model_dump(mode="json") if candidate else None,
                xml_content=xml.decode() if xml else None,
                validation=validation,
            )
            db.add(attempt)
            db.flush()
            return attempt
    except IntegrityError:
        # Unique intent is the final arbiter even when row locks are unavailable (SQLite).
        previous = _existing(db, organization_id, resource_id, digest)
        if previous is None:
            raise
        return previous


def discard_candidate(
    db: Session, *, organization_id: str, attempt_id: str, now: datetime
) -> AutomationDiscard:
    """Withdraw a staged copy, preserving bytes/history; not a rollback of an active version."""
    if now.utcoffset() is None:
        raise ValueError("clock_timezone_required")
    _ensure_transaction(db)
    attempt = db.scalar(
        select(AutomationAttempt)
        .where(
            AutomationAttempt.id == attempt_id,
            AutomationAttempt.organization_id == organization_id,
        )
        .with_for_update()
    )
    if attempt is None:
        raise LookupError("automation_attempt_not_found")
    _verified_attempt(attempt)
    if attempt.candidate is None:
        raise ValueError("automation_attempt_has_no_candidate")
    previous = db.get(AutomationDiscard, attempt_id)
    if previous is not None:
        if (
            content_digest(previous.receipt) != previous.receipt_sha256
            or previous.organization_id != organization_id
            or previous.receipt.get("organization_id") != organization_id
            or previous.receipt.get("attempt_id") != attempt_id
            or previous.receipt.get("previous_receipt_sha256") != attempt.receipt_sha256
        ):
            raise ValueError("discard_integrity_failure")
        return previous
    receipt = {
        "version": "autocorrection-discard-1.0",
        "actor": "service:idml-autocorrection",
        "attempt_id": attempt_id,
        "organization_id": organization_id,
        "previous_receipt_sha256": attempt.receipt_sha256,
        "state": "discarded",
        "recorded_at": now.isoformat(),
        "active_snapshot_changed": False,
        "release_approved": False,
    }
    record = AutomationDiscard(
        attempt_id=attempt_id,
        organization_id=organization_id,
        receipt=receipt,
        receipt_sha256=content_digest(receipt),
    )
    db.add(record)
    db.flush()
    return record
