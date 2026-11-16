"""Conservative, literal ESA bibliography patterns; no network or inferred values."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

ReferenceType = Literal["journal", "book", "thesis", "other"]
_PUBLICATION = re.compile(
    r",\s+((?:19|20)\d{2})\.(?=\s*(?:https?://|Available at:|Accessed on:|p\.|$))", re.I
)
_ACCESS = re.compile(r"Accessed on:\s*(.+?)\.?\s*$", re.I)
_DATE = re.compile(r"([A-Za-z]+)\.?\s+(\d{1,2}),\s*(\d{4})")
_MONTHS = {
    name: number
    for number, names in enumerate(
        (
            "jan january",
            "feb february",
            "mar march",
            "apr april",
            "may",
            "jun june",
            "jul july",
            "aug august",
            "sep sept september",
            "oct october",
            "nov november",
            "dec december",
        ),
        1,
    )
    for name in names.split()
}


@dataclass(frozen=True)
class ReferenceMetadata:
    publication_type: ReferenceType
    fields: dict[str, str] = field(default_factory=dict)
    editors: tuple[str, ...] = ()
    review_reasons: tuple[str, ...] = ()


def access_date(value: str) -> tuple[str | None, tuple[str, ...]]:
    """Return the literal access label/date only when unique and calendar-valid."""
    if not re.search(r"Accessed on:", value, re.I):
        return None, ()
    match = _ACCESS.search(value)
    if len(re.findall(r"Accessed on:", value, re.I)) != 1 or match is None:
        return None, ("ambiguous_reference_access_date",)
    parsed = _DATE.fullmatch(match.group(1))
    if parsed is None:
        return None, ("unsupported_reference_access_date",)
    try:
        date(int(parsed[3]), _MONTHS[parsed[1].lower()], int(parsed[2]))
    except (KeyError, ValueError):
        return None, ("invalid_reference_access_date",)
    return value[match.start() : match.end()].rstrip().removesuffix("."), ()


def reference_metadata(value: str, title: str | None, source: str | None) -> ReferenceMetadata:
    """Unknown types retain source fields and a reason, not a fictitious journal type."""
    fields: dict[str, str] = {}
    accessed, reasons = access_date(value)
    if accessed:
        fields["access_date"] = accessed
    publication = _PUBLICATION.search(value)
    if publication:
        fields["year"] = publication[1]
    if not (title and source and publication):
        return ReferenceMetadata(
            "other", fields, review_reasons=(*reasons, "reference_type_unresolved")
        )
    thesis = re.fullmatch(
        r"(Doctoral \(dissertation\)|Master.?s? \(dissertation\))"
        r"\s+[\u2013\u2014-]\s+(.+),\s+([^,]+)",
        source,
        re.I,
    )
    if thesis:
        fields.update(
            source=title,
            title="",
            publisher_name=thesis[2],
            publisher_location=thesis[3],
            publication_description=thesis[1],
        )
        return ReferenceMetadata("thesis", fields, review_reasons=reasons)
    chapter = re.fullmatch(r"(.+)\. In:\s+(.+?)\s+\((Org\.|Eds?\.)\)\.\s+(.+)", title, re.I)
    publisher = re.fullmatch(r"([^:]+):\s+(.+)", source)
    if chapter:
        fields.update(title="", part_title=chapter[1], source=chapter[4])
        if publisher:
            fields.update(publisher_location=publisher[1], publisher_name=publisher[2])
        else:
            fields["publisher_name"] = source
        pages = re.fullmatch(
            r"\s*p\.\s*(\d+)\s*[-\u2013]\s*(\d+)\.?\s*", value[publication.end() :]
        )
        if pages:
            fields.update(first_page=pages[1], last_page=pages[2])
        editors = tuple(item.strip() for item in chapter[2].split(";") if item.strip())
        # SPS 1.10 requires author for collab; keep institutional organizer literal.
        if any("," not in editor for editor in editors):
            fields["publication_description"] = title[chapter.start(2) : chapter.end(3) + 1]
            editors = ()
        return ReferenceMetadata("book", fields, editors, reasons)
    if publisher and not re.search(r",\s*(?:v|n|p)\.\s*", value[: publication.start()]):
        edition = re.fullmatch(r"(.+)\.\s+(\d+(?:st|nd|rd|th|\.)?\s+ed\.?)", title, re.I)
        fields.update(
            title="",
            source=edition[1] if edition else title,
            publisher_location=publisher[1],
            publisher_name=publisher[2],
        )
        if edition:
            fields["edition"] = edition[2]
        return ReferenceMetadata("book", fields, review_reasons=reasons)
    serial = value[: publication.start()]
    if re.search(r",\s+(?:v|n)\.\s*\d", serial) or (
        publisher is None and re.search(r",\s+p\.\s*\d", serial)
    ):
        return ReferenceMetadata("journal", fields, review_reasons=reasons)
    return ReferenceMetadata(
        "other", fields, review_reasons=(*reasons, "reference_type_unresolved")
    )
