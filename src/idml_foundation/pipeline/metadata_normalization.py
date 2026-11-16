"""Exact, bounded representation changes; never infer missing editorial values."""

import re

BRAZIL_UFS = frozenset(
    "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split()
)


def split_explicit_brazil_state(city: str, country: str) -> tuple[str, str | None]:
    """Recognize only the qualified City (UF), Brazil/Brasil source notation."""
    match = re.fullmatch(r"([^()]+?)\s+\(([A-Z]{2})\)", city)
    if country in {"Brazil", "Brasil"} and match and match[2] in BRAZIL_UFS:
        return match[1].strip(), match[2]
    return city, None


def normalize_credit_writing_role(role: str) -> str:
    """Known writing labels only; preserve unknown, combined or qualified roles."""
    match = re.fullmatch(
        r"Writing\s*[\-\u2013\u2014]\s*(original draft|review (?:and|&) editing)", role
    )
    if match:
        suffix = "original draft" if match[1] == "original draft" else "review & editing"
        return "Writing \u2013 " + suffix
    return role
