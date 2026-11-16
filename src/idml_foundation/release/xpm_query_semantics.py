"""Verify selected public responses; not all XPM queries or authenticated ownership."""

import hashlib
import json
from datetime import datetime, timedelta
from typing import Any, Literal

from pydantic import AwareDatetime, Field

from idml_foundation.domain.common import SHA256_PATTERN, StrictModel
from idml_foundation.release.articlemeta_orcids import normalized_name
from idml_foundation.release.doi_snapshot import bind_doi_snapshot
from idml_foundation.release.orcid_query_diagnostics import (
    crossref_author_links,
    public_name_diagnostic,
)
from idml_foundation.services.validation_scope import validate_scope
from idml_foundation.services.xpm_query_targets import (
    endpoint,
    parse_candidate,
    plain_name,
    query_targets,
)


class QueryReceipt(StrictModel):
    kind: Literal["crossref", "orcid"]
    identifier: str = Field(min_length=1, max_length=220)
    url: str = Field(max_length=512)
    status: Literal["available", "unavailable"]
    retrieved_at: AwareDatetime
    response_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    payload: str | None = Field(default=None, max_length=1024**2)


class QueryEvidence(StrictModel):
    version: Literal["xpm-query-evidence-1.0"]
    scope: dict[str, str]
    report_sha256: str = Field(pattern=SHA256_PATTERN)
    receipts: tuple[QueryReceipt, ...] = Field(max_length=17)


def assess_queries(
    *, xml: bytes, evidence: QueryEvidence, scope: dict[str, str], report_sha256: str, now: datetime
) -> dict[str, Any]:
    evidence = QueryEvidence.model_validate(evidence.model_dump(mode="python", warnings=False))
    if (
        validate_scope(evidence.scope) != validate_scope(scope)
        or evidence.report_sha256 != report_sha256
        or hashlib.sha256(xml).hexdigest() != scope["xml_sha256"]
        or now.utcoffset() is None
    ):
        raise ValueError("query_evidence_binding_mismatch")
    targets = query_targets(xml)
    expected = {(t["kind"], t["identifier"]): t for t in targets}
    actual = {(r.kind, r.identifier) for r in evidence.receipts}
    if actual != set(expected) or len(actual) != len(evidence.receipts):
        raise ValueError("query_evidence_set_mismatch")
    if sum(len((r.payload or "").encode()) for r in evidence.receipts) > 2 * 1024**2:
        raise ValueError("query_evidence_budget")
    root = parse_candidate(xml)
    checks = []
    links: list[dict[str, str]] = []
    link_source = None
    for receipt in evidence.receipts:
        public_name_check = None
        host, path = endpoint(receipt.kind, receipt.identifier)
        if receipt.url != "https://" + host + path:
            raise ValueError("query_evidence_origin_mismatch")
        if not timedelta(0) <= now - receipt.retrieved_at <= timedelta(hours=24):
            raise ValueError("query_evidence_expired")
        if receipt.status == "unavailable":
            if receipt.payload is not None or receipt.response_sha256 is not None:
                raise ValueError("query_evidence_unavailable_with_payload")
            state, reason = "unavailable", "authority-unavailable"
        else:
            if (
                receipt.payload is None
                or receipt.response_sha256 != hashlib.sha256(receipt.payload.encode()).hexdigest()
            ):
                raise ValueError("query_evidence_payload_mismatch")
            raw = receipt.payload.encode()
            state, reason = "matched", "exact-public-record-match"
            try:
                if receipt.kind == "crossref":
                    bound = bind_doi_snapshot(
                        candidate=xml,
                        snapshot=raw,
                        expected_candidate_sha256=scope["xml_sha256"],
                        expected_snapshot_sha256=receipt.response_sha256,
                        retrieved_at=receipt.retrieved_at,
                        now=now,
                    )
                    message = json.loads(bound.payload)["message"]
                    for field, xpath in (
                        ("title", "front/article-meta/title-group/article-title"),
                        ("container-title", "front/journal-meta/journal-title-group/journal-title"),
                    ):
                        nodes = root.findall(xpath)
                        values = message.get(field)
                        if (
                            len(nodes) != 1
                            or not isinstance(values, list)
                            or len(values) != 1
                            or not isinstance(values[0], str)
                            or not values[0].strip()
                            or " ".join("".join(nodes[0].itertext()).split())
                            != " ".join(values[0].split())
                        ):
                            raise ValueError("crossref_titles_mismatch")
                    names = [
                        normalized_name(plain_name(n))
                        for n in root.findall(
                            "front/article-meta/contrib-group/contrib[@contrib-type='author']"
                        )
                    ]
                    authors = message.get("author")
                    if not isinstance(authors, list) or not names or len(authors) != len(names):
                        raise ValueError("crossref_roster_mismatch")
                    authority_names = []
                    for author in authors:
                        if (
                            not isinstance(author, dict)
                            or not isinstance(author.get("given"), str)
                            or not isinstance(author.get("family"), str)
                        ):
                            raise ValueError("crossref_roster_shape")
                        authority_names.append(
                            normalized_name(author["given"] + " " + author["family"])
                        )
                    if authority_names != names:
                        raise ValueError("crossref_roster_mismatch")
                    links = crossref_author_links(root, message)
                    link_source = receipt.response_sha256
                else:
                    name = expected[(receipt.kind, receipt.identifier)]["name"]
                    public_name_check = public_name_diagnostic(raw, receipt.identifier, name)
                    if public_name_check != "exact-public-name-match":
                        raise ValueError("orcid_public_name_mismatch")
            except (ValueError, TypeError, KeyError):
                state, reason = "conflict", "authority-response-does-not-match"
        checks.append(
            dict(
                kind=receipt.kind,
                identifier_sha256=hashlib.sha256(receipt.identifier.encode()).hexdigest(),
                status=state,
                reason=reason,
                response_sha256=receipt.response_sha256,
            )
        )
        if receipt.kind == "orcid":
            checks[-1]["public_name_check"] = public_name_check or "public-name-unavailable"
    return dict(
        version="xpm-selected-query-assessment-1.0",
        checks=checks,
        crossref_author_links={
            "version": "orcid-deposit-diagnostic-1.0",
            "status": "assessed" if link_source is not None else "unavailable",
            "response_sha256": link_source,
            "checks": links,
            "authenticated_ownership": False,
        },
        selected_checks_matched=all(c["status"] == "matched" for c in checks)
        and all(c["status"] in {"matched", "not-deposited"} for c in links),
        required_queries_complete=False,
        authenticated_orcid_ownership=False,
    )
