"""Web-initiated evaluation, limited to the qualified affiliation operation."""

import asyncio
import hashlib
import json
import os
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from lxml import etree
from sqlalchemy.orm import Session

from idml_foundation.ai.autocorrection_contracts import (
    POLICY_VERSION,
    AutomationContext,
    AutomationScope,
    Digest,
)
from idml_foundation.ai.autocorrection_policy import policy_digest
from idml_foundation.ai.edit_cycle import MODEL, review_candidate
from idml_foundation.ai.openclaw_client import OpenClawResponsesClient
from idml_foundation.autocorrection_models import (
    AutomationAttempt,
    AutomationDiscard,
    AutomationGrantRecord,
)
from idml_foundation.domain.canonical import CanonicalArticle
from idml_foundation.domain.common import StrictModel, content_digest
from idml_foundation.models import Artifact, DomainSnapshot, Job, utcnow
from idml_foundation.pipeline.profile import load_profile
from idml_foundation.pipeline.validation import OfflineJatsValidator
from idml_foundation.schemas import EditEvaluationPayload, EditPreflightPayload
from idml_foundation.services.artifacts import read_artifact_bytes
from idml_foundation.services.autocorrection_authorization import (
    provision_field_grants,
    verify_parent_authorization,
)
from idml_foundation.services.autocorrection_executor import _human_state, _verified_attempt
from idml_foundation.services.autocorrection_preflight import run_edit_preflight
from idml_foundation.services.autocorrection_promotion import promote_revalidated_candidate
from idml_foundation.services.autocorrection_sources import ExtractionGrant, resolve_idml_evidence
from idml_foundation.services.enrichment import _read
from idml_foundation.settings import Settings


class WebEditDecision(StrictModel):
    purpose: Literal["review-and-promote-affiliation-v1"]
    model: Literal["openai/gpt-5.4-mini"]
    scope: EditEvaluationPayload
    organization_id: UUID
    authorization_id: UUID
    allowed_literal_sha256: Digest
    pdf_artifact_id: UUID
    pdf_sha256: Digest


def _selection(
    settings: Settings, org: str, request: EditEvaluationPayload
) -> WebEditDecision | None:
    root = settings.automation_authorization_root
    if root is None:
        return None
    if any(p.is_symlink() or p.is_junction() for p in (root, *root.absolute().parents)):
        raise ValueError("unsafe_decision_root")
    path = (
        Path("web-edit-decisions")
        / str(UUID(org))
        / str(request.resource_id)
        / str(request.canonical_snapshot_id)
        / f"{request.review_version}.json"
    )
    try:
        decision = WebEditDecision.model_validate_json(_read(root, path, 8192))
    except FileNotFoundError:
        return None
    if decision.scope != request or str(decision.organization_id) != org:
        raise ValueError("web_decision_scope_mismatch")
    return decision


def evaluate_revision(
    db: Session, job: Job, settings: Settings, *, operator_active: Callable[[], bool] | None = None
) -> dict[str, Any]:
    request = EditEvaluationPayload.model_validate(job.payload)
    decision = _selection(settings, job.organization_id, request)
    preflight = run_edit_preflight(
        db,
        job,
        settings,
        request=EditPreflightPayload(
            **request.model_dump(), authorization_id=decision.authorization_id if decision else None
        ),
    )
    result = dict(preflight, version="web-edit-cycle-1.0")
    if preflight["state"] != "staged" or preflight.get("offline_valid") is not True or not decision:
        return result
    if not settings.feature_web_edit_provider:
        return dict(result, reason="provider_window_closed")
    if (
        not settings.validator_socket
        or not settings.xpm_socket
        or not settings.validator_scoped_authorities
    ):
        return dict(result, reason="formal_validation_unavailable")
    scope = AutomationScope.model_validate(preflight["scope"])
    profile = load_profile(settings.journal_profile_path)
    batch = provision_field_grants(
        db,
        organization_id=job.organization_id,
        scope=scope,
        authorization_id=decision.authorization_id,
        profile=profile,
        settings=settings,
        now=utcnow(),
        require_revision_decision=True,
    )
    if (
        len(batch.intent.operations) != 1
        or batch.intent.operations[0].operation != "affiliation-original-literal"
    ):
        return dict(result, state="abstained", reason="operation_outside_web_scope")
    op = batch.intent.operations[0]
    attempt = db.get(AutomationAttempt, preflight["attempt_id"])
    snap = db.get(DomainSnapshot, str(scope.snapshot_id))
    if not attempt or not snap or not attempt.xml_content or not snap.source_artifact_id:
        raise ValueError("candidate_unavailable")
    _verified_attempt(attempt)
    _, human_hash = _human_state(db, job.organization_id, str(scope.resource_id))
    if (
        db.get(AutomationDiscard, attempt.id) is not None
        or human_hash != attempt.receipt["human_state_sha256"]
    ):
        return dict(result, state="refused", reason="candidate_no_longer_current")
    article = CanonicalArticle.model_validate(snap.payload)
    record = db.get(AutomationGrantRecord, attempt.receipt["operations"][0]["authorization_id"])
    if not record or content_digest(record.payload) != record.payload_sha256:
        raise ValueError("grant_integrity_failure")
    grant = ExtractionGrant.model_validate(record.payload)
    if grant.parent_authorization_id != decision.authorization_id:
        return dict(result, state="refused", reason="grant_scope_mismatch")
    source = db.get(Artifact, snap.source_artifact_id)
    if (
        source is None
        or source.organization_id != job.organization_id
        or source.scanner_status != "clamav_clean"
    ):
        return dict(result, state="refused", reason="source_unverified")
    evidence = resolve_idml_evidence(
        article=article,
        operation=op,
        scope=scope,
        grant=grant,
        idml=read_artifact_bytes(source, settings),
        assets={},
        settings=settings,
        now=utcnow(),
    )
    if evidence.source_text_sha256 != decision.allowed_literal_sha256:
        return dict(result, state="refused", reason="literal_not_authorized")
    xml = attempt.xml_content.encode()
    if hashlib.sha256(xml).hexdigest() != preflight["xml_sha256"]:
        raise ValueError("candidate_hash_mismatch")
    (position,) = [i for i, a in enumerate(article.front.affiliations) if a.id == op.subject_id]
    aff = etree.fromstring(xml, etree.XMLParser(resolve_entities=False, no_network=True)).findall(
        "front/article-meta/aff"
    )[position]
    (node,) = aff.findall("institution[@content-type='original']")
    literal = node.text
    if literal != evidence.source_text:
        raise ValueError("candidate_literal_mismatch")

    def authorized() -> bool:
        try:
            verify_parent_authorization(grant, settings, utcnow())
            return (operator_active is None or operator_active()) and _selection(
                settings, job.organization_id, request
            ) == decision
        except (ValueError, OSError):
            return False

    packet = dict(
        xml_sha256=preflight["xml_sha256"],
        operation=op.operation,
        source_literal=literal,
        original_field="missing",
        candidate_element="article-meta/aff/institution[@content-type='original']",
        candidate_value=literal,
        evidence_sha256=evidence.source_text_sha256,
    )
    client = OpenClawResponsesClient(
        base_url=settings.openclaw_gateway_url,
        token=settings.openclaw_gateway_token.get_secret_value(),
        expected_model_key=MODEL,
    )
    claim = (
        settings.artifact_root
        / ".web-edit-runs"
        / str(scope.organization_id)
        / str(decision.authorization_id)
    )
    claim.parent.mkdir(parents=True, exist_ok=True)
    try:
        with claim.open("x") as f:
            f.write(job.id)
    except FileExistsError:
        return dict(result, state="refused", reason="decision_already_used")

    def checkpoint(receipt: dict[str, Any]) -> None:
        temporary = claim.with_suffix(".writing")
        temporary.write_text(json.dumps(receipt), encoding="utf-8")
        os.replace(temporary, claim.with_suffix(".json"))

    started = utcnow()
    votes = asyncio.run(
        review_candidate(
            preflight,
            packet,
            client,
            still_authorized=authorized,
            interrupted=lambda: False,
            checkpoint=checkpoint,
        )
    )
    result.update(review=votes, provider_calls=len(votes["calls"]))
    if votes["state"] != "supported_for_revalidation" or not authorized():
        return dict(
            result,
            state="refused",
            reason=votes["state"]
            if votes["state"] != "supported_for_revalidation"
            else "authorization_refused",
        )
    context = AutomationContext.model_validate(
        dict(
            scope=scope,
            enabled=True,
            policy_version=POLICY_VERSION,
            policy_sha256=policy_digest(),
            cycle=max(c["round"] for c in votes["calls"]),
            started_at=started,
            consumed_tokens=sum(c["input_tokens"] + c["output_tokens"] for c in votes["calls"]),
            consumed_cost_usd=votes["cost_microusd"] / 1000000,
            other_active_executions=0,
            findings=batch.findings,
        )
    )

    def checked_clock() -> datetime:
        if not authorized():
            raise ValueError("web_edit_authorization_revoked")
        return utcnow()

    promotion = promote_revalidated_candidate(
        db,
        organization_id=job.organization_id,
        request_id=UUID(job.id),
        attempt_id=attempt.id,
        intent=batch.intent,
        context=context,
        pdf_artifact_id=str(decision.pdf_artifact_id),
        pdf_sha256=decision.pdf_sha256,
        profile=profile,
        settings=settings,
        validator=OfflineJatsValidator(
            Path(__file__).resolve().parents[3] / "vendor" / "jats" / "1.3"
        ),
        clock=checked_clock,
    )
    checked_clock()
    return dict(
        result,
        state="applied" if promotion["applied_now"] else "blocked",
        reason="native_validation",
        active_snapshot_changed=promotion["applied_now"],
        revalidation_id=promotion["revalidation_id"],
    )
