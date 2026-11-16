"""Supplemental public-record diagnostics; never infer authenticated ownership."""

import hashlib
import json
import xml.etree.ElementTree as ET
from typing import Any

from idml_foundation.release.articlemeta_orcids import normalized_name, public_name_matches
from idml_foundation.services.xpm_query_targets import endpoint, plain_name


def identifier(value: str) -> str:
    value = value.strip()
    for prefix in ("https://orcid.org/", "http://orcid.org/"):
        value = value.removeprefix(prefix)
    endpoint("orcid", value)
    return value


def public_name_diagnostic(raw: bytes, orcid: str, name: str) -> str:
    """Classify nonmatches without fuzzy matching, rewriting or identity claims."""
    try:
        if public_name_matches(raw, orcid, name):
            return "exact-public-name-match"
        person = json.loads(raw).get("name")
        if not isinstance(person, dict) or person.get("visibility") != "public":
            return "public-name-unavailable"
        values = {}
        for key in ("given-names", "family-name", "credit-name"):
            field = person.get(key)
            value = field.get("value") if isinstance(field, dict) else None
            values[key] = value.strip() if isinstance(value, str) else ""
        if not values["credit-name"] and not all(
            values[key] for key in ("given-names", "family-name")
        ):
            return "public-name-incomplete"
        return "public-name-not-exact"
    except (ValueError, TypeError, AttributeError):
        return "public-record-invalid"


def crossref_author_links(root: ET.Element, message: dict[str, Any]) -> list[dict[str, str]]:
    """Called only after DOI/ISSN/titles/ordered roster have been verified.

    Missing deposit identifiers are not discrepancies. Present contradictory or
    malformed identifiers are. Neither a link nor a deposit authentication flag
    establishes authenticated ownership in this application.
    """
    authors = root.findall("front/article-meta/contrib-group/contrib[@contrib-type='author']")
    names = [normalized_name(plain_name(n)) for n in authors]
    deposits = message["author"]
    if len(authors) != len(deposits):
        raise ValueError("crossref_roster_mismatch")
    result = []
    for node, name, deposit in zip(authors, names, deposits, strict=True):
        ids = node.findall("contrib-id[@contrib-id-type='orcid']")
        if not ids:
            continue
        orcid = identifier(ids[0].text or "")
        state, reason = "matched", "exact-deposited-author-orcid-link"
        value = deposit.get("ORCID")
        if names.count(name) != 1:
            state, reason = "unavailable", "ambiguous-author-name"
        elif value is None or value == "":
            state, reason = "not-deposited", "author-orcid-not-deposited"
        else:
            try:
                if not isinstance(value, str) or identifier(value) != orcid:
                    state, reason = "conflict", "deposited-author-orcid-mismatch"
            except ValueError:
                state, reason = "conflict", "deposited-author-orcid-invalid"
        result.append(
            dict(
                identifier_sha256=hashlib.sha256(orcid.encode()).hexdigest(),
                status=state,
                reason=reason,
            )
        )
    return result
