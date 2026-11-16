"""Exact IDML extraction for VH-09. Inputs here are server-owned, never model output."""

import hashlib
import re
from datetime import datetime, timedelta
from io import BytesIO
from typing import Literal, Self
from uuid import UUID
from zipfile import ZipFile

from lxml import etree
from pydantic import AwareDatetime, model_validator

from idml_foundation.ai.autocorrection_contracts import (
    AutomationEvidence,
    AutomationOperation,
    AutomationScope,
    Digest,
    Identifier,
    Operation,
)
from idml_foundation.domain.canonical import CanonicalArticle
from idml_foundation.domain.common import EvidenceLocator, StrictModel, content_digest
from idml_foundation.ingest.safe_zip import inspect_idml
from idml_foundation.ingest.xml_security import parse_untrusted_xml
from idml_foundation.settings import Settings


class ExtractionGrant(StrictModel):
    """Operator-recorded binding of one existing field evidence to one exact extraction.

    Stored by trusted administration only. A hash is integrity, not authentication.
    No caller-provided replacement text, XPath, filesystem path, or URL is evaluated.
    """

    version: Literal["autocorrection-extraction-grant-1.0"] = "autocorrection-extraction-grant-1.0"
    authorization_id: UUID
    decision_sha256: Digest
    scope: AutomationScope
    operation: Operation
    subject_id: Identifier
    evidence_id: Identifier
    locator: EvidenceLocator
    source_text_sha256: Digest
    collected_at: AwareDatetime
    issued_at: AwareDatetime
    expires_at: AwareDatetime
    parent_authorization_id: UUID | None = None
    parent_authorization_sha256: Digest | None = None
    catalog_sha256: Digest | None = None

    @model_validator(mode="after")
    def bounded_source(self) -> Self:
        parent = (
            self.parent_authorization_id,
            self.parent_authorization_sha256,
            self.catalog_sha256,
        )
        if any(item is not None for item in parent) and not all(
            item is not None for item in parent
        ):
            raise ValueError("extraction_parent_authorization_incomplete")
        if not self.collected_at <= self.issued_at < self.expires_at:
            raise ValueError("extraction_grant_dates_invalid")
        if self.expires_at - self.collected_at > timedelta(days=30):
            raise ValueError("extraction_grant_too_long")
        if self.locator.artifact_sha256 != self.scope.source_idml_sha256:
            raise ValueError("extraction_grant_source_mismatch")
        return self


class SourceResolutionError(ValueError):
    """Only fixed public codes, never paths, source text or parser exception messages."""


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise SourceResolutionError(code)


def _literal_text(element: etree._Element) -> str:
    # A deliberately narrow extraction grammar: do not silently omit tables, notes,
    # inline objects or special characters from a broader story selection.
    tag = etree.QName(element).localname if isinstance(element.tag, str) else ""
    _require(not element.tail or not element.tail.strip(), "unsupported_idml_text")
    if tag == "Content":
        _require(len(element) == 0, "unsupported_idml_text")
        return element.text or ""
    if tag == "Br":
        _require(len(element) == 0 and not element.text, "unsupported_idml_text")
        return "\n"
    _require(
        tag in {"Story", "ParagraphStyleRange", "CharacterStyleRange"}
        and (not element.text or not element.text.strip()),
        "unsupported_idml_text",
    )
    return "".join(_literal_text(child) for child in element)


def source_element(root: etree._Element, element_id: str | None) -> etree._Element:
    """Resolve Self or the exact virtual paragraph locator emitted by IdmlParser.

    The ordinal is source structure, not fuzzy text matching. Collisions between a
    real Self and a virtual locator, duplicate stories and out-of-range ordinals fail.
    """
    _require(bool(element_id), "extraction_element_required")
    direct = [e for e in root.iter() if e.get("Self") == element_id]
    virtual = []
    match = re.fullmatch(r"(.+):paragraph:(0|[1-9][0-9]*)", element_id or "")
    if match:
        stories = [e for e in root.iter() if e.get("Self") == match[1]]
        _require(len(stories) == 1, "extraction_element_not_unique")
        _require(etree.QName(stories[0]).localname == "Story", "extraction_element_not_unique")
        paragraphs = [
            e
            for e in stories[0].iter()
            if isinstance(e.tag, str) and etree.QName(e).localname == "ParagraphStyleRange"
        ]
        ordinal = int(match[2])
        _require(ordinal < len(paragraphs), "extraction_element_not_unique")
        virtual = [paragraphs[ordinal]]
    _require(len(direct) + len(virtual) == 1, "extraction_element_not_unique")
    return (direct + virtual)[0]


def resolve_idml_evidence(
    *,
    article: CanonicalArticle,
    operation: AutomationOperation,
    scope: AutomationScope,
    grant: ExtractionGrant,
    idml: bytes,
    assets: dict[str, bytes],
    settings: Settings,
    now: datetime,
) -> AutomationEvidence:
    """Read only selected ZIP members; no extraction to disk and no network access.

    `assets` maps canonical asset IDs to hash-checked bytes from tenant storage.
    Revocation and the authenticity of the stored grant are checked by the executor.
    """
    grant = ExtractionGrant.model_validate(grant.model_dump(mode="python"))
    _require(now.utcoffset() is not None, "clock_timezone_required")
    _require(grant.scope == scope, "extraction_scope_mismatch")
    _require(
        (grant.operation, grant.subject_id, grant.evidence_id)
        == (operation.operation, operation.subject_id, operation.evidence_id),
        "extraction_operation_mismatch",
    )
    _require(grant.issued_at <= now < grant.expires_at, "extraction_grant_expired")
    _require(hashlib.sha256(idml).hexdigest() == scope.source_idml_sha256, "idml_hash_mismatch")
    matches = [e for e in article.evidence if e.id == operation.evidence_id]
    _require(len(matches) == 1, "extraction_evidence_missing")
    evidence = matches[0]
    _require(
        evidence.source_kind == "idml"
        and evidence.locator == grant.locator
        and evidence.content_sha256 == grant.source_text_sha256,
        "extraction_binding_mismatch",
    )
    locator = evidence.locator
    _require(bool(locator.element_id), "extraction_element_required")
    try:
        inspect_idml(idml, settings)
        with ZipFile(BytesIO(idml)) as archive:
            member = archive.read(locator.logical_path)
        root = parse_untrusted_xml(member)
    except (ValueError, KeyError, OSError) as exc:
        raise SourceResolutionError("idml_extraction_unavailable") from exc
    element = source_element(root, locator.element_id)
    target_sha = None
    if operation.operation == "figure-asset-exact":
        _require(
            etree.QName(element).localname == "Link"
            and locator.start_offset is None
            and locator.end_offset is None,
            "unsupported_idml_link",
        )
        text = element.get("LinkResourceURI", "")
        _require(
            bool(text) and text not in {".", ".."} and not any(c in text for c in "/\\:"),
            "unsupported_idml_link",
        )
        targets = [a for a in article.assets if a.logical_name == text]
        _require(len(targets) == 1, "asset_target_not_unique")
        target = targets[0]
        payload = assets.get(target.id)
        _require(payload is not None, "asset_bytes_missing")
        assert payload is not None
        target_sha = hashlib.sha256(payload).hexdigest()
        _require(target.sha256 == target_sha, "asset_bytes_mismatch")
    else:
        text = _literal_text(element)
        if locator.start_offset is not None or locator.end_offset is not None:
            _require(
                locator.start_offset is not None
                and locator.end_offset is not None
                and 0 <= locator.start_offset < locator.end_offset <= len(text),
                "extraction_offsets_invalid",
            )
            text = text[locator.start_offset : locator.end_offset]
    _require(0 < len(text) <= 4096, "extraction_text_size_invalid")
    digest = hashlib.sha256(text.encode()).hexdigest()
    _require(digest == grant.source_text_sha256, "extraction_text_mismatch")
    return AutomationEvidence(
        version="autocorrection-evidence-1.0",
        scope=scope,
        evidence_id=operation.evidence_id,
        operation=operation.operation,
        subject_id=operation.subject_id,
        source_kind="idml",
        artifact_sha256=scope.source_idml_sha256,
        source_text=text,
        source_text_sha256=digest,
        extraction_sha256=content_digest(
            {
                "version": "idml-literal-extraction-1.0",
                "grant_sha256": content_digest(grant),
                "member_sha256": hashlib.sha256(member).hexdigest(),
                "locator": locator.model_dump(mode="json"),
                "text_sha256": digest,
                "target_asset_sha256": target_sha,
            }
        ),
        authorization_id=grant.authorization_id,
        authorization_decision_sha256=grant.decision_sha256,
        status="active",
        collected_at=grant.collected_at,
        issued_at=grant.issued_at,
        expires_at=grant.expires_at,
        target_asset_sha256=target_sha,
    )
