"""Publication precision is evidence: never complete a partial date by guessing."""

import re
from datetime import date


def publication_parts(value: str) -> tuple[int, ...]:
    if not re.fullmatch(r"(?:19|20)\d{2}(?:-\d{2}(?:-\d{2})?)?", value):
        raise ValueError("invalid publication date format")
    parts = tuple(int(part) for part in value.split("-"))
    date(*((*parts, 1, 1)[:3]))
    return parts


def refines_publication_date(current: str, proposed: str) -> bool:
    """Equal or greater precision, with every already known part unchanged."""
    old, new = publication_parts(current), publication_parts(proposed)
    return len(new) >= len(old) and new[: len(old)] == old
