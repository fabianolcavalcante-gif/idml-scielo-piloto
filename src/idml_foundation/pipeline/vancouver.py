"""Deterministic parser for Vancouver (ICMJE/NLM) references and numeric citations.

Covers the shapes used by SciELO health journals such as RBEPID:
    "12. Gomes CS, Silva AG, et al. Title. Rev Bras Epidemiol. 2021;24(Supl. 2):e210013."
    "3. World Health Organization. Title [Internet]. Geneva: WHO; 2020 [accessed on ...]."
Anything that does not match is returned with only what is certain (label, authors, title),
so nothing is invented.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_LABEL = re.compile(r"^\s*(\d{1,3})\s*\.?\s+(?=\S)")
# ". 2021;24(Supl. 2):e210013" or ". 2020 Mar 3;12(3):100-5" or ". 2019;8:e1"
_JOURNAL_TAIL = re.compile(
    r"[.?!]?\s+(?P<year>(?:18|19|20)\d{2})[a-z]?"
    r"(?:\s+[A-Z][a-z]{2}(?:\s+\d{1,2})?)?\s*;\s*"
    r"(?P<volume>[^():;]*?)\s*(?:\((?P<issue>[^)]*)\))?\s*:\s*"
    r"(?P<pages>[A-Za-z]*\d+[A-Za-z0-9]*(?:\s*[-\u2013]\s*[A-Za-z]?\d+[A-Za-z0-9]*)?)"
)
_INITIALS = re.compile(r"[A-ZÀ-Ý]{1,4}")
_SENTENCE_END = re.compile(r"[.?!](?=\s)")


@dataclass(frozen=True)
class VancouverReference:
    label: int | None
    authors: tuple[str, ...] = ()  # "Surname, INITIALS" (builder splits on the comma)
    collab: bool = False
    et_al: bool = False
    title: str | None = None
    source: str | None = None
    year: str | None = None
    volume: str | None = None
    issue: str | None = None
    first_page: str | None = None
    last_page: str | None = None
    elocation_id: str | None = None
    publication_type: str | None = None
    review_reasons: tuple[str, ...] = field(default_factory=tuple)


def reference_label(value: str) -> int | None:
    match = _LABEL.match(value)
    return int(match.group(1)) if match else None


def _authors_end(text: str) -> int:
    """Index of the '.' closing the author list ('..., Silva AG.' or '..., et al.')."""
    for match in _SENTENCE_END.finditer(text):
        word = text[: match.start()].rsplit(" ", 1)[-1].rstrip(",")
        if _INITIALS.fullmatch(word) or word == "al":
            return match.start()
    first = _SENTENCE_END.search(text)
    return first.start() if first else -1


def _person(value: str) -> str | None:
    parts = value.split()
    if len(parts) >= 2 and _INITIALS.fullmatch(parts[-1]):
        return f"{' '.join(parts[:-1])}, {parts[-1]}"
    return None


def _pages(value: str) -> tuple[str | None, str | None, str | None]:
    if re.fullmatch(r"e[a-z]*\d+[a-z0-9]*", value, re.IGNORECASE):
        return None, None, value
    if "-" in value or "\u2013" in value:
        first, last = (part.strip() for part in re.split(r"[-\u2013]", value, maxsplit=1))
        if last.isdigit() and first.isdigit() and len(last) < len(first):
            last = first[: len(first) - len(last)] + last  # 100-5 -> 100-105
        return first, last, None
    return value, None, None


def parse_vancouver(line: str) -> VancouverReference:
    label = reference_label(line)
    body = _LABEL.sub("", line, count=1).strip()
    end = _authors_end(body)
    if end < 0:
        return VancouverReference(label=label, review_reasons=("vancouver_unparsed",))
    author_text, rest = body[:end].strip(), body[end + 1 :].strip()
    names = [item.strip() for item in author_text.split(",") if item.strip()]
    et_al = bool(names) and names[-1].casefold() in {"et al", "et al."}
    if et_al:
        names = names[:-1]
    persons = [_person(name) for name in names]
    collab = bool(names) and not any(persons)
    authors = (author_text,) if collab else tuple(p for p in persons if p)

    tail = _JOURNAL_TAIL.search(rest)
    if tail is not None:
        head = rest[: tail.start()].strip()  # "Title. Source" (source may lack the dot)
        sentences = [m.end() for m in _SENTENCE_END.finditer(head + " ")]
        if sentences and sentences[-1] >= len(head):
            sentences = sentences[:-1]
        split = sentences[-1] if sentences else -1
        title = head[:split].strip(" .") if split > 0 else None
        source = head[split:].strip(" .") if split > 0 else head.strip(" .")
        first, last, elocation = _pages(tail.group("pages"))
        return VancouverReference(
            label=label,
            authors=authors,
            collab=collab,
            et_al=et_al,
            title=title or None,
            source=source or None,
            year=tail.group("year"),
            volume=(tail.group("volume") or "").strip() or None,
            issue=(tail.group("issue") or "").strip() or None,
            first_page=first,
            last_page=last,
            elocation_id=elocation,
            publication_type="journal",
        )
    sentence = _SENTENCE_END.search(rest)
    title = (rest[: sentence.start()] if sentence else rest).strip(" .") or None
    kind = "webpage" if "[internet]" in rest.casefold() else None
    year = re.findall(r"(?<!\d)((?:18|19|20)\d{2})(?!\d)", rest)
    return VancouverReference(
        label=label,
        authors=authors,
        collab=collab,
        et_al=et_al,
        title=title,
        year=year[0] if year else None,
        publication_type=kind,
        review_reasons=("vancouver_non_journal_partial",),
    )


_NUMERIC_CITATION = re.compile(r"^[\s\d,;\-\u2013]+$")


def numeric_citation_spans(text: str) -> list[tuple[int, int, int]]:
    """(start, end, number) for each number in '1', '2,3', '4-6' (range endpoints)."""
    if not _NUMERIC_CITATION.fullmatch(text) or not re.search(r"\d", text):
        return []
    return [(m.start(), m.end(), int(m.group())) for m in re.finditer(r"\d{1,3}", text)]
