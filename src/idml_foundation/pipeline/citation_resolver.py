from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import pairwise

from idml_foundation.domain.canonical import (
    CrossReference,
    InlineKind,
    InlineNode,
    Reference,
    RichText,
)
from idml_foundation.domain.common import stable_id
from idml_foundation.pipeline.vancouver import numeric_citation_spans, reference_label

_YEAR = re.compile(r"(?<!\d)((?:18|19|20)\d{2}[a-z]?)(?!\d)", re.IGNORECASE)
_PERSONAL_AUTHOR = re.compile(r"(?:^|;\s*)([^,;]{1,80})(?:,\s|(?=;))")
_GROUP_PREFIX = re.compile(r"^([A-ZÀ-ÖØ-Þ][A-ZÀ-ÖØ-Þ0-9 &'\-]+?)(?:\s*\(([A-Z0-9]{2,})\))?\.\s")
_UNRESOLVED_CANDIDATE = re.compile(
    r"(?<!\w)(?:[A-ZÀ-ÖØ-Þ][A-ZÀ-ÖØ-Þ'\-]+(?:\s+et\s+al\.?|"
    r"(?:\s*;\s*[A-ZÀ-ÖØ-Þ][A-ZÀ-ÖØ-Þ'\-]+){1,2}))"
    r"\s*,\s*((?:18|19|20)\d{2}[a-z]?)(?!\w)",
)


@dataclass(frozen=True)
class ReferenceSignature:
    target_id: str
    authors: tuple[str, ...]
    year: str


@dataclass(frozen=True)
class CitationMatch:
    start: int
    end: int
    target_id: str


@dataclass(frozen=True)
class CitationResolution:
    content: RichText
    cross_references: tuple[CrossReference, ...]
    review_reasons: tuple[str, ...]


def _reference_signature(reference: Reference) -> ReferenceSignature | None:
    text = reference.mixed_citation.plain.value or ""
    publication_part = re.split(
        r"\b(?:Available\s+at|Accessed\s+on)\s*:|https?://",
        text,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    year_matches = tuple(_YEAR.finditer(publication_part))
    if not year_matches:
        return None
    year_match = year_matches[-1]
    author_part = re.split(r"\bIn\s*:", text, maxsplit=1, flags=re.IGNORECASE)[0]
    authors = tuple(
        candidate
        for match in _PERSONAL_AUTHOR.finditer(author_part)
        if (candidate := " ".join(match.group(1).split()))
        and all(not character.isalpha() or character.isupper() for character in candidate)
    )
    if not authors:
        group = _GROUP_PREFIX.match(text)
        if group is not None:
            authors = (group.group(2) or " ".join(group.group(1).split()),)
    if not authors:
        return None
    return ReferenceSignature(
        target_id=reference.id,
        authors=authors,
        year=year_match.group(1),
    )


def reference_signatures(references: tuple[Reference, ...]) -> tuple[ReferenceSignature, ...]:
    return tuple(
        signature
        for reference in references
        if (signature := _reference_signature(reference)) is not None
    )


def _name(name: str) -> str:
    words = [re.escape(part) for part in name.split()]
    return r"\s+".join(words)


def _citation_patterns(signature: ReferenceSignature) -> tuple[tuple[re.Pattern[str], str], ...]:
    authors = tuple(_name(author) for author in signature.authors)
    year = re.escape(signature.year)
    if len(authors) == 1:
        parenthetical = rf"{authors[0]}\s*,\s*{year}"
        narrative = rf"{authors[0]}\s*\(\s*(?P<year>{year})\s*\)"
    elif len(authors) == 2:
        parenthetical = rf"{authors[0]}\s*(?:;|&|\band\b|\be\b)\s*{authors[1]}\s*,\s*{year}"
        narrative = (
            rf"{authors[0]}\s+(?:and|e|&)\s+{authors[1]}"
            rf"\s*\(\s*(?P<year>{year})\s*\)"
        )
    elif len(authors) == 3:
        parenthetical = (
            rf"{authors[0]}\s*[;,]\s*{authors[1]}\s*(?:;|,|&|\band\b|\be\b)\s*"
            rf"{authors[2]}\s*,\s*{year}"
        )
        narrative = (
            rf"{authors[0]}\s*,\s*{authors[1]}\s+(?:and|e|&)\s+{authors[2]}"
            rf"\s*\(\s*(?P<year>{year})\s*\)"
        )
    else:
        parenthetical = rf"{authors[0]}\s+et\s+al\.?\s*,\s*{year}"
        narrative = rf"{authors[0]}\s+et\s+al\.?\s*\(\s*(?P<year>{year})\s*\)"
    flags = re.IGNORECASE
    patterns = [
        (re.compile(rf"(?<!\w){parenthetical}(?!\w)", flags), "full"),
        (re.compile(rf"(?<!\w){narrative}(?!\w)", flags), "year"),
    ]
    if len(authors) == 3:
        patterns.extend(
            (
                (
                    re.compile(
                        rf"(?<!\w){authors[0]}\s+et\s+al\.?\s*,\s*{year}(?!\w)",
                        flags,
                    ),
                    "full",
                ),
                (
                    re.compile(
                        rf"(?<!\w){authors[0]}\s+et\s+al\.?\s*"
                        rf"\(\s*(?P<year>{year})\s*\)(?!\w)",
                        flags,
                    ),
                    "year",
                ),
            )
        )
    return tuple(patterns)


def find_citations(
    text: str,
    references: tuple[Reference, ...],
) -> tuple[tuple[CitationMatch, ...], tuple[tuple[int, int], ...]]:
    candidates: dict[tuple[int, int], set[str]] = {}
    for signature in reference_signatures(references):
        for pattern, span_kind in _citation_patterns(signature):
            for found in pattern.finditer(text):
                span = found.span("year") if span_kind == "year" else found.span()
                candidates.setdefault(span, set()).add(signature.target_id)

    ambiguous = tuple(sorted(span for span, targets in candidates.items() if len(targets) > 1))
    resolved = [
        CitationMatch(start=span[0], end=span[1], target_id=next(iter(targets)))
        for span, targets in candidates.items()
        if len(targets) == 1
    ]
    resolved.sort(key=lambda item: (item.start, -(item.end - item.start), item.target_id))

    selected: list[CitationMatch] = []
    for match in resolved:
        if any(match.start < item.end and item.start < match.end for item in selected):
            continue
        selected.append(match)
    return tuple(selected), ambiguous


def _slice_inlines(
    rich_text: RichText,
    article_id: str,
    paragraph_id: str,
    matches: tuple[CitationMatch, ...],
) -> tuple[InlineNode, ...]:
    source = rich_text.inlines or (
        InlineNode(
            id=stable_id(article_id, "inline", f"{paragraph_id}:source"),
            kind=InlineKind.TEXT,
            text=rich_text.plain.value or "",
            evidence_ids=rich_text.plain.evidence_ids,
        ),
    )
    if not matches:
        return source
    boundaries = {0, len(rich_text.plain.value or "")}
    for match in matches:
        boundaries.update((match.start, match.end))
    offsets: list[tuple[int, int, InlineNode]] = []
    cursor = 0
    for inline in source:
        end = cursor + len(inline.text)
        offsets.append((cursor, end, inline))
        boundaries.update((cursor, end))
        cursor = end

    pieces: list[InlineNode] = []
    sorted_boundaries = sorted(boundaries)
    for start, end in pairwise(sorted_boundaries):
        if start == end:
            continue
        covering_match = next(
            (item for item in matches if item.start <= start and end <= item.end), None
        )
        if covering_match is not None:
            if start != covering_match.start:
                continue
            evidence_ids = tuple(
                dict.fromkeys(
                    evidence_id
                    for source_start, source_end, inline in offsets
                    if source_start < covering_match.end and covering_match.start < source_end
                    for evidence_id in inline.evidence_ids
                )
            )
            pieces.append(
                InlineNode(
                    id=stable_id(
                        article_id,
                        "inline",
                        f"{paragraph_id}:citation:{covering_match.start}:"
                        f"{covering_match.end}:{covering_match.target_id}",
                    ),
                    kind=InlineKind.CROSS_REFERENCE,
                    text=(rich_text.plain.value or "")[covering_match.start : covering_match.end],
                    target_id=covering_match.target_id,
                    attributes={"ref-type": "bibr"},
                    evidence_ids=evidence_ids,
                )
            )
            continue
        source_item = next(
            inline
            for source_start, source_end, inline in offsets
            if source_start <= start and end <= source_end
        )
        pieces.append(
            InlineNode(
                id=stable_id(
                    article_id,
                    "inline",
                    f"{paragraph_id}:text:{start}:{end}:{source_item.kind.value}",
                ),
                kind=source_item.kind,
                text=(rich_text.plain.value or "")[start:end],
                href=source_item.href,
                name=source_item.name,
                attributes=source_item.attributes,
                evidence_ids=source_item.evidence_ids,
            )
        )
    return tuple(pieces)


def _numeric_matches(
    rich_text: RichText, references: tuple[Reference, ...]
) -> tuple[CitationMatch, ...]:
    """Superscript '1', '2,3', '4-6' -> citations of the references labelled with those numbers.

    Active only when most references carry numeric labels (Vancouver lists). Superscripts
    on a power of ten (10^6) or after a word of at most two letters (R^2, m^2) are
    exponents or units, not citations.
    """
    labels = {
        number: reference.id
        for reference in references
        if (number := reference_label(reference.mixed_citation.plain.value or "")) is not None
    }
    if not references or len(labels) * 2 < len(references):
        return ()
    plain = rich_text.plain.value or ""
    found: list[CitationMatch] = []
    cursor = 0
    for inline in rich_text.inlines:
        start = cursor
        cursor += len(inline.text)
        if inline.kind != InlineKind.SUPERSCRIPT:
            continue
        spans = numeric_citation_spans(inline.text)
        if not spans:
            continue
        before = plain[:start].rstrip(" ")
        last_word = re.search(r"([^\W\d_]+)$", before)
        power_of_ten = re.search(r"(?:^|[^\d])10$", before) is not None
        short_symbol = last_word is not None and len(last_word.group(1)) <= 2
        if power_of_ten or short_symbol:
            continue
        found.extend(
            CitationMatch(start=start + first, end=start + last, target_id=labels[number])
            for first, last, number in spans
            if number in labels
        )
    return tuple(found)


def resolve_citations(
    rich_text: RichText,
    references: tuple[Reference, ...],
    *,
    article_id: str,
    paragraph_id: str,
) -> CitationResolution:
    text = rich_text.plain.value or ""
    matches, ambiguous = find_citations(text, references)
    numeric = _numeric_matches(rich_text, references)
    if numeric:
        matches = tuple(
            sorted(
                (
                    *numeric,
                    *(
                        match
                        for match in matches
                        if not any(match.start < n.end and n.start < match.end for n in numeric)
                    ),
                ),
                key=lambda item: item.start,
            )
        )
    content = rich_text.model_copy(
        update={"inlines": _slice_inlines(rich_text, article_id, paragraph_id, matches)}
    )
    if numeric:
        numeric_spans = {(item.start, item.end) for item in numeric}
        marked: list[InlineNode] = []
        cursor = 0
        for inline in content.inlines:
            span = (cursor, cursor + len(inline.text))
            cursor = span[1]
            if inline.kind == InlineKind.CROSS_REFERENCE and span in numeric_spans:
                inline = inline.model_copy(
                    update={"attributes": {**inline.attributes, "source-position": "superscript"}}
                )
            marked.append(inline)
        content = content.model_copy(update={"inlines": tuple(marked)})
    citation_inlines = tuple(
        inline for inline in content.inlines if inline.kind == InlineKind.CROSS_REFERENCE
    )
    cross_references = tuple(
        CrossReference(
            target_id=match.target_id,
            reference_type="reference",
            label=text[match.start : match.end],
            evidence_ids=inline.evidence_ids,
        )
        for match, inline in zip(matches, citation_inlines, strict=True)
    )
    covered = [(item.start, item.end) for item in matches]
    unresolved = tuple(
        candidate.span()
        for candidate in _UNRESOLVED_CANDIDATE.finditer(text)
        if not any(candidate.start() < end and start < candidate.end() for start, end in covered)
    )
    reasons = tuple(
        [
            f"ambiguous_bibliographic_citation:{paragraph_id}:{start}:{end}"
            for start, end in ambiguous
        ]
        + [
            f"unresolved_bibliographic_citation:{paragraph_id}:{start}:{end}"
            for start, end in unresolved
        ]
    )
    return CitationResolution(
        content=content,
        cross_references=cross_references,
        review_reasons=reasons,
    )
