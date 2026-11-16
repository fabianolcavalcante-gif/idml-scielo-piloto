"""Lossless rendering of a narrowly qualified, explicit institutional hierarchy."""

import hashlib
import re

from idml_foundation.domain.canonical import Affiliation, FieldState
from idml_foundation.domain.common import Evidence

_TWO_LEVELS = re.compile(
    r"(?P<first>Graduate School of [^,;\r\n]+), (?P<second>Department of [^,;\r\n]+)"
)


def institution_divisions(
    affiliation: Affiliation, evidence: tuple[Evidence, ...] = ()
) -> tuple[str, ...]:
    """Keep the canonical source intact; never infer a missing organizational unit.

    The canonical department field retains the literal subdivision phrase. Only
    the qualified School -> Department syntax is rendered as two JATS nodes.
    Other syntax, edited/ambiguous data and unrelated evidence remain unsplit.
    """
    department = affiliation.department
    if department is None or not department.value:
        return ()
    original = affiliation.original_text
    institution = affiliation.institution
    fallback = (department.value,)
    if original is None or not original.value or not institution.value:
        return fallback
    fields = (department, original, institution)
    if any(f.state != FieldState.PRESENT or f.alternatives for f in fields):
        return fallback
    shared = set(department.evidence_ids).intersection(
        institution.evidence_ids, affiliation.evidence_ids
    )
    if (
        department.transformation != "deterministic-affiliation-decomposition"
        or institution.transformation != "deterministic-affiliation-decomposition"
    ):
        return fallback
    if original.transformation == "affiliation-original-literal":
        # Automation records the exact substring as a new evidence object. Its
        # parent must be the same source paragraph used to decompose both units.
        parents = [e.locator for e in evidence if e.id in shared and e.source_kind == "idml"]
        matches = [
            e
            for e in evidence
            if e.id in original.evidence_ids
            and e.id in affiliation.evidence_ids
            and e.source_kind == "idml"
            and e.content_sha256 == hashlib.sha256(original.value.encode()).hexdigest()
            and e.locator.start_offset is not None
            and e.locator.end_offset == e.locator.start_offset + len(original.value)
            and e.locator.model_copy(update={"start_offset": None, "end_offset": None}) in parents
        ]
        if len(matches) != 1:
            return fallback
    elif original.transformation != "line-from-affiliation-style" or not shared.intersection(
        original.evidence_ids
    ):
        return fallback
    match = _TWO_LEVELS.fullmatch(department.value)
    if match is None:
        return fallback
    prefix = institution.value + ", " + department.value
    if not any(
        original.value.startswith(prefix + " " + dash + " ") for dash in ("\u2013", "\u2014")
    ):
        return fallback
    divisions = (match["first"], match["second"])
    return divisions if ", ".join(divisions) == department.value else fallback
