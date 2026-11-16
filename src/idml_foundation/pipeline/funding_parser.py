"""Parse explicit single-funder declarations; comma-separated prose is not a registry."""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ParsedFunding:
    agency: str | None = None
    award: str | None = None
    explicit_none: bool = False


def parse_funding(value: str) -> ParsedFunding:
    if re.fullmatch(r"none\.?", value, re.IGNORECASE):
        return ParsedFunding(explicit_none=True)
    # Explicitly labeled fields preserve commas and conjunctions in institution names.
    # No guessed segmentation of free prose or duplication of a grant across funders.
    match = re.fullmatch(
        r"Funder:\s*([^;\n]+?);\s*Award:\s*#?([A-Za-z0-9][A-Za-z0-9./-]*[A-Za-z0-9]|[0-9])\.?",
        value,
        re.IGNORECASE,
    )
    if match:
        return ParsedFunding(match[1].strip(), match[2])
    match = re.fullmatch(
        r"([^,;\n]+?),\s*grant(?:\s+number)?\s+#?"
        r"([A-Za-z0-9][A-Za-z0-9./-]*[A-Za-z0-9]|[0-9])\.?",
        value,
        re.IGNORECASE,
    )
    if match and not re.search(r"\band\b|&", match[1], re.IGNORECASE):
        return ParsedFunding(match[1].strip(), match[2])
    return ParsedFunding()
