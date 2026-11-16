"""Literal boundaries for ESA references without a volume, not a citation database."""

from __future__ import annotations

import re


def reference_without_volume(value: str) -> tuple[tuple[str, ...], str | None, str | None]:
    """Keep access metadata and extent labels out of title/container extraction.

    The source citation remains authoritative and unchanged. This helper handles
    the existing dot-separated ESA layout; it neither classifies publication type
    nor invents missing fields or expands author initials.
    """
    publication = re.search(
        r",\s+(?:19|20)\d{2}\.(?=\s*(?:https?://|Available at:|Accessed on:|p\.|$))",
        value,
        re.IGNORECASE,
    )
    if publication is None:
        return (), None, None
    core = value[: publication.start()]
    extent = re.search(r",\s+(?:n|p)\.\s*", core)
    if extent is not None:
        core = core[: extent.start()]
    prefix, separator, source = core.rpartition(". ")
    if not separator or not source.strip():
        return (), None, None
    # Look from the start: semicolons in a title or a chapter's editor list must
    # not move the author/title boundary. A run of initials belongs to the author.
    for boundary in re.finditer(r"\.\s+", prefix):
        author = prefix[: boundary.start()]
        last_token = author.rsplit(maxsplit=1)[-1] if author.strip() else ""
        initial = len(last_token) == 1 and last_token.isalpha()
        remainder = prefix[boundary.end() :]
        if initial and re.match(r"[^\W\d_]\.(?:\s|;)", remainder):
            continue
        if not author.strip() or not remainder.strip():
            break
        if initial:
            author += "."
        authors = tuple(item.strip() for item in author.split(";") if item.strip())
        return authors, remainder.strip(), source.strip()
    return (), None, source.strip()
