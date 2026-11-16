"""Closed, non-mutating eligibility policy. No model-supplied values or JSON pointers."""

import hashlib
from collections.abc import Iterator
from datetime import datetime

from pydantic import ValidationError

from idml_foundation.ai.autocorrection_contracts import (
    POLICY_VERSION,
    PROFILE_SHA256,
    AutomationContext,
    AutomationDecision,
    AutomationEvent,
    AutomationEvidence,
    AutomationIntent,
    AutomationOperation,
    PreparedAutomationOperation,
    intent_digest,
)
from idml_foundation.ai.security import contains_policy_override
from idml_foundation.domain.canonical import (
    CanonicalArticle,
    FieldState,
    FigureBlock,
    Section,
    SourcedText,
)
from idml_foundation.domain.common import content_digest
from idml_foundation.pipeline.profile import JournalProfile


def policy_manifest() -> dict[str, object]:
    return {
        "version": POLICY_VERSION,
        "profile_sha256": PROFILE_SHA256,
        "operations": {
            "country-code-exact": "/front/affiliations/{index}/country_code",
            "figure-asset-exact": "/body/{section}/[children/{section}/]blocks/{index}/asset_id",
            "affiliation-original-literal": "/front/affiliations/{index}/original_text",
        },
        "missing_only": True,
        "source_kind": "idml",
        "model_values_allowed": False,
        "max_cycles": 2,
        "max_operations": 5,
        "max_parallel_articles": 1,
        "default_seconds": 300,
        "default_tokens": 50_000,
        "default_cost_usd": "5.00",
        "revalidation_required": True,
        "historical_human_decisions_immutable": True,
        "release_approved": False,
    }


def policy_digest() -> str:
    return content_digest(policy_manifest())


def value_digest(value: SourcedText | str | None) -> str:
    return content_digest(
        {"value": value.model_dump(mode="json") if isinstance(value, SourcedText) else value}
    )


class _Refused(ValueError):
    pass


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise _Refused(code)


def _sections(sections: tuple[Section, ...], root: str = "/body") -> Iterator[tuple[str, Section]]:
    for index, section in enumerate(sections):
        path = f"{root}/{index}"
        yield path, section
        yield from _sections(section.children, path + "/children")


def _missing(value: SourcedText | None) -> bool:
    return value is None or (
        value.state == FieldState.MISSING and value.value is None and not value.alternatives
    )


def _prepare(
    operation: AutomationOperation,
    article: CanonicalArticle,
    evidence: AutomationEvidence,
    profile: JournalProfile,
) -> PreparedAutomationOperation:
    source = next((e for e in article.evidence if e.id == evidence.evidence_id), None)
    _require(source is not None, "evidence_not_in_snapshot")
    assert source is not None
    _require(
        source.source_kind == "idml"
        and source.locator.artifact_sha256 == evidence.artifact_sha256
        and source.content_sha256 == evidence.source_text_sha256,
        "source_content_not_verified",
    )
    before: SourcedText | str | None
    after: SourcedText | str
    if operation.operation == "figure-asset-exact":
        figures = [
            (f"{path}/blocks/{i}/asset_id", b)
            for path, section in _sections(article.body)
            for i, b in enumerate(section.blocks)
            if isinstance(b, FigureBlock) and b.id == operation.subject_id
        ]
        _require(len(figures) == 1, "subject_not_qualified")
        path, figure = figures[0]
        _require(evidence.evidence_id in figure.evidence_ids, "evidence_not_bound_to_field")
        _require(figure.asset_id is None, "existing_value_protected")
        _require(
            evidence.source_text not in {".", ".."}
            and not any(c in evidence.source_text for c in "/\\:"),
            "asset_name_not_qualified",
        )
        # Never fuzzy-match, infer from order, change paths, or generate an asset ID.
        matches = [a for a in article.assets if a.logical_name == evidence.source_text]
        _require(len(matches) == 1, "asset_target_not_unique")
        asset = matches[0]
        _require(
            asset.state == FieldState.PRESENT
            and asset.sha256 == evidence.target_asset_sha256
            and asset.media_type in {"image/jpeg", "image/png", "image/tiff"},
            "asset_target_not_verified",
        )
        before, after = figure.asset_id, asset.id
    else:
        affiliations = [
            (i, a) for i, a in enumerate(article.front.affiliations) if a.id == operation.subject_id
        ]
        _require(len(affiliations) == 1, "subject_not_qualified")
        index, affiliation = affiliations[0]
        _require(evidence.evidence_id in affiliation.evidence_ids, "evidence_not_bound_to_field")
        if operation.operation == "country-code-exact":
            country = affiliation.country
            _require(country is not None, "country_source_missing")
            assert country is not None
            _require(
                country.state == FieldState.PRESENT
                and not country.alternatives
                and country.value == evidence.source_text
                and evidence.evidence_id in country.evidence_ids,
                "country_source_not_exact",
            )
            code = profile.country_codes.get(evidence.source_text)
            _require(code is not None, "country_outside_qualified_profile")
            assert code is not None
            value, before, leaf = code, affiliation.country_code, "country_code"
        else:
            _require(
                affiliation.institution.state == FieldState.PRESENT
                and not affiliation.institution.alternatives,
                "institution_not_unambiguous",
            )
            value, before, leaf = evidence.source_text, affiliation.original_text, "original_text"
        _require(_missing(before), "existing_value_protected")
        _require(
            bool(value.strip()) and not any(ord(c) < 32 and c not in "\n\t\r" for c in value),
            "source_text_invalid",
        )
        path = f"/front/affiliations/{index}/{leaf}"
        # Dedicated typed operation; generic review protections stay unchanged.
        after = SourcedText(
            value=value,
            state=FieldState.PRESENT,
            evidence_ids=(evidence.evidence_id,),
            transformation=operation.operation,
        )
    _require(value_digest(before) == operation.expected_value_sha256, "stale_field")
    return PreparedAutomationOperation(
        operation=operation.operation,
        subject_id=operation.subject_id,
        finding_id=operation.finding_id,
        path=path,
        before_sha256=value_digest(before),
        after_sha256=value_digest(after),
        value=after,
        evidence_id=evidence.evidence_id,
        evidence_sha256=content_digest(evidence),
        authorization_id=evidence.authorization_id,
    )


def evaluate_autocorrection(
    *,
    intent: AutomationIntent,
    article: CanonicalArticle,
    context: AutomationContext,
    evidence: tuple[AutomationEvidence, ...],
    profile: JournalProfile,
    now: datetime,
) -> AutomationDecision:
    """Prepare private operations only; no file/DB/XML writes or network calls.

    Executor must re-check current grants, snapshot, review, limits and this policy
    atomically in VH-09. Eligibility is neither execution nor validator approval.
    """
    # Do not let model_copy/model_construct or mutable nested dictionaries bypass contracts.
    intent = AutomationIntent.model_validate(intent.model_dump(mode="python"))
    context = AutomationContext.model_validate(context.model_dump(mode="python"))
    digest = intent_digest(intent)
    result = dict(scope=context.scope, intent_sha256=digest)
    try:
        _require(now.utcoffset() is not None, "clock_timezone_required")
        _require(context.enabled, "automation_disabled")
        _require(intent.scope == context.scope, "scope_mismatch")
        _require(context.policy_sha256 == policy_digest(), "policy_mismatch")
        _require(content_digest(profile) == PROFILE_SHA256, "profile_mismatch")
        _require(
            content_digest(article) == context.scope.snapshot_sha256
            and article.article_id == context.scope.article_id
            and article.journal_profile_id == context.scope.profile_id,
            "snapshot_mismatch",
        )
        article = CanonicalArticle.model_validate(article.model_dump(mode="python"))
        _require(context.cycle <= context.limits.max_cycles, "cycle_limit")
        _require(len(intent.operations) <= context.limits.max_operations, "operation_limit")
        _require(
            0 <= (now - context.started_at).total_seconds() < context.limits.max_seconds,
            "time_limit",
        )
        _require(context.consumed_tokens < context.limits.max_tokens, "token_limit")
        _require(context.consumed_cost_usd < context.limits.max_cost_usd, "cost_limit")
        _require(context.other_active_executions == 0, "concurrency_limit")
        _require(digest not in context.attempted_intents, "repeated_intent")
        if intent.needs_human:
            return AutomationDecision(**result, disposition="abstained", reason="human_required")
        ids = [f.finding_id for f in context.findings]
        _require(len(ids) == len(set(ids)), "ambiguous_finding")
        items = tuple(
            AutomationEvidence.model_validate(e.model_dump(mode="python")) for e in evidence
        )
        _require(
            len({(e.operation, e.subject_id, e.evidence_id) for e in items}) == len(items),
            "ambiguous_evidence",
        )
        prepared = []
        for op in intent.operations:
            finding = next((f for f in context.findings if f.finding_id == op.finding_id), None)
            _require(finding is not None, "finding_missing")
            assert finding is not None
            _require(
                finding.operation == op.operation and finding.subject_id == op.subject_id,
                "finding_mismatch",
            )
            if (
                finding.requires_human
                or finding.human_decision_present
                or finding.origin != "deterministic-vh1"
            ):
                return AutomationDecision(
                    **result, disposition="abstained", reason="human_or_historical_protection"
                )
            item = next(
                (
                    e
                    for e in items
                    if (e.operation, e.subject_id, e.evidence_id)
                    == (op.operation, op.subject_id, op.evidence_id)
                ),
                None,
            )
            _require(item is not None, "evidence_missing")
            assert item is not None
            _require(
                item.scope == context.scope
                and item.artifact_sha256 == context.scope.source_idml_sha256,
                "evidence_scope_mismatch",
            )
            _require(
                item.status == "active" and item.issued_at <= now < item.expires_at,
                "evidence_expired_or_revoked",
            )
            _require(
                hashlib.sha256(item.source_text.encode()).hexdigest() == item.source_text_sha256,
                "evidence_content_mismatch",
            )
            _require(not contains_policy_override(item.source_text), "source_instruction_detected")
            operation = _prepare(op, article, item, profile)
            _require(
                not any(
                    p in {"", "/"}
                    or operation.path == p
                    or operation.path.startswith(p.rstrip("/") + "/")
                    or p.startswith(operation.path + "/")
                    for p in context.protected_paths
                ),
                "human_path_protected",
            )
            prepared.append(operation)
        _require(len({p.path for p in prepared}) == len(prepared), "conflicting_operations")
        return AutomationDecision(
            **result,
            disposition="eligible_for_candidate",
            reason="closed_policy_passed",
            operations=tuple(prepared),
        )
    except _Refused as exc:
        return AutomationDecision(**result, disposition="refused", reason=str(exc))
    except ValidationError:
        return AutomationDecision(
            **result, disposition="refused", reason="invalid_trusted_evidence"
        )


def decision_event(
    decision: AutomationDecision,
    *,
    now: datetime,
    previous_event_sha256: str | None = None,
) -> AutomationEvent:
    """Redacted event contract; persistence and append-only transaction belong to VH-09."""
    return AutomationEvent(
        scope=decision.scope,
        policy_sha256=policy_digest(),
        intent_sha256=decision.intent_sha256,
        decision_sha256=content_digest(decision),
        state=decision.disposition,
        recorded_at=now,
        previous_event_sha256=previous_event_sha256,
    )
