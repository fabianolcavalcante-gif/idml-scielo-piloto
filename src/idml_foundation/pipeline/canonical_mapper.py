from __future__ import annotations

import dataclasses
import hashlib
import re
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, cast
from urllib.parse import urlparse

from idml_foundation.asset_identity import figure_asset_number, inline_equation_asset_number
from idml_foundation.domain.canonical import (
    Affiliation,
    ArticleHistoryDate,
    Asset,
    BackMatter,
    CanonicalArticle,
    Contributor,
    ContributorName,
    FieldState,
    FigureBlock,
    FormulaBlock,
    FormulaRepresentation,
    FrontMatter,
    FundingStatement,
    Identifier,
    InlineKind,
    InlineNode,
    JournalIdentity,
    ListBlock,
    ListItem,
    LocalizedText,
    NoteBlock,
    Paragraph,
    Reference,
    RichText,
    Section,
    SourcedText,
    TableBlock,
    TableCellSpan,
)
from idml_foundation.domain.common import (
    Evidence,
    EvidenceLocator,
    SourceKind,
    canonical_bytes,
    stable_id,
)
from idml_foundation.domain.raw import (
    AnchoredPlacement,
    RawAnchoredObject,
    RawArticle,
    RawAsset,
    RawObjectKind,
    RawParagraph,
    RawStory,
)
from idml_foundation.pipeline.citation_resolver import resolve_citations
from idml_foundation.pipeline.country_codes import iso_country_code
from idml_foundation.pipeline.funding_parser import parse_funding
from idml_foundation.pipeline.idml_parser import style_prefix
from idml_foundation.pipeline.metadata_normalization import split_explicit_brazil_state
from idml_foundation.pipeline.profile import JournalProfile
from idml_foundation.pipeline.reference_metadata import ReferenceType, reference_metadata
from idml_foundation.pipeline.reference_parser import reference_without_volume
from idml_foundation.pipeline.vancouver import parse_vancouver

_ARTICLE_NUMBER = re.compile(r"(?:^|_)(20\d{2})(\d{1,4})(?:_|$)")
_AUTHOR_MARKERS = re.compile(r"[\d*]+")
_NUMBERED_GRAPHIC = re.compile(
    r"^\s*(figure|figura|fig\.?|table|tabela|chart|quadro|graph|gr[áa]fico)\s*([1-9]\d*)\b",
    re.IGNORECASE,
)
# 'Chart 1. Continuation.' repeats the caption of a table split across pages.
_CONTINUATION_CAPTION = re.compile(
    r"^[\s.:\-\u2013\u2014]*(?:continuation|continued|continua[çc][ãa]o|continua|cont\.)",
    re.IGNORECASE,
)
_TABLE_LABEL_WORDS = frozenset({"table", "tabela", "chart", "quadro"})


def _caption_family(word: str) -> str:
    """'table' for Table/Tabela/Chart/Quadro captions, 'figure' otherwise."""
    return "table" if word.casefold().rstrip(".") in _TABLE_LABEL_WORDS else "figure"


def _caption_label(word: str, number: int) -> str:
    """Keep the source label word ('Chart 1'); normalize 'Fig.' to 'Figure'."""
    clean = word.rstrip(".")
    if clean.casefold() == "fig":
        clean = "Figure"
    return f"{clean[:1].upper()}{clean[1:].lower()} {number}"


_CAPTION_SEPARATOR = re.compile(r"^[\s.\-\u2013\u2014:]*")
_MISSING_INLINE_FORMULA = re.compile(r"(?m)^[ \t]*(?=:[ \t]+\S)")
_NATIVE_DISPLAY_FORMULA = re.compile(
    r"(?m)^(?P<source>[^\n]*(?:=|\u2211|\u220f|\u2264|\u2265|\u2248|\u2260)[^\n]*?)"
    r"[ \t]*(?P<label>\([1-9]\d*\))[ \t]*$"
)
_PSEUDOCODE_LINE = re.compile(r"(?m)^\d+:\s*[^\n]+$")
_LIST_MARKER = re.compile(r"^\s*(?:\d+[.)]|[\u2022\u25aa\u25e6*-])\s*")
_LIST_LINE_MARKER = re.compile(r"(?m)^[ \t]*(?:\d+[.)]|[\u2022\u25aa\u25e6*-])[ \t]*")
_NATIVE_INLINE_ASSIGNMENT = re.compile(
    r"(?m)^(?P<source>[^\s:,\n]{1,12}\s*=\s*[^;\n]{1,100},\s*"
    r"[^\s:,\n]{1,12}\s*=\s*\[[^\n]+\])[ \t]*$"
)
_EMAIL = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.IGNORECASE)
_ORCID_URL = re.compile(r"https://orcid\.org/\d{4}-\d{4}-\d{4}-\d{3}[\dX]")
_HISTORY = re.compile(
    r"^Received\s+on:\s*(\d{2}/\d{2}/\d{4})\s*[\-\u2013\u2014]\s*"
    r"Accepted\s+on:\s*(\d{2}/\d{2}/\d{4})$",
    re.IGNORECASE,
)
_SECTION_ROLE = re.compile(r"^section-level-([1-9]\d*)$")
_REFERENCE_DOI = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
_REFERENCE_YEAR = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")
_REFERENCE_PUBLICATION_YEAR = re.compile(
    r",\s*((?:19|20)\d{2})\.(?=\s*(?:https?://|Available at:|$))",
    re.IGNORECASE,
)
_AFFILIATION = re.compile(
    r"^(?P<institution>[^,]+),\s*(?P<department>.+?)\s*[\ufffd\u2013\u2014]\s*"
    r"(?P<city>[^,]+),\s*(?P<country>[^.]+)\.?$"
)

_STANDARD_SECTION_TYPES = {
    "introduction": "intro",
    "materials and methods": "materials|methods",
    "methods": "materials|methods",
    "results": "results",
    "result discussion": "results|discussion",
    "results and discussion": "results|discussion",
    "discussion": "discussion",
    "conclusion": "conclusions",
    "conclusions": "conclusions",
}


@dataclass(frozen=True)
class _CorrespondenceData:
    email: SourcedText | None = None
    history_dates: tuple[ArticleHistoryDate, ...] = ()
    funding: tuple[FundingStatement, ...] = ()
    conflicts: SourcedText | None = None
    notes: tuple[NoteBlock, ...] = ()
    review_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class _BackStatementData:
    contribution_statement: SourcedText | None = None
    data_availability: SourcedText | None = None
    excluded_paragraph_ids: frozenset[str] = frozenset()
    review_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class _NativeDisplayFormula:
    start: int
    end: int
    source: str
    label: str


def _safe_external_href(value: str) -> str | None:
    if len(value) > 2048 or any(ord(character) < 32 for character in value):
        return None
    parsed = urlparse(value)
    if parsed.scheme.casefold() in {"http", "https"} and parsed.netloc:
        return value
    if parsed.scheme.casefold() == "mailto" and parsed.path:
        return value
    return None


def _present(value: str, evidence_ids: tuple[str, ...], transformation: str) -> SourcedText:
    return SourcedText(
        value=value.strip(),
        state=FieldState.PRESENT,
        evidence_ids=evidence_ids,
        transformation=transformation,
        confidence=1.0,
    )


def _missing(transformation: str) -> SourcedText:
    return SourcedText(state=FieldState.MISSING, transformation=transformation, confidence=1.0)


def _section_title(value: str, level: int) -> str:
    normalized = " ".join(value.split())
    return normalized.upper() if level == 1 else normalized


def _section_type(value: str, level: int) -> str | None:
    if level != 1:
        return None
    normalized = " ".join(value.split()).casefold()
    return _STANDARD_SECTION_TYPES.get(normalized)


# Roles that never belong inside a data table: a table holding them is a layout box.
_FLOW_ROLES = frozenset(
    {
        "abstract",
        "abstract-heading",
        "keywords",
        "title-primary",
        "title-secondary",
        "contributors",
        "affiliations",
    }
)
_ABSTRACT_LABELS = frozenset({"abstract", "resumo", "resumen", "résumé"})
_REFERENCE_LABELS = frozenset(
    {"references", "referências", "referencias", "referência", "bibliography", "bibliografia"}
)


_KEYWORDS_LINE = re.compile(
    r"^\s*(keywords|key words|palavras-chave|palavras chave|palabras clave|descritores)"
    r"\s*:\s*(.*)$",
    re.IGNORECASE | re.DOTALL,
)


_ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
_MARKER_TOKEN = re.compile(r"\*|\d+|[IVXLC]+")


def _marker_index(token: str) -> int | None:
    """Affiliation ordinal of an author marker: '3' -> 3, 'IV' -> 4, '*' -> None."""
    if token.isdigit():
        return int(token)
    if not token or any(character not in _ROMAN_VALUES for character in token):
        return None
    total = 0
    for current, following in zip(token, [*token[1:], ""], strict=True):
        value = _ROMAN_VALUES[current]
        total += -value if following and _ROMAN_VALUES[following] > value else value
    return total


def _split_marked_authors(
    runs: list[tuple[str, bool]],
) -> list[tuple[str, list[str]]]:
    """Split an author line into (name, markers) using superscript runs as markers.

    Commas in normal text separate authors; a segment with markers but no name
    (e.g. the ", III" of "Duarte II, III") extends the previous author's markers.
    """
    authors: list[tuple[str, list[str]]] = []
    name = ""
    markers: list[str] = []

    def close() -> None:
        nonlocal name, markers
        clean = " ".join(name.replace("*", " ").split())
        if any(character.isalpha() for character in clean):
            authors.append((clean, markers))
        elif authors:
            authors[-1][1].extend(markers)
        name, markers = "", []

    for value, superscript in runs:
        if superscript:
            markers.extend(_MARKER_TOKEN.findall(value))
            continue
        for index, piece in enumerate(value.split(",")):
            if index:
                close()
            markers.extend("*" for _ in range(piece.count("*")))
            name += piece
    close()
    return authors


_HISTORY_TYPES = {
    "received on": "received",
    "recebido em": "received",
    "recibido el": "received",
    "reviewed on": "rev-recd",
    "revised on": "rev-recd",
    "revisado em": "rev-recd",
    "reformulado em": "rev-recd",
    "accepted on": "accepted",
    "approved on": "accepted",
    "aceito em": "accepted",
    "aprovado em": "accepted",
    "aceptado el": "accepted",
}
_HISTORY_LANGUAGE = {
    label: ("en" if label.endswith(" on") else "es" if label.endswith(" el") else "pt")
    for label in _HISTORY_TYPES
}
_HISTORY_LABELLED = re.compile(
    r"(?P<label>" + "|".join(map(re.escape, _HISTORY_TYPES)) + r")\s*:?\s*"
    r"(?P<date>\d{1,2}/\d{1,2}/\d{4})",
    re.IGNORECASE,
)


def _history_iso_date(value: str, order: str) -> str | None:
    """Parse d/m/y or m/d/y per profile; an unambiguous date (a part > 12) wins."""
    first, second, year = (int(part) for part in value.split("/"))
    if first > 12 and second <= 12:
        order = "dmy"
    elif second > 12 and first <= 12:
        order = "mdy"
    day, month = (second, first) if order == "mdy" else (first, second)
    try:
        return datetime(year, month, day).date().isoformat()
    except ValueError:
        return None


_AFFILIATION_NO_DEPARTMENT = re.compile(
    r"^(?P<institution>[^,\ufffd\u2013\u2014]+?)\s*[\ufffd\u2013\u2014]\s*"
    r"(?P<city>[^,]+),\s*(?P<country>[^.]+)\.?$"
)


def _roman(number: int) -> str:
    out = ""
    for value, letters in ((100, "C"), (90, "XC"), (50, "L"), (40, "XL"), (10, "X"), (9, "IX")):
        while number >= value:
            out, number = out + letters, number - value
    for value, letters in ((5, "V"), (4, "IV"), (1, "I")):
        while number >= value:
            out, number = out + letters, number - value
    return out


def _strip_affiliation_label(line: str, ordinal: int) -> str:
    """Drop the leading affiliation label: any digits, a spaced roman numeral, or the
    expected ordinal glued to the name ('IVNTS' as 4th line -> 'NTS')."""
    stripped = re.sub(r"^(?:\d+|[IVXLC]+(?=\s))", "", line).strip()
    if stripped != line.strip():
        return stripped
    expected = _roman(ordinal)
    if line.startswith(expected) and line[len(expected) : len(expected) + 1].isupper():
        return line[len(expected) :].strip()
    return line


class _AffiliationParts:
    """Minimal match-like view so the caller can keep using ``groupdict()``."""

    def __init__(self, values: dict[str, str]) -> None:
        self._values = values

    def groupdict(self) -> dict[str, str]:
        return dict(self._values)


def _split_trailing_country(match: re.Match[str]) -> re.Match[str] | _AffiliationParts:
    """'- Bogotá, Cundinamarca, Colombia' -> city 'Bogotá, Cundinamarca', country 'Colombia'."""
    values = {key: value or "" for key, value in match.groupdict().items()}
    city, country = values["city"], values["country"]
    if "," not in country or iso_country_code(country):
        return match
    head, last = country.rsplit(",", 1)
    if not iso_country_code(last):
        return match
    values["city"] = f"{city.strip()}, {head.strip()}"
    values["country"] = last.strip()
    return _AffiliationParts(values)


def _author_run_groups(runs: list[tuple[str, bool]]) -> list[list[int]]:
    """Indices of the runs belonging to each author, with the same rules as
    ``_split_marked_authors`` (used to attach ORCID icon links to the right author)."""
    groups: list[list[int]] = []
    name = ""
    current: list[int] = []

    def close() -> None:
        nonlocal name, current
        if any(character.isalpha() for character in name):
            groups.append(current)
        elif groups:
            groups[-1].extend(current)
        name, current = "", []

    for index, (value, superscript) in enumerate(runs):
        if superscript:
            current.append(index)
            continue
        for position, piece in enumerate(value.split(",")):
            if position:
                close()
            name += piece.replace("*", " ")
        current.append(index)
    close()
    return groups


def _front_heading_role(value: str) -> str | None:
    """Recognize abstract/reference headings set with an ordinary section style."""
    normalized = " ".join(value.split()).strip(":. ").casefold()
    if normalized in _ABSTRACT_LABELS:
        return "abstract-heading"
    if normalized in _REFERENCE_LABELS:
        return "references-heading"
    return None


def _language_from_label(value: str, fallback: str) -> str:
    normalized = " ".join(value.split()).strip(":. ").casefold()
    if normalized in {"abstract", "keywords"}:
        return "en"
    if normalized in {"resumo", "palavras-chave", "palavras chave"}:
        return "pt"
    return fallback


def _credit_roles(statement: SourcedText | None) -> dict[str, tuple[str, ...]]:
    if statement is None or not statement.value:
        return {}
    roles: dict[str, tuple[str, ...]] = {}
    for item in re.split(
        r"\.\s+(?=[A-Z][^:]{1,100},\s*[^:]+:)|\.\s+(?=[A-ZÀ-Ý]{1,8}\s*:)|\.$",
        statement.value.strip(),
    ):
        if ":" not in item:
            continue
        source_name, source_roles = item.split(":", 1)
        key = " ".join(source_name.replace(",", " ").split()).casefold()
        normalized_roles = []
        for role in source_roles.split(","):
            value = " ".join(role.split()).strip(". ").replace("\ufffd", "\u2013")
            if value:
                normalized_roles.append(value)
        if key and normalized_roles:
            roles[key] = tuple(normalized_roles)
    return roles


_PARTICLES = frozenset({"de", "da", "do", "das", "dos", "del", "la", "e", "y", "van", "von"})
_CONTRIBUTIONS_LINE = re.compile(
    r"^\s*(?:authors?[\u2019']?\s*contributions?|contribui[çc][õo]es\s+dos\s+autores)\s*:\s*(.+)$",
    re.IGNORECASE,
)


def _name_initials(name: str) -> set[str]:
    """Lower-cased initials of a full name, with and without particles ('de', 'da'...)."""
    variants: set[str] = set()
    for separator in (r"[\s\-]+", r"\s+"):  # 'La-Rotta' counts as L or as LR
        parts = [part for part in re.split(separator, name) if part and part[0].isalpha()]
        variants.add("".join(part[0] for part in parts).casefold())
        variants.add(
            "".join(part[0] for part in parts if part.casefold() not in _PARTICLES).casefold()
        )
    return variants


def _contribution_line(
    paragraphs: list[tuple[RawStory, RawParagraph]], text_for: object
) -> SourcedText | None:
    """'AUTHORS' CONTRIBUTIONS: CEAL: ...' typed inside the correspondence block."""
    for story, paragraph in paragraphs:
        for line in text_for(story, paragraph).splitlines():  # type: ignore[operator]
            match = _CONTRIBUTIONS_LINE.match(line)
            if match:
                return _present(
                    match.group(1).strip(),
                    paragraph.evidence_ids,
                    "correspondence-contributions-line",
                )
    return None


def _author_title_boundary(prefix: str, start: int) -> int:
    """Position of the '. ' that ends the last author, skipping initials ('NUNES, T. F.')."""
    candidates = [match.start() for match in re.finditer(r"\. ", prefix[start:])]
    last_initial = -1
    for offset in candidates:
        position = start + offset
        token = prefix[:position].rsplit(" ", 1)[-1].lstrip(",")
        if re.fullmatch(r"[A-ZÀ-Ý]", token):
            last_initial = position
            continue
        return position
    return last_initial


def _reference_parts(value: str) -> tuple[tuple[str, ...], str | None, str | None]:
    journal = re.match(r"^(?P<prefix>.+)\.\s+(?P<source>.+?),\s+v\.\s*", value)
    if journal is not None:
        prefix = journal.group("prefix")
        source = journal.group("source").strip()
    else:
        return reference_without_volume(value)
    last_semicolon = prefix.rfind(";")
    boundary = _author_title_boundary(prefix, last_semicolon + 1)
    if boundary < 0:
        return (), None, source
    author_text = prefix[:boundary].strip()
    title = prefix[boundary + 2 :].strip()
    authors = tuple(item.strip() for item in author_text.split(";") if item.strip())
    return authors, title or None, source or None


def _reference_details(value: str, year: str | None) -> dict[str, str]:
    details: dict[str, str] = {}
    patterns = {
        "volume": r",\s+v\.\s*([^,]+)",
        "issue": r",\s+n\.\s*([^,]+)",
    }
    for key, pattern in patterns.items():
        if match := re.search(pattern, value):
            details[key] = match.group(1).strip()
    pages = re.search(r",\s+p\.\s*([^,\-]+?)(?:\s*-\s*([^,]+))?,", value)
    if pages:
        details["first_page"] = pages.group(1).strip()
        details["last_page"] = pages.group(2).strip() if pages.group(2) else details["first_page"]
    elif year and "volume" in details:
        tail = re.search(
            rf",\s+v\.\s*[^,]+(?:,\s+n\.\s*[^,]+)?(?:,\s+([^,]+))?,\s*{re.escape(year)}\.",
            value,
        )
        if tail and tail.group(1):
            details["elocation_id"] = tail.group(1).strip()
    return details


def _native_display_formulas(value: str) -> tuple[_NativeDisplayFormula, ...]:
    return tuple(
        _NativeDisplayFormula(
            start=match.start(),
            end=match.end(),
            source=match.group("source").strip(),
            label=match.group("label"),
        )
        for match in _NATIVE_DISPLAY_FORMULA.finditer(value)
        if match.group("source").strip()
    )


def _rich_text_slice(
    value: RichText,
    start: int,
    end: int,
    *,
    article_id: str,
    locator: str,
) -> RichText | None:
    plain = value.plain.value or ""
    sliced_plain = plain[start:end]
    if not sliced_plain.strip():
        return None
    cursor = 0
    sliced_inlines: list[InlineNode] = []
    for inline in value.inlines:
        inline_start = cursor
        inline_end = cursor + len(inline.text)
        overlap_start = max(start, inline_start)
        overlap_end = min(end, inline_end)
        if overlap_start < overlap_end:
            sliced_inlines.append(
                inline.model_copy(
                    update={
                        "id": stable_id(article_id, "inline-slice", f"{locator}:{inline.id}"),
                        "text": inline.text[
                            overlap_start - inline_start : overlap_end - inline_start
                        ],
                    }
                )
            )
        elif not inline.text and inline.kind == InlineKind.INLINE_FORMULA and start <= cursor < end:
            sliced_inlines.append(
                inline.model_copy(
                    update={"id": stable_id(article_id, "inline-slice", f"{locator}:{inline.id}")}
                )
            )
        cursor = inline_end
    return RichText(
        plain=value.plain.model_copy(
            update={
                "value": sliced_plain,
                "state": FieldState.PRESENT,
                "transformation": "native-display-formula-split",
            }
        ),
        inlines=tuple(sliced_inlines),
    )


def _without_prefix(value: RichText, length: int) -> RichText:
    plain = value.plain.value or ""
    if length <= 0 or length > len(plain):
        return value
    remaining = length
    inlines: list[InlineNode] = []
    for inline in value.inlines:
        if remaining >= len(inline.text):
            remaining -= len(inline.text)
            if not inline.text:
                inlines.append(inline)
            continue
        if remaining:
            inline = inline.model_copy(update={"text": inline.text[remaining:]})
            remaining = 0
        if inline.text or inline.kind == InlineKind.INLINE_FORMULA:
            inlines.append(inline)
    return value.model_copy(
        update={
            "plain": value.plain.model_copy(
                update={
                    "value": plain[length:] or None,
                    "transformation": "caption-label-extracted",
                }
            ),
            "inlines": tuple(inlines),
        }
    )


def _insert_missing_inline_formula_nodes(
    inlines: list[InlineNode],
    *,
    plain: str,
    paragraph: RawParagraph,
    article_id: str,
) -> list[InlineNode]:
    """Represent source-visible gaps without inventing formula text or changing plain content."""
    offsets = [match.start() for match in _MISSING_INLINE_FORMULA.finditer(plain)]
    for gap_position, offset in reversed(tuple(enumerate(offsets))):
        cursor = 0
        for index, inline in enumerate(inlines):
            next_cursor = cursor + len(inline.text)
            if cursor <= offset <= next_cursor and inline.kind != InlineKind.INLINE_FORMULA:
                local_offset = offset - cursor
                insertion = index
                if local_offset == len(inline.text):
                    insertion += 1
                elif local_offset > 0:
                    left = inline.model_copy(
                        update={
                            "id": stable_id(article_id, "inline-gap-left", f"{inline.id}:{offset}"),
                            "text": inline.text[:local_offset],
                        }
                    )
                    right = inline.model_copy(
                        update={
                            "id": stable_id(
                                article_id, "inline-gap-right", f"{inline.id}:{offset}"
                            ),
                            "text": inline.text[local_offset:],
                        }
                    )
                    inlines[index : index + 1] = [left, right]
                    insertion = index + 1
                inlines.insert(
                    insertion,
                    InlineNode(
                        id=stable_id(
                            article_id,
                            "inline-formula-gap",
                            f"{paragraph.id}:{gap_position}:{offset}",
                        ),
                        kind=InlineKind.INLINE_FORMULA,
                        text="",
                        formula_source=SourcedText(
                            state=FieldState.NEEDS_REVIEW,
                            evidence_ids=paragraph.evidence_ids,
                            transformation="source-visible-inline-formula-gap",
                            confidence=1.0,
                        ),
                        formula_representation=FormulaRepresentation.UNKNOWN,
                        evidence_ids=paragraph.evidence_ids,
                    ),
                )
                break
            cursor = next_cursor
    return inlines


def _mark_native_inline_assignments(
    inlines: list[InlineNode],
    *,
    plain: str,
    paragraph: RawParagraph,
    article_id: str,
) -> list[InlineNode]:
    """Represent a complete native mathematical assignment line as one inline formula."""
    for match in reversed(tuple(_NATIVE_INLINE_ASSIGNMENT.finditer(plain))):
        cursor = 0
        positioned: list[tuple[int, int, int, InlineNode]] = []
        for index, inline in enumerate(inlines):
            end = cursor + len(inline.text)
            positioned.append((index, cursor, end, inline))
            cursor = end
        affected = [
            item for item in positioned if item[1] < match.end() and item[2] > match.start()
        ]
        if not affected or any(item[3].kind == InlineKind.INLINE_FORMULA for item in affected):
            continue
        first_index, first_start, _, first_inline = affected[0]
        last_index, last_start, _, last_inline = affected[-1]
        replacement: list[InlineNode] = []
        if match.start() > first_start:
            replacement.append(
                first_inline.model_copy(
                    update={
                        "id": stable_id(
                            article_id,
                            "native-inline-formula-head",
                            f"{first_inline.id}:{match.start()}",
                        ),
                        "text": first_inline.text[: match.start() - first_start],
                    }
                )
            )
        evidence_ids = tuple(
            dict.fromkeys(evidence_id for item in affected for evidence_id in item[3].evidence_ids)
        )
        replacement.append(
            InlineNode(
                id=stable_id(
                    article_id,
                    "native-inline-formula",
                    f"{paragraph.id}:{match.start()}:{match.end()}",
                ),
                kind=InlineKind.INLINE_FORMULA,
                text=plain[match.start() : match.end()],
                formula_source=_present(
                    match.group("source"),
                    evidence_ids,
                    "native-inline-formula-source",
                ),
                formula_representation=FormulaRepresentation.TEXT,
                evidence_ids=evidence_ids,
            )
        )
        last_local_end = match.end() - last_start
        if last_local_end < len(last_inline.text):
            replacement.append(
                last_inline.model_copy(
                    update={
                        "id": stable_id(
                            article_id,
                            "native-inline-formula-tail",
                            f"{last_inline.id}:{match.end()}",
                        ),
                        "text": last_inline.text[last_local_end:],
                    }
                )
            )
        inlines[first_index : last_index + 1] = replacement
    return inlines


def _group_pseudocode_inline_formulas(
    inlines: list[InlineNode],
    *,
    plain: str,
    paragraph: RawParagraph,
    article_id: str,
) -> list[InlineNode]:
    """Collapse a source expression split across several anchored glyph assets."""
    for line in reversed(tuple(_PSEUDOCODE_LINE.finditer(plain))):
        cursor = 0
        positioned: list[tuple[int, int, int, InlineNode]] = []
        for index, inline in enumerate(inlines):
            end = cursor + len(inline.text)
            positioned.append((index, cursor, end, inline))
            cursor = end
        formula_positions = [
            item
            for item in positioned
            if item[3].kind == InlineKind.INLINE_FORMULA and line.start() <= item[1] < line.end()
        ]
        if len(formula_positions) < 3:
            continue

        first_index, group_start, _, _ = formula_positions[0]
        last_index = first_index
        source_parts: list[str] = []
        evidence_ids: list[str] = []
        trailing: InlineNode | None = None
        for index, start, end, inline in positioned[first_index:]:
            if start >= line.end():
                break
            last_index = index
            evidence_ids.extend(inline.evidence_ids)
            if inline.kind == InlineKind.INLINE_FORMULA:
                source_value = inline.formula_source.value if inline.formula_source else None
                if source_value:
                    source_parts.append(re.sub(r"\.[^.]+$", "", source_value.rsplit("/", 1)[-1]))
            else:
                source_parts.append(inline.text[: max(0, line.end() - start)])
            if end > line.end():
                split = line.end() - start
                trailing = inline.model_copy(
                    update={
                        "id": stable_id(
                            article_id,
                            "pseudocode-formula-tail",
                            f"{inline.id}:{line.end()}",
                        ),
                        "text": inline.text[split:],
                    }
                )
                break

        grouped_source = "".join(source_parts).strip()
        grouped = InlineNode(
            id=stable_id(
                article_id,
                "grouped-inline-formula",
                f"{paragraph.id}:{line.start()}:{line.end()}",
            ),
            kind=InlineKind.INLINE_FORMULA,
            text=plain[group_start : line.end()],
            formula_source=_present(
                grouped_source,
                tuple(dict.fromkeys(evidence_ids)),
                "grouped-pseudocode-formula-components",
            ),
            formula_representation=FormulaRepresentation.TEXT,
            evidence_ids=tuple(dict.fromkeys(evidence_ids)),
        )
        replacement = [grouped]
        if trailing is not None and trailing.text:
            replacement.append(trailing)
        inlines[first_index : last_index + 1] = replacement
    return inlines


_DOI_IN_TEXT = re.compile(r"(?<![\d.])10\.\d{4,9}/[^\s<>\"]+")


_ERRATUM_CORRECTS = re.compile(
    r"(?:this\s+erratum\s+corrects|esta\s+errata\s+corrige|errata\s+de)\s*:?\s*"
    r"(?:https?://(?:dx\.)?doi\.org/\s*)?(10\.\d{4,9}/\S+)",
    re.IGNORECASE,
)


def _corrected_doi(raw: RawArticle, source_doi: str | None) -> str | None:
    """DOI of the article an erratum corrects, or None when this is not an erratum."""
    is_erratum = bool(source_doi and source_doi.casefold().endswith("erratum"))
    for story in raw.stories:
        text = "".join(run.text for run in story.runs)
        if match := _ERRATUM_CORRECTS.search(text):
            return match.group(1).rstrip(".,;)")
    if is_erratum and source_doi:
        return re.sub(r"erratum$", "", source_doi, flags=re.IGNORECASE) or None
    return None


def _doi_in_text(value: str) -> str | None:
    """First DOI in 'https://doi.org 10.1590/x' or 'https://doi.org10.1590/x' (typed slips)."""
    match = _DOI_IN_TEXT.search(value)
    return match.group(0).rstrip(".,;)") if match else None


def _article_id(source_id: str) -> str:
    match = _ARTICLE_NUMBER.search(source_id)
    if not match:
        return source_id.casefold()
    return f"e{match.group(1)}{match.group(2).zfill(4)}"


class CanonicalMapper:
    """Apply one explicit, versioned journal profile without semantic guessing."""

    def __init__(self, profile: JournalProfile) -> None:
        self.profile = profile

    def map(self, raw: RawArticle) -> CanonicalArticle:
        style_names = {style.id: style.source_name for style in raw.styles}
        style_properties = {style.id: style.properties for style in raw.styles}
        character_names = {style.id: style.normalized_name for style in raw.styles}
        story_by_id = {story.id: story for story in raw.stories}
        paragraphs_by_role: defaultdict[str, list[tuple[RawStory, RawParagraph]]] = defaultdict(
            list
        )
        unknown: set[str] = set()

        def paragraph_role(paragraph: RawParagraph) -> str | None:
            source_name = style_names.get(paragraph.paragraph_style_id or "", "")
            return self.profile.role_for_style(source_name, style_prefix(source_name))

        table_by_cell = {cell.id: table.id for table in raw.tables for cell in table.cells}
        layout_table_ids = frozenset(
            table_by_cell[paragraph.table_cell_id]
            for story in raw.stories
            for paragraph in story.paragraphs
            if paragraph.table_cell_id in table_by_cell and paragraph_role(paragraph) in _FLOW_ROLES
        )
        for story_id in raw.reading_order:
            story = story_by_id[story_id]
            runs = {run.id: run for run in story.runs}
            for paragraph in story.paragraphs:
                if paragraph.table_cell_id and (
                    table_by_cell.get(paragraph.table_cell_id) not in layout_table_ids
                ):
                    continue
                source_name = style_names.get(paragraph.paragraph_style_id or "", "")
                role = paragraph_role(paragraph)
                text = "".join(runs[run_id].text for run_id in paragraph.text_run_ids)
                if role and role.startswith("section-level-"):
                    role = _front_heading_role(text) or role
                if role:
                    paragraphs_by_role[role].append((story, paragraph))
                elif text.strip():
                    unknown.add(source_name or "<no-style>")

        profile_evidence = Evidence(
            id=stable_id(raw.article_id, "evidence", self.profile.profile_id),
            source_kind=SourceKind.SYSTEM,
            locator=EvidenceLocator(
                artifact_sha256=raw.source_artifact_sha256,
                logical_path="profiles/esa-aop-1.0.json",
                element_id=self.profile.profile_id,
            ),
            content_sha256=hashlib.sha256(canonical_bytes(self.profile)).hexdigest(),
            description="Versioned deterministic journal profile",
        )
        evidence = (*raw.evidence, profile_evidence)
        article_id = _article_id(raw.article_id)

        def text_for(story: RawStory, paragraph: RawParagraph) -> str:
            runs = {run.id: run for run in story.runs}
            return "".join(runs[item].text for item in paragraph.text_run_ids).strip()

        source_doi = next(
            (
                doi
                for story, paragraph in paragraphs_by_role["article-doi"]
                if (doi := _doi_in_text(text_for(story, paragraph)))
            ),
            None,
        )
        article_id = self.profile.article_id_for_doi(source_doi) or article_id
        corrected_doi = _corrected_doi(raw, source_doi)

        def first_text(role: str) -> tuple[str, tuple[str, ...]] | None:
            for story, paragraph in paragraphs_by_role[role]:
                value = text_for(story, paragraph)
                if value:
                    return value, paragraph.evidence_ids
            return None

        abstract_headings = [
            text_for(story, paragraph)
            for story, paragraph in paragraphs_by_role["abstract-heading"]
        ]
        document_languages = [
            _language_from_label(
                heading,
                self.profile.primary_language if position == 0 else self.profile.secondary_language,
            )
            for position, heading in enumerate(abstract_headings)
        ]
        titles: list[LocalizedText] = []
        for position, role in enumerate(("title-primary", "title-secondary")):
            language = (
                document_languages[position]
                if position < len(document_languages)
                else (
                    self.profile.primary_language
                    if position == 0
                    else self.profile.secondary_language
                )
            )
            candidate = first_text(role)
            if candidate:
                titles.append(
                    LocalizedText(
                        language=language,
                        text=_present(candidate[0], candidate[1], f"style-role:{role}"),
                    )
                )

        article_identifiers = [
            Identifier(
                kind="publisher-id",
                value=_present(article_id, (profile_evidence.id,), "filename-rule"),
            )
        ]
        if corrected_doi:
            article_identifiers.append(
                Identifier(
                    kind="corrected-article-doi",
                    value=_present(corrected_doi, (profile_evidence.id,), "erratum-corrects-doi"),
                )
            )
            if not titles:
                titles.append(
                    LocalizedText(
                        language=self.profile.primary_language,
                        text=_present("ERRATUM", (profile_evidence.id,), "erratum-default-title"),
                    )
                )
        article_doi = first_text("article-doi")
        if article_doi:
            doi = _doi_in_text(article_doi[0]) or re.sub(
                r"^https?://(?:dx\.)?doi\.org/", "", article_doi[0], flags=re.I
            )
            article_identifiers.append(
                Identifier(
                    kind="doi",
                    value=_present(doi, article_doi[1], "style-role:article-doi"),
                )
            )

        back_statements = self._back_statements(paragraphs_by_role, text_for, raw)
        affiliations = self._affiliations(paragraphs_by_role, text_for, article_id)
        contributors = self._contributors(
            paragraphs_by_role,
            text_for,
            article_id,
            tuple(item.id for item in affiliations),
            raw,
            contribution_statement=back_statements.contribution_statement
            or _contribution_line(paragraphs_by_role["correspondence"], text_for),
        )
        correspondence = self._correspondence(paragraphs_by_role, text_for, article_id, raw)
        if correspondence.email is not None:
            corresponding_positions = [
                position
                for position, contributor in enumerate(contributors)
                if contributor.corresponding
            ]
            if len(corresponding_positions) == 1:
                position = corresponding_positions[0]
                contributors = tuple(
                    contributor.model_copy(update={"email": correspondence.email})
                    if index == position
                    else contributor
                    for index, contributor in enumerate(contributors)
                )
        abstracts: list[LocalizedText] = []
        keywords: list[LocalizedText] = []
        story_rank = {story_id: index for index, story_id in enumerate(raw.reading_order)}

        def document_key(item: tuple[RawStory, RawParagraph]) -> tuple[int, int]:
            return story_rank.get(item[0].id, len(story_rank)), item[1].position

        heading_keys = sorted(
            (document_key(item), position)
            for position, item in enumerate(paragraphs_by_role["abstract-heading"])
            if abstract_headings[position].strip()
        )
        grouped: dict[int, list[tuple[str, tuple[str, ...]]]] = {}
        for position, (story, paragraph) in enumerate(paragraphs_by_role["abstract"]):
            key = document_key((story, paragraph))
            preceding = [heading for heading_key, heading in heading_keys if heading_key < key]
            # Without headings, each abstract paragraph keeps its historical positional slot.
            slot = preceding[-1] if preceding else position
            value = text_for(story, paragraph)
            kept_lines: list[str] = []
            for line in (value or "").split("\n"):
                keyword_line = _KEYWORDS_LINE.match(line)
                if keyword_line is None or not keyword_line.group(2).strip():
                    kept_lines.append(line)
                    continue
                # "Keywords: a. b." typed inside the abstract box belongs to the keywords.
                keywords.append(
                    LocalizedText(
                        language=_language_from_label(
                            keyword_line.group(1),
                            self.profile.primary_language
                            if slot == 0
                            else self.profile.secondary_language,
                        ),
                        text=_present(
                            keyword_line.group(2).strip(),
                            paragraph.evidence_ids,
                            "style-role:abstract-keywords-line",
                        ),
                    )
                )
            value = "\n".join(kept_lines).strip()
            if value:
                grouped.setdefault(slot, []).append((value, paragraph.evidence_ids))
        for slot, parts in grouped.items():
            fallback = (
                self.profile.primary_language if slot == 0 else self.profile.secondary_language
            )
            language = _language_from_label(
                abstract_headings[slot] if slot < len(abstract_headings) else "", fallback
            )
            abstracts.append(
                LocalizedText(
                    language=language,
                    text=_present(
                        "\n".join(value for value, _ in parts),
                        tuple(dict.fromkeys(e for _, ids in parts for e in ids)),
                        "style-role:abstract",
                    ),
                )
            )
        for position, (story, paragraph) in enumerate(paragraphs_by_role["keywords"]):
            fallback = (
                self.profile.primary_language if position == 0 else self.profile.secondary_language
            )
            value = text_for(story, paragraph)
            label = value.split(":", 1)[0] if ":" in value else ""
            language = _language_from_label(label, fallback)
            if ":" in value:
                value = value.split(":", 1)[1].strip()
            if value:
                keywords.append(
                    LocalizedText(
                        language=language,
                        text=_present(value, paragraph.evidence_ids, "style-role:keywords"),
                    )
                )

        references = self._references(paragraphs_by_role, text_for, article_id)
        sections, section_review_reasons = self._sections(
            raw,
            paragraphs_by_role,
            style_names,
            character_names,
            style_properties,
            article_id,
            references,
            excluded_paragraph_ids=back_statements.excluded_paragraph_ids,
            layout_table_ids=layout_table_ids,
        )
        notes = (*self._notes(raw, character_names, article_id), *correspondence.notes)
        assets = tuple(
            Asset(
                id=item.id,
                logical_name=item.logical_path,
                media_type=item.media_type,
                sha256=item.sha256,
                state=FieldState.NEEDS_REVIEW if item.external else FieldState.PRESENT,
                evidence_ids=item.evidence_ids,
            )
            for item in raw.assets
        )
        review_reasons = [f"unmapped_style:{name}" for name in sorted(unknown)]
        review_reasons.extend(
            f"{reason}:{reference.id}"
            for reference in references
            for reason in reference.review_reasons
        )
        review_reasons.extend(
            f"reading_order:{issue.code}:{issue.story_id or 'document'}"
            for issue in raw.reading_order_issues
        )
        if any(item.external for item in raw.assets):
            review_reasons.append("external_assets_require_package_resolution")
        review_reasons.extend(section_review_reasons)
        review_reasons.extend(back_statements.review_reasons)
        review_reasons.extend(correspondence.review_reasons)
        if correspondence.email is not None:
            corresponding_count = sum(item.corresponding for item in contributors)
            if corresponding_count != 1:
                review_reasons.append("correspondence_email_requires_single_marked_contributor")

        return CanonicalArticle(
            article_id=article_id,
            journal_profile_id=self.profile.profile_id,
            source_raw_sha256=hashlib.sha256(canonical_bytes(raw)).hexdigest(),
            front=FrontMatter(
                journal=JournalIdentity(
                    title=_present(
                        self.profile.journal_title,
                        (profile_evidence.id,),
                        "journal-profile",
                    ),
                    abbreviated_title=_present(
                        self.profile.journal_abbreviated_title,
                        (profile_evidence.id,),
                        "journal-profile",
                    ),
                    identifiers=(
                        Identifier(
                            kind="publisher-id",
                            value=_present(
                                self.profile.journal_publisher_id,
                                (profile_evidence.id,),
                                "journal-profile",
                            ),
                        ),
                        Identifier(
                            kind="print-issn",
                            value=_present(
                                self.profile.journal_print_issn,
                                (profile_evidence.id,),
                                "journal-profile",
                            ),
                        ),
                        Identifier(
                            kind="electronic-issn",
                            value=_present(
                                self.profile.journal_issn,
                                (profile_evidence.id,),
                                "journal-profile",
                            ),
                        ),
                    ),
                    publisher_name=_present(
                        self.profile.publisher_name,
                        (profile_evidence.id,),
                        "journal-profile",
                    ),
                ),
                article_identifiers=tuple(article_identifiers),
                article_category=_present(
                    "correction" if corrected_doi else self.profile.article_category,
                    (profile_evidence.id,),
                    "erratum-correction-type" if corrected_doi else "journal-profile",
                ),
                titles=tuple(titles),
                contributors=contributors,
                affiliations=affiliations,
                publication_date=_missing("not-present-in-idml-style-profile"),
                history_dates=correspondence.history_dates,
                abstracts=tuple(abstracts),
                keywords=tuple(keywords),
                license_text=_present(
                    self.profile.license_text,
                    (profile_evidence.id,),
                    "journal-profile",
                ),
                license_url=(
                    _present(self.profile.license_url, (profile_evidence.id,), "journal-profile")
                    if self.profile.license_url
                    else None
                ),
                funding=correspondence.funding,
                subject_category=_present(
                    "Erratum" if corrected_doi else self.profile.subject_category,
                    (profile_evidence.id,),
                    "erratum-section" if corrected_doi else "journal-profile",
                ),
            ),
            body=sections,
            back=BackMatter(
                contribution_statement=back_statements.contribution_statement,
                data_availability=back_statements.data_availability,
                conflicts=correspondence.conflicts,
                notes=notes,
                references=references,
            ),
            assets=assets,
            evidence=evidence,
            review_reasons=tuple(dict.fromkeys(review_reasons)),
        )

    def _back_statements(
        self,
        by_role: defaultdict[str, list[tuple[RawStory, RawParagraph]]],
        text_for: Callable[[RawStory, RawParagraph], str],
        raw: RawArticle,
    ) -> _BackStatementData:
        items = [
            (*item, role)
            for role in ("section-level-1", "section-level-2", "paragraph")
            for item in by_role[role]
        ]
        items.sort(key=lambda item: (raw.reading_order.index(item[0].id), item[1].position))
        contribution_statement: SourcedText | None = None
        data_availability: SourcedText | None = None
        excluded: set[str] = set()
        review_reasons: list[str] = []
        labels = {
            "authors' contributions": "contribution",
            "data availability statement": "data-availability",
        }
        for position, (story, paragraph, role) in enumerate(items):
            if not role.startswith("section-level"):
                continue
            normalized = re.sub(r"\s+", " ", text_for(story, paragraph)).strip().casefold()
            normalized = normalized.replace("\u2019", "'")
            statement_type = labels.get(normalized)
            if statement_type is None:
                continue
            if position + 1 >= len(items) or items[position + 1][2] != "paragraph":
                review_reasons.append(f"{statement_type}_statement_missing_after_heading")
                continue
            _, statement_paragraph, _ = items[position + 1]
            statement_story = items[position + 1][0]
            value = text_for(statement_story, statement_paragraph)
            if not value:
                review_reasons.append(f"{statement_type}_statement_empty")
                continue
            sourced = _present(
                value,
                statement_paragraph.evidence_ids,
                f"labeled-back-statement:{statement_type}",
            )
            if statement_type == "contribution":
                if contribution_statement is not None:
                    review_reasons.append("multiple_contribution_statements")
                    continue
                contribution_statement = sourced
            else:
                if data_availability is not None:
                    review_reasons.append("multiple_data_availability_statements")
                    continue
                data_availability = sourced
            excluded.update((paragraph.id, statement_paragraph.id))

        return _BackStatementData(
            contribution_statement=contribution_statement,
            data_availability=data_availability,
            excluded_paragraph_ids=frozenset(excluded),
            review_reasons=tuple(review_reasons),
        )

    def _correspondence(
        self,
        by_role: defaultdict[str, list[tuple[RawStory, RawParagraph]]],
        text_for: Callable[[RawStory, RawParagraph], str],
        article_id: str,
        raw: RawArticle,
    ) -> _CorrespondenceData:
        email: SourcedText | None = None
        conflicts: SourcedText | None = None
        history_dates: list[ArticleHistoryDate] = []
        funding: list[FundingStatement] = []
        notes: list[NoteBlock] = []
        review_reasons: list[str] = []
        seen_history: set[str] = set()
        hyperlink_targets = {
            link.source_id: link.target
            for link in raw.links
            if link.relationship == "external-hyperlink"
        }

        for story, paragraph in by_role["correspondence"]:
            evidence_ids = paragraph.evidence_ids
            lines = tuple(line.strip() for line in text_for(story, paragraph).splitlines())
            editor_line_count = sum(
                line.casefold().startswith(
                    tuple(
                        f"{label.casefold()}:"
                        for label in ("Associate editor", "Scientific editor", "Editor")
                    )
                )
                for line in lines
            )
            paragraph_orcid_targets = tuple(
                dict.fromkeys(
                    target
                    for run_id in paragraph.text_run_ids
                    if (target := hyperlink_targets.get(run_id)) is not None
                    and target.casefold().startswith("https://orcid.org/")
                )
            )
            if editor_line_count > 1 and paragraph_orcid_targets:
                review_reasons.append("ambiguous_editor_orcid_hyperlinks")
            for line_position, line in enumerate(lines):
                if not line:
                    continue
                lowered = line.casefold()
                if lowered.startswith("*corresponding author:"):
                    match = _EMAIL.search(line)
                    if match is None:
                        review_reasons.append("correspondence_email_not_parseable")
                    elif email is None:
                        email = _present(
                            match.group(0), evidence_ids, "correspondence-labeled-email"
                        )
                    else:
                        review_reasons.append("multiple_correspondence_emails")
                    continue
                if lowered.startswith("conflicts of interest:"):
                    value = line.split(":", 1)[1].strip()
                    if value and conflicts is None:
                        conflicts = _present(
                            value, evidence_ids, "correspondence-labeled-conflicts"
                        )
                    elif value:
                        review_reasons.append("multiple_conflicts_statements")
                    else:
                        review_reasons.append("empty_conflicts_statement")
                    continue
                if lowered.startswith("funding:"):
                    value = line.split(":", 1)[1].strip()
                    if not value:
                        review_reasons.append("empty_funding_statement")
                        continue
                    parsed_funding = parse_funding(value)
                    if not parsed_funding.agency and not parsed_funding.explicit_none:
                        review_reasons.append("funding_structure_requires_authority")
                    funding.append(
                        FundingStatement(
                            agency=(
                                _missing("explicit-no-funding-agency")
                                if parsed_funding.explicit_none
                                else _present(
                                    parsed_funding.agency,
                                    evidence_ids,
                                    "explicit-single-funder-declaration",
                                )
                                if parsed_funding.agency
                                else SourcedText(
                                    state=FieldState.NEEDS_REVIEW,
                                    evidence_ids=evidence_ids,
                                    transformation="unresolved-funding-structure",
                                )
                            ),
                            award_id=(
                                _present(
                                    parsed_funding.award,
                                    evidence_ids,
                                    "explicit-single-funder-award",
                                )
                                if parsed_funding.award
                                else None
                            ),
                            statement=_present(
                                value, evidence_ids, "correspondence-labeled-funding"
                            ),
                        )
                    )
                    continue
                history_match = _HISTORY.fullmatch(line)
                if history_match is not None:
                    for date_type, raw_date in zip(
                        ("received", "accepted"), history_match.groups(), strict=True
                    ):
                        if date_type in seen_history:
                            review_reasons.append(f"duplicate_history_date:{date_type}")
                            continue
                        try:
                            iso_date = datetime.strptime(raw_date, "%d/%m/%Y").date().isoformat()
                        except ValueError:
                            review_reasons.append(f"invalid_history_date:{date_type}")
                            continue
                        history_dates.append(
                            ArticleHistoryDate(
                                date_type=cast(
                                    Literal["received", "rev-request", "rev-recd", "accepted"],
                                    date_type,
                                ),
                                date=_present(
                                    iso_date,
                                    evidence_ids,
                                    "correspondence-dd-mm-yyyy-to-iso-8601",
                                ),
                            )
                        )
                        seen_history.add(date_type)
                    continue
                labelled = list(_HISTORY_LABELLED.finditer(line))
                if labelled:
                    for item in labelled:
                        date_type = _HISTORY_TYPES[item.group("label").casefold()]
                        if date_type in seen_history:
                            review_reasons.append(f"duplicate_history_date:{date_type}")
                            continue
                        labelled_date = _history_iso_date(
                            item.group("date"),
                            self.profile.history_date_order.get(
                                _HISTORY_LANGUAGE[item.group("label").casefold()], "dmy"
                            ),
                        )
                        if labelled_date is None:
                            review_reasons.append(f"invalid_history_date:{date_type}")
                            continue
                        history_dates.append(
                            ArticleHistoryDate(
                                date_type=cast(
                                    Literal["received", "rev-request", "rev-recd", "accepted"],
                                    date_type,
                                ),
                                date=_present(
                                    labelled_date,
                                    evidence_ids,
                                    "correspondence-labelled-date-to-iso-8601",
                                ),
                            )
                        )
                        seen_history.add(date_type)
                    continue
                editor_type = next(
                    (
                        label
                        for label in ("Associate editor", "Scientific editor", "Editor")
                        if lowered.startswith(f"{label.casefold()}:")
                    ),
                    None,
                )
                if editor_type is not None:
                    value = line.split(":", 1)[1].strip()
                    if not value:
                        review_reasons.append(f"empty_{editor_type.casefold().replace(' ', '_')}")
                        continue
                    orcid_targets = paragraph_orcid_targets if editor_line_count == 1 else ()
                    if len(orcid_targets) == 1:
                        value = f"{value} {orcid_targets[0]}"
                    elif len(orcid_targets) > 1:
                        review_reasons.append("ambiguous_editor_orcid_hyperlinks")
                    notes.append(
                        NoteBlock(
                            id=stable_id(
                                article_id,
                                "correspondence-note",
                                f"{paragraph.id}:{line_position}:{editor_type.casefold()}",
                            ),
                            note_type=(
                                "edited-by"
                                if editor_type == "Editor"
                                else editor_type.casefold().replace(" ", "-")
                            ),
                            content=RichText(
                                plain=_present(
                                    value,
                                    evidence_ids,
                                    "correspondence-labeled-editor",
                                )
                            ),
                            evidence_ids=evidence_ids,
                        )
                    )
                    if not orcid_targets:
                        review_reasons.append(
                            f"{editor_type.casefold().replace(' ', '_')}_orcid_requires_enrichment"
                        )
                    continue
                review_reasons.append("unmapped_correspondence_line")

        return _CorrespondenceData(
            email=email,
            history_dates=tuple(history_dates),
            funding=tuple(funding),
            conflicts=conflicts,
            notes=tuple(notes),
            review_reasons=tuple(dict.fromkeys(review_reasons)),
        )

    def _notes(
        self,
        raw: RawArticle,
        character_names: dict[str, str],
        article_id: str,
    ) -> tuple[NoteBlock, ...]:
        story_by_note_id = {note_id: story for story in raw.stories for note_id in story.note_ids}
        hyperlinks_by_run = {
            link.source_id: target
            for link in raw.links
            if link.relationship == "external-hyperlink"
            and (target := _safe_external_href(link.target)) is not None
        }
        notes: list[NoteBlock] = []
        for position, note in enumerate(raw.notes):
            story = story_by_note_id.get(note.id)
            if story is None:
                continue
            paragraph = RawParagraph(
                id=stable_id(article_id, "note-paragraph", note.id),
                position=position,
                text_run_ids=note.text_run_ids,
                evidence_ids=note.evidence_ids,
            )
            notes.append(
                NoteBlock(
                    id=stable_id(article_id, "note", note.id),
                    note_type="footnote",
                    content=self._rich_text(
                        story,
                        paragraph,
                        character_names,
                        article_id,
                        run_ids=note.text_run_ids,
                        hyperlinks_by_run=hyperlinks_by_run,
                    ),
                    evidence_ids=note.evidence_ids,
                )
            )
        return tuple(notes)

    def _contributors(
        self,
        by_role: defaultdict[str, list[tuple[RawStory, RawParagraph]]],
        text_for: object,
        article_id: str,
        affiliation_ids: tuple[str, ...],
        raw: RawArticle,
        *,
        contribution_statement: SourcedText | None,
    ) -> tuple[Contributor, ...]:
        contributors: list[Contributor] = []
        roles_by_name = _credit_roles(contribution_statement)
        links_by_run = {
            link.source_id: link
            for link in raw.links
            if link.relationship == "external-hyperlink"
            and _ORCID_URL.fullmatch(link.target) is not None
        }
        style_by_id = {style.id: style for style in raw.styles}

        def superscript(run_style_id: str | None) -> bool:
            style = style_by_id.get(run_style_id or "")
            if style is None:
                return False
            name = style.normalized_name.casefold()
            position = str(style.properties.get("Position", "")).casefold()
            return "superscript" in name or "sobrescrito" in name or position == "superscript"

        for story, paragraph in by_role["contributors"]:
            value = text_for(story, paragraph)  # type: ignore[operator]
            paragraph_orcids = [
                links_by_run[run_id] for run_id in paragraph.text_run_ids if run_id in links_by_run
            ]
            run_by_id = {run.id: run for run in story.runs}
            marked = [
                (run_by_id[run_id].text, superscript(run_by_id[run_id].character_style_id))
                for run_id in paragraph.text_run_ids
                if run_id in run_by_id
            ]
            marked_ids = [run_id for run_id in paragraph.text_run_ids if run_id in run_by_id]
            author_runs: list[list[str]] = []
            if any(flag and _MARKER_TOKEN.search(text) for text, flag in marked):
                authors = _split_marked_authors(marked)
                author_runs = [
                    [marked_ids[index] for index in group] for group in _author_run_groups(marked)
                ]
            else:
                authors = [
                    (
                        " ".join(_AUTHOR_MARKERS.sub("", source).split()),
                        re.findall(r"\*|\d+", source),
                    )
                    for source in re.split(r"\s*,\s*", value)
                ]
            for position, (clean_name, marker_tokens) in enumerate(authors):
                source_name = clean_name + ("*" if "*" in marker_tokens else "")
                markers = [
                    index for token in marker_tokens if (index := _marker_index(token)) is not None
                ]
                parts = clean_name.split()
                if len(parts) < 2:
                    continue
                selected_affiliations = tuple(
                    dict.fromkeys(
                        affiliation_ids[index - 1]
                        for index in markers
                        if 0 < index <= len(affiliation_ids)
                    )
                )
                contributor_id = stable_id(article_id, "contributor", str(len(contributors)))
                own_links = (
                    [links_by_run[r] for r in author_runs[position] if r in links_by_run]
                    if position < len(author_runs)
                    else []
                )
                orcid_link = (
                    own_links[0]
                    if own_links
                    else None
                    if author_runs
                    else paragraph_orcids[position]
                    if position < len(paragraph_orcids)
                    else None
                )
                name_tokens = {
                    part.casefold()
                    for part in re.findall(r"[A-Za-z]+", clean_name)
                    if len(part) >= 4
                }
                matching_roles = [
                    roles
                    for name, roles in roles_by_name.items()
                    if name_tokens
                    & {part.casefold() for part in re.findall(r"[A-Za-z]+", name) if len(part) >= 4}
                ]
                if not matching_roles:
                    # "CEAL: Conceptualization, ..." identifies authors by their initials.
                    initials = _name_initials(clean_name)
                    matching_roles = [
                        roles for name, roles in roles_by_name.items() if name in initials
                    ]
                contributors.append(
                    Contributor(
                        id=contributor_id,
                        contributor_type="person",
                        name=ContributorName(
                            given_names=_present(
                                " ".join(parts[:-1]),
                                paragraph.evidence_ids,
                                "deterministic-last-token-name-split",
                            ),
                            surname=_present(
                                parts[-1],
                                paragraph.evidence_ids,
                                "deterministic-last-token-name-split",
                            ),
                        ),
                        orcid=(
                            _present(
                                orcid_link.target,
                                orcid_link.evidence_ids,
                                "source-authenticated-orcid-hyperlink",
                            )
                            if orcid_link is not None
                            else None
                        ),
                        affiliation_ids=selected_affiliations,
                        roles=matching_roles[0] if len(matching_roles) == 1 else (),
                        corresponding="*" in source_name,
                        evidence_ids=paragraph.evidence_ids,
                    )
                )
        return tuple(contributors)

    def _affiliations(
        self,
        by_role: defaultdict[str, list[tuple[RawStory, RawParagraph]]],
        text_for: object,
        article_id: str,
    ) -> tuple[Affiliation, ...]:
        affiliations: list[Affiliation] = []
        for story, paragraph in by_role["affiliations"]:
            value = text_for(story, paragraph)  # type: ignore[operator]
            for line in value.splitlines():
                clean = line.strip()
                if not clean:
                    continue
                clean = _strip_affiliation_label(clean, len(affiliations) + 1)
                match: re.Match[str] | _AffiliationParts | None = _AFFILIATION.fullmatch(clean)
                if match is None:
                    # "Institution - City, Country." without a department segment.
                    match = _AFFILIATION_NO_DEPARTMENT.fullmatch(clean)
                if isinstance(match, re.Match):
                    match = _split_trailing_country(match)
                if match is None:
                    institution = clean
                    original_text = department = city = state = country = country_code = None
                else:
                    values = {key: value.strip() for key, value in match.groupdict().items()}
                    institution = values["institution"]
                    original_text = _present(
                        clean,
                        paragraph.evidence_ids,
                        "line-from-affiliation-style",
                    )
                    department = (
                        _present(
                            values["department"],
                            paragraph.evidence_ids,
                            "deterministic-affiliation-decomposition",
                        )
                        if values.get("department")
                        else None
                    )
                    city_value, state_value = split_explicit_brazil_state(
                        values["city"], values["country"]
                    )
                    city = _present(
                        city_value,
                        paragraph.evidence_ids,
                        "deterministic-affiliation-decomposition",
                    )
                    state = (
                        _present(
                            state_value,
                            paragraph.evidence_ids,
                            "explicit-affiliation-parenthesized-uf",
                        )
                        if state_value
                        else None
                    )
                    country = _present(
                        values["country"],
                        paragraph.evidence_ids,
                        "deterministic-affiliation-decomposition",
                    )
                    code = self.profile.country_codes.get(values["country"])
                    generic_code = None if code else iso_country_code(values["country"])
                    country_code = (
                        _present(
                            code,
                            paragraph.evidence_ids,
                            "journal-profile-country-code",
                        )
                        if code
                        else _present(
                            generic_code,
                            paragraph.evidence_ids,
                            "cldr-country-name-to-iso-3166",
                        )
                        if generic_code
                        else None
                    )
                affiliations.append(
                    Affiliation(
                        id=stable_id(article_id, "affiliation", str(len(affiliations))),
                        institution=_present(
                            institution,
                            paragraph.evidence_ids,
                            "deterministic-affiliation-decomposition",
                        ),
                        original_text=original_text,
                        department=department,
                        city=city,
                        state_or_province=state,
                        country=country,
                        country_code=country_code,
                        evidence_ids=paragraph.evidence_ids,
                    )
                )
        return tuple(affiliations)

    def _rich_text(
        self,
        story: RawStory,
        paragraph: RawParagraph,
        character_names: dict[str, str],
        article_id: str,
        *,
        run_ids: tuple[str, ...] | None = None,
        inline_formulas_by_run: dict[str, list[RawAnchoredObject]] | None = None,
        raw_assets: dict[str, RawAsset] | None = None,
        formula_sources_by_object: dict[str, str] | None = None,
        hyperlinks_by_run: dict[str, str] | None = None,
    ) -> RichText:
        runs = {run.id: run for run in story.runs}
        inlines: list[InlineNode] = []
        plain = ""
        selected_run_ids = run_ids if run_ids is not None else paragraph.text_run_ids
        for run_id in selected_run_ids:
            run = runs[run_id]
            for formula_position, formula in enumerate(
                (inline_formulas_by_run or {}).get(run_id, ())
            ):
                asset_id = formula.asset_ids[0] if formula.asset_ids else None
                asset = (raw_assets or {}).get(asset_id or "")
                source = (
                    asset.logical_path
                    if asset is not None
                    else (formula_sources_by_object or {}).get(formula.id)
                )
                representation = (
                    FormulaRepresentation.IMAGE
                    if asset is not None
                    else FormulaRepresentation.TEXT
                    if source is not None
                    else FormulaRepresentation.UNKNOWN
                )
                inlines.append(
                    InlineNode(
                        id=stable_id(
                            article_id,
                            "inline-formula",
                            f"{paragraph.id}:{run_id}:{formula_position}",
                        ),
                        kind=InlineKind.INLINE_FORMULA,
                        text="",
                        formula_source=(
                            _present(
                                source,
                                formula.evidence_ids,
                                (
                                    "anchored-inline-pdf-formula"
                                    if asset is not None
                                    else "embedded-story-inline-formula"
                                ),
                            )
                            if source is not None
                            else SourcedText(
                                state=FieldState.NEEDS_REVIEW,
                                evidence_ids=formula.evidence_ids,
                                transformation="unresolved-inline-formula-source",
                                confidence=1.0,
                            )
                        ),
                        formula_representation=representation,
                        formula_asset_id=asset_id,
                        evidence_ids=formula.evidence_ids,
                    )
                )
            plain += run.text
            if not run.text:
                continue
            style_name = character_names.get(run.character_style_id or "", "")
            kind = InlineKind.TEXT
            is_italic = "italic" in style_name or "italico" in style_name
            is_bold = "bold" in style_name or "negrito" in style_name
            if "superscript" in style_name or "sobrescrito" in style_name:
                kind = InlineKind.SUPERSCRIPT
            elif "subscript" in style_name or "subscrito" in style_name:
                kind = InlineKind.SUBSCRIPT
            elif is_bold:
                kind = InlineKind.STRONG
            elif is_italic:
                kind = InlineKind.EMPHASIS
            attributes: dict[str, str] = {}
            if is_bold and is_italic:
                attributes["source-emphasis"] = "bold italic"
            href = (hyperlinks_by_run or {}).get(run_id)
            if href is not None:
                kind = InlineKind.EXTERNAL_LINK
                if is_bold or is_italic:
                    attributes["source-emphasis"] = " ".join(
                        name
                        for name, enabled in (("bold", is_bold), ("italic", is_italic))
                        if enabled
                    )
            inlines.append(
                InlineNode(
                    id=stable_id(article_id, "inline", f"{paragraph.id}:{run_id}"),
                    kind=kind,
                    text=run.text,
                    href=href,
                    attributes=attributes,
                    evidence_ids=run.evidence_ids,
                )
            )
        inlines = _insert_missing_inline_formula_nodes(
            inlines,
            plain=plain,
            paragraph=paragraph,
            article_id=article_id,
        )
        inlines = _mark_native_inline_assignments(
            inlines,
            plain=plain,
            paragraph=paragraph,
            article_id=article_id,
        )
        inlines = _group_pseudocode_inline_formulas(
            inlines,
            plain=plain,
            paragraph=paragraph,
            article_id=article_id,
        )
        return RichText(
            plain=SourcedText(
                value=plain or None,
                state=FieldState.PRESENT if plain.strip() else FieldState.NEEDS_REVIEW,
                evidence_ids=paragraph.evidence_ids,
                transformation="lossless-run-concatenation",
                confidence=1.0,
            ),
            inlines=tuple(inlines),
        )

    def _sections(
        self,
        raw: RawArticle,
        by_role: defaultdict[str, list[tuple[RawStory, RawParagraph]]],
        style_names: dict[str, str],
        character_names: dict[str, str],
        style_properties: dict[str, dict[str, str | int | float | bool | None]],
        article_id: str,
        references: tuple[Reference, ...],
        *,
        excluded_paragraph_ids: frozenset[str] = frozenset(),
        layout_table_ids: frozenset[str] = frozenset(),
    ) -> tuple[tuple[Section, ...], tuple[str, ...]]:
        embedded_story_sources = {
            anchored_object.source_self_id
            for anchored_object in raw.anchored_objects
            if not anchored_object.asset_ids
        }
        body_items = [
            (*item, role)
            for role in (
                *sorted(
                    (name for name in by_role if _SECTION_ROLE.fullmatch(name)),
                    key=lambda name: int(name.rsplit("-", 1)[1]),
                ),
                "paragraph",
                "list-level-1",
                "list-level-2",
            )
            for item in by_role[role]
            if item[1].id not in excluded_paragraph_ids
            and item[0].source_self_id not in embedded_story_sources
        ]
        body_items.sort(key=lambda item: (raw.reading_order.index(item[0].id), item[1].position))
        sections: list[dict[str, object]] = []
        section_stack: list[dict[str, object]] = []
        citation_review_reasons: list[str] = []
        formula_review_reasons: list[str] = []
        hyperlinks_by_run: dict[str, str] = {}
        for link in raw.links:
            if link.relationship != "external-hyperlink":
                continue
            if safe_target := _safe_external_href(link.target):
                hyperlinks_by_run[link.source_id] = safe_target
            else:
                citation_review_reasons.append(f"unsafe_external_hyperlink:{link.id}")
        raw_assets = {asset.id: asset for asset in raw.assets}
        story_by_source_self = {story.source_self_id: story for story in raw.stories}
        formula_sources_by_object = {
            anchored_object.id: "".join(
                run.text for run in story_by_source_self[anchored_object.source_self_id].runs
            ).strip()
            for anchored_object in raw.anchored_objects
            if not anchored_object.asset_ids
            and anchored_object.source_self_id in story_by_source_self
        }
        block_formulas_by_run: defaultdict[str, list[RawAnchoredObject]] = defaultdict(list)
        inline_formulas_by_run: defaultdict[str, list[RawAnchoredObject]] = defaultdict(list)
        last_inline_equation_asset_number = 0
        for anchored_object in raw.anchored_objects:
            if (
                anchored_object.kind == RawObjectKind.FORMULA
                and anchored_object.anchor_run_id is not None
            ):
                if anchored_object.placement == AnchoredPlacement.INLINE:
                    asset = raw_assets.get(
                        anchored_object.asset_ids[0] if anchored_object.asset_ids else ""
                    )
                    sequence_number = (
                        inline_equation_asset_number(asset.logical_path)
                        if asset is not None
                        else None
                    )
                    if sequence_number is not None:
                        if sequence_number <= last_inline_equation_asset_number:
                            continue
                        last_inline_equation_asset_number = sequence_number
                target = (
                    inline_formulas_by_run
                    if anchored_object.placement == AnchoredPlacement.INLINE
                    else block_formulas_by_run
                )
                target[anchored_object.anchor_run_id].append(anchored_object)
        current: dict[str, object] | None = None
        for story, paragraph, role in body_items:
            runs = {run.id: run for run in story.runs}
            text = "".join(runs[item].text for item in paragraph.text_run_ids).strip()
            block_formula_objects = [
                formula
                for run_id in paragraph.text_run_ids
                for formula in block_formulas_by_run.get(run_id, ())
            ]
            inline_formula_objects = [
                formula
                for run_id in paragraph.text_run_ids
                for formula in inline_formulas_by_run.get(run_id, ())
            ]
            if not text and not block_formula_objects and not inline_formula_objects:
                continue
            if section_match := _SECTION_ROLE.fullmatch(role):
                level = int(section_match.group(1))
                title = _section_title(text, level)
                current = {
                    "id": stable_id(article_id, "section", paragraph.id),
                    "title": _present(
                        title,
                        paragraph.evidence_ids,
                        f"style-role:{role}:normalized-heading-whitespace-and-case",
                    ),
                    "level": level,
                    "section_type": _section_type(text, level),
                    "blocks": [],
                    "children": [],
                    "evidence_ids": paragraph.evidence_ids,
                }
                while section_stack:
                    parent_level = section_stack[-1]["level"]
                    assert isinstance(parent_level, int)
                    if parent_level < level:
                        break
                    section_stack.pop()
                if section_stack:
                    children = section_stack[-1]["children"]
                    assert isinstance(children, list)
                    children.append(current)
                else:
                    sections.append(current)
                section_stack.append(current)
            else:
                if current is None:
                    current = {
                        "id": stable_id(article_id, "section", "untitled-body"),
                        "title": _missing("body-content-before-section-heading"),
                        "level": 1,
                        "blocks": [],
                        "children": [],
                        "evidence_ids": (),
                    }
                    sections.append(current)
                    section_stack.append(current)
                blocks = cast(list[object], current["blocks"])
                properties = style_properties.get(paragraph.paragraph_style_id or "", {})
                list_type = str(properties.get("BulletsAndNumberingListType", ""))
                if list_type in {"BulletList", "NumberedList"} or role.startswith("list-level-"):
                    content = self._rich_text(
                        story,
                        paragraph,
                        character_names,
                        article_id,
                        inline_formulas_by_run=inline_formulas_by_run,
                        raw_assets=raw_assets,
                        formula_sources_by_object=formula_sources_by_object,
                        hyperlinks_by_run=hyperlinks_by_run,
                    )
                    line_markers = tuple(_LIST_LINE_MARKER.finditer(content.plain.value or ""))
                    item_contents: list[RichText] = []
                    if len(line_markers) > 1 and line_markers[0].start() == 0:
                        for position, marker in enumerate(line_markers):
                            end = (
                                line_markers[position + 1].start()
                                if position + 1 < len(line_markers)
                                else len(content.plain.value or "")
                            )
                            item_content = _rich_text_slice(
                                content,
                                marker.end(),
                                end,
                                article_id=article_id,
                                locator=f"list:{paragraph.id}:{position}",
                            )
                            if item_content is not None:
                                item_contents.append(
                                    item_content.model_copy(
                                        update={
                                            "plain": item_content.plain.model_copy(
                                                update={
                                                    "transformation": (
                                                        "numbered-lines-split-and-markers-extracted"
                                                    )
                                                }
                                            )
                                        }
                                    )
                                )
                    else:
                        if single_marker := _LIST_MARKER.match(content.plain.value or ""):
                            content = _without_prefix(content, single_marker.end())
                        item_contents.append(content)
                    formula_review_reasons.extend(
                        f"inline_formula_requires_mathml_transcription:{inline.id}"
                        for item_content in item_contents
                        for inline in item_content.inlines
                        if inline.kind == InlineKind.INLINE_FORMULA
                        and inline.formula_source is not None
                        and inline.formula_source.transformation == "native-inline-formula-source"
                    )
                    items = tuple(
                        ListItem(
                            id=stable_id(article_id, "list-item", f"{paragraph.id}:{position}"),
                            content=item_content,
                            evidence_ids=paragraph.evidence_ids,
                        )
                        for position, item_content in enumerate(item_contents)
                    )
                    ordered = list_type == "NumberedList" or bool(re.match(r"^\s*\d+[.)]", text))
                    if (
                        blocks
                        and isinstance(blocks[-1], ListBlock)
                        and blocks[-1].ordered == ordered
                    ):
                        previous_list = blocks[-1]
                        blocks[-1] = previous_list.model_copy(
                            update={
                                "items": (*previous_list.items, *items),
                                "evidence_ids": tuple(
                                    dict.fromkeys(
                                        (*previous_list.evidence_ids, *paragraph.evidence_ids)
                                    )
                                ),
                            }
                        )
                    else:
                        blocks.append(
                            ListBlock(
                                id=stable_id(article_id, "list", paragraph.id),
                                ordered=ordered,
                                items=items,
                                evidence_ids=paragraph.evidence_ids,
                            )
                        )
                    continue

                def append_paragraph(
                    run_ids: list[str],
                    segment: int,
                    story: RawStory = story,
                    paragraph: RawParagraph = paragraph,
                    block_formula_objects: list[RawAnchoredObject] = block_formula_objects,
                    blocks: list[object] = blocks,
                    inline_formula_objects: list[RawAnchoredObject] = inline_formula_objects,
                ) -> None:
                    if not run_ids:
                        return
                    rich_text = self._rich_text(
                        story,
                        paragraph,
                        character_names,
                        article_id,
                        run_ids=tuple(run_ids),
                        inline_formulas_by_run=inline_formulas_by_run,
                        raw_assets=raw_assets,
                        formula_sources_by_object=formula_sources_by_object,
                        hyperlinks_by_run=hyperlinks_by_run,
                    )
                    if block_formula_objects:
                        plain_with_label = rich_text.plain.value or ""
                        leading_label = re.match(r"^\s*(\([1-9]\d*\))\s*", plain_with_label)
                        known_labels = {
                            formula.label for formula in block_formula_objects if formula.label
                        }
                        if leading_label and leading_label.group(1) in known_labels:
                            rich_text = _without_prefix(rich_text, leading_label.end())
                    formula_review_reasons.extend(
                        f"inline_formula_requires_mathml_transcription:{inline.id}"
                        for inline in rich_text.inlines
                        if inline.kind == InlineKind.INLINE_FORMULA
                        and inline.formula_source is not None
                        and inline.formula_source.transformation == "native-inline-formula-source"
                    )
                    if rich_text.plain.value is None and not any(
                        inline.kind == InlineKind.INLINE_FORMULA for inline in rich_text.inlines
                    ):
                        return
                    paragraph_locator = (
                        paragraph.id
                        if not block_formula_objects
                        else f"{paragraph.id}:segment:{segment}"
                    )
                    plain_value = rich_text.plain.value or ""
                    native_formulas = _native_display_formulas(plain_value)

                    def append_text_part(
                        part_content: RichText,
                        part: int,
                        *,
                        split: bool,
                    ) -> None:
                        paragraph_id = stable_id(
                            article_id,
                            "paragraph",
                            f"{paragraph_locator}:part:{part}" if split else paragraph_locator,
                        )
                        citation_resolution = resolve_citations(
                            part_content,
                            references,
                            article_id=article_id,
                            paragraph_id=paragraph_id,
                        )
                        blocks.append(
                            Paragraph(
                                id=paragraph_id,
                                content=citation_resolution.content,
                                cross_references=citation_resolution.cross_references,
                                evidence_ids=paragraph.evidence_ids,
                            )
                        )
                        citation_review_reasons.extend(citation_resolution.review_reasons)
                        text_value = citation_resolution.content.plain.value or ""
                        for match in re.finditer(r"(?m)^[ \t]*:[ \t]+\S", text_value):
                            formula_review_reasons.append(
                                f"possible_missing_inline_formula:{paragraph.id}:{match.start()}"
                            )

                    if native_formulas:
                        cursor = 0
                        for formula_position, native_formula in enumerate(native_formulas):
                            before = _rich_text_slice(
                                rich_text,
                                cursor,
                                native_formula.start,
                                article_id=article_id,
                                locator=f"{paragraph_locator}:part:{formula_position}",
                            )
                            if before is not None:
                                append_text_part(before, formula_position, split=True)
                            formula_id = stable_id(
                                article_id,
                                "native-display-formula",
                                f"{paragraph.id}:{native_formula.label}",
                            )
                            blocks.append(
                                FormulaBlock(
                                    id=formula_id,
                                    display=True,
                                    source=_present(
                                        native_formula.source,
                                        paragraph.evidence_ids,
                                        "source-native-display-formula",
                                    ),
                                    representation=FormulaRepresentation.TEXT,
                                    label=_present(
                                        native_formula.label,
                                        paragraph.evidence_ids,
                                        "source-native-formula-label",
                                    ),
                                    evidence_ids=paragraph.evidence_ids,
                                )
                            )
                            formula_review_reasons.append(
                                f"native_formula_requires_mathml_transcription:{formula_id}"
                            )
                            cursor = native_formula.end
                        after = _rich_text_slice(
                            rich_text,
                            cursor,
                            len(plain_value),
                            article_id=article_id,
                            locator=f"{paragraph_locator}:part:{len(native_formulas)}",
                        )
                        if after is not None:
                            append_text_part(after, len(native_formulas), split=True)
                    else:
                        append_text_part(rich_text, 0, split=False)
                    for inline_formula in inline_formula_objects:
                        if inline_formula.anchor_run_id not in run_ids:
                            continue
                        formula_review_reasons.append(
                            f"inline_formula_requires_mathml_transcription:{inline_formula.id}"
                        )

                def append_formula(
                    formula: RawAnchoredObject,
                    blocks: list[object] = blocks,
                ) -> None:
                    asset_id = formula.asset_ids[0] if formula.asset_ids else None
                    asset = raw_assets.get(asset_id or "")
                    source = asset.logical_path if asset is not None else "unresolved-formula-asset"
                    blocks.append(
                        FormulaBlock(
                            id=stable_id(article_id, "formula", formula.id),
                            display=True,
                            source=_present(
                                source,
                                formula.evidence_ids,
                                "anchored-pdf-formula",
                            ),
                            representation=FormulaRepresentation.IMAGE,
                            label=(
                                _present(
                                    formula.label,
                                    formula.evidence_ids,
                                    "anchored-formula-label",
                                )
                                if formula.label
                                else None
                            ),
                            asset_id=asset_id,
                            evidence_ids=formula.evidence_ids,
                        )
                    )
                    formula_review_reasons.append(
                        f"formula_requires_mathml_transcription:{formula.id}"
                    )

                segment_run_ids: list[str] = []
                segment = 0
                for run_id in paragraph.text_run_ids:
                    formulas = block_formulas_by_run.get(run_id, ())
                    if formulas:
                        append_paragraph(segment_run_ids, segment)
                        segment += 1
                        segment_run_ids = []
                        for formula in formulas:
                            append_formula(formula)
                    else:
                        segment_run_ids.append(run_id)
                append_paragraph(segment_run_ids, segment)

        raw_tables = {table.id: table for table in raw.tables if table.id not in layout_table_ids}
        story_by_table = {table_id: story for story in raw.stories for table_id in story.table_ids}
        table_story = {table_id: story.id for table_id, story in story_by_table.items()}
        story_page = {
            story.id: min(
                (frame.page_index for frame in raw.frames if frame.parent_story_id == story.id),
                default=10**9,
            )
            for story in raw.stories
        }
        story_order = {story_id: position for position, story_id in enumerate(raw.reading_order)}
        captions = by_role["caption"]
        used_table_footnotes: set[str] = set()
        graphic_blocks: list[FigureBlock | TableBlock] = []
        graphic_review_reasons: list[str] = [
            *citation_review_reasons,
            *formula_review_reasons,
        ]
        used_tables: set[str] = set()
        used_assets: set[str] = set()
        figure_asset_ids = {
            asset_id
            for anchored_object in raw.anchored_objects
            if anchored_object.kind == RawObjectKind.FIGURE
            for asset_id in anchored_object.asset_ids
        }
        figure_assets_by_number: defaultdict[int, list[RawAsset]] = defaultdict(list)
        for raw_asset in raw.assets:
            number = figure_asset_number(raw_asset.logical_path)
            if raw_asset.id in figure_asset_ids and number is not None:
                figure_assets_by_number[number].append(raw_asset)
        for candidates in figure_assets_by_number.values():
            candidates.sort(key=lambda item: (item.logical_path.casefold(), item.id))
        recognized_figure_asset_ids = {
            item.id for candidates in figure_assets_by_number.values() for item in candidates
        }
        run_lookup = {run.id: run for item in raw.stories for run in item.runs}

        def caption_kind(story: RawStory, paragraph: RawParagraph) -> str | None:
            value = "".join(run_lookup[item].text for item in paragraph.text_run_ids)
            match = _NUMBERED_GRAPHIC.match(value)
            if match is None or _CONTINUATION_CAPTION.match(value[match.end() :]):
                return None
            return _caption_family(match.group(1))

        table_caption_keys = sorted(
            (story_order[story.id], paragraph.position)
            for story, paragraph in captions
            if caption_kind(story, paragraph) == "table"
        )

        def table_rows(table_id: str) -> tuple[tuple[RichText, ...], ...]:
            table = raw_tables[table_id]
            rows: list[tuple[RichText, ...]] = []
            for row_index in range(table.row_count):
                row: list[RichText] = []
                for column_index in range(table.column_count):
                    cell = next(
                        (
                            item
                            for item in table.cells
                            if item.row == row_index and item.column == column_index
                        ),
                        None,
                    )
                    value = (
                        "".join(run_lookup[item].text for item in cell.text_run_ids) if cell else ""
                    )
                    if value.strip() and cell:
                        source_story = story_by_table[table_id]
                        source_paragraph = next(
                            (
                                paragraph
                                for paragraph in source_story.paragraphs
                                if paragraph.table_cell_id == cell.id
                            ),
                            RawParagraph(
                                id=stable_id(article_id, "table-cell-paragraph", cell.id),
                                position=0,
                                text_run_ids=cell.text_run_ids,
                                table_cell_id=cell.id,
                                evidence_ids=cell.evidence_ids,
                            ),
                        )
                        cell_rich = self._rich_text(
                            source_story,
                            source_paragraph,
                            character_names,
                            article_id,
                            run_ids=cell.text_run_ids,
                            hyperlinks_by_run=hyperlinks_by_run,
                        )
                    else:
                        cell_rich = RichText(plain=_missing("empty-or-spanned-table-cell"))
                    if value.strip() and cell:
                        cell_resolution = resolve_citations(
                            cell_rich,
                            references,
                            article_id=article_id,
                            paragraph_id=stable_id(
                                article_id,
                                "table-cell",
                                f"{table_id}:{row_index}:{column_index}",
                            ),
                        )
                        cell_rich = cell_resolution.content
                        graphic_review_reasons.extend(cell_resolution.review_reasons)
                    row.append(cell_rich)
                rows.append(tuple(row))
            return tuple(rows)

        def table_header_rows(table_id: str) -> int:
            """Count leading rows whose filled cells all use the profile's header style."""
            table = raw_tables[table_id]
            source_story = story_by_table[table_id]
            paragraphs_by_cell: defaultdict[str, list[RawParagraph]] = defaultdict(list)
            for item in source_story.paragraphs:
                if item.table_cell_id:
                    paragraphs_by_cell[item.table_cell_id].append(item)
            header = 0
            for row_index in range(table.row_count - 1):
                filled = [
                    cell
                    for cell in table.cells
                    if cell.row == row_index
                    and "".join(run_lookup[item].text for item in cell.text_run_ids).strip()
                ]
                roles = {
                    self.profile.role_for_style(
                        style_names.get(item.paragraph_style_id or "", ""),
                        style_prefix(style_names.get(item.paragraph_style_id or "", "")),
                    )
                    for cell in filled
                    for item in paragraphs_by_cell[cell.id]
                }
                if not filled or roles != {"table-heading"}:
                    break
                header += 1
            return header

        def table_cell_spans(table_id: str) -> tuple[TableCellSpan, ...]:
            return tuple(
                TableCellSpan(
                    row=cell.row,
                    column=cell.column,
                    row_span=cell.row_span,
                    column_span=cell.column_span,
                )
                for cell in raw_tables[table_id].cells
                if cell.row_span > 1 or cell.column_span > 1
            )

        for story, paragraph in captions:
            runs = {run.id: run for run in story.runs}
            caption_value = "".join(runs[item].text for item in paragraph.text_run_ids)
            numbered = _NUMBERED_GRAPHIC.match(caption_value)
            if numbered is None:
                if caption_value.strip():
                    graphic_review_reasons.append(f"unnumbered_graphic_caption:{paragraph.id}")
                continue
            if _CONTINUATION_CAPTION.match(caption_value[numbered.end() :]):
                continue
            label_word = numbered.group(1)
            kind, number_text = _caption_family(label_word), numbered.group(2)
            number = int(number_text)
            caption_source = (
                self._rich_text(
                    story,
                    paragraph,
                    character_names,
                    article_id,
                    hyperlinks_by_run=hyperlinks_by_run,
                )
                if caption_value.strip()
                else RichText(plain=_missing("caption-style-contained-no-caption-text"))
            )
            separator = _CAPTION_SEPARATOR.match(caption_value[numbered.end() :])
            prefix_length = numbered.end() + (separator.end() if separator else 0)
            caption_source = _without_prefix(caption_source, prefix_length)
            caption = caption_source
            if caption_value.strip():
                caption_resolution = resolve_citations(
                    caption_source,
                    references,
                    article_id=article_id,
                    paragraph_id=stable_id(article_id, "caption", paragraph.id),
                )
                caption = caption_resolution.content
                graphic_review_reasons.extend(caption_resolution.review_reasons)
            if kind == "table":
                candidate_tables = sorted(
                    (
                        table_id
                        for table_id in raw_tables
                        if table_id not in used_tables
                        and story_page.get(table_story.get(table_id, ""), 10**9)
                        == story_page.get(story.id, 10**9)
                    ),
                    key=lambda table_id: (
                        raw.reading_order.index(table_story[table_id]),
                        raw_tables[table_id].source_self_id,
                    ),
                )
                if not candidate_tables:
                    graphic_review_reasons.append(f"unmatched_table_caption:{number}")
                    continue
                table_id = candidate_tables[0]
                used_tables.add(table_id)
                table = raw_tables[table_id]
                caption_key = (story_order[story.id], paragraph.position)
                next_caption_key = next(
                    (position for position in table_caption_keys if position > caption_key),
                    (len(raw.reading_order), 0),
                )
                table_footnotes = tuple(
                    self._rich_text(
                        footnote_story,
                        footnote_paragraph,
                        character_names,
                        article_id,
                        hyperlinks_by_run=hyperlinks_by_run,
                    )
                    for footnote_story, footnote_paragraph in by_role["table-footnote"]
                    if footnote_paragraph.id not in used_table_footnotes
                    and story_page.get(footnote_story.id, 10**9) == story_page.get(story.id, 10**9)
                    and caption_key
                    < (
                        story_order.get(footnote_story.id, len(raw.reading_order)),
                        footnote_paragraph.position,
                    )
                    < next_caption_key
                )
                used_table_footnotes.update(
                    footnote_paragraph.id
                    for footnote_story, footnote_paragraph in by_role["table-footnote"]
                    if story_page.get(footnote_story.id, 10**9) == story_page.get(story.id, 10**9)
                    and caption_key
                    < (
                        story_order.get(footnote_story.id, len(raw.reading_order)),
                        footnote_paragraph.position,
                    )
                    < next_caption_key
                )
                graphic_blocks.append(
                    TableBlock(
                        id=stable_id(article_id, "canonical-table", table.id),
                        label=_present(
                            _caption_label(label_word, number),
                            paragraph.evidence_ids,
                            "numbered-caption-label",
                        ),
                        caption=caption,
                        rows=table_rows(table_id),
                        cell_spans=table_cell_spans(table_id),
                        footnotes=table_footnotes,
                        evidence_ids=table.evidence_ids,
                        header_rows=table_header_rows(table_id),
                    )
                )
            else:
                matching_assets = [
                    item for item in figure_assets_by_number[number] if item.id not in used_assets
                ]
                if len(matching_assets) == 1:
                    asset = matching_assets[0]
                    used_assets.add(asset.id)
                    asset_id = asset.id
                elif not matching_assets:
                    graphic_review_reasons.append(f"unmatched_figure_asset:{number}")
                    asset_id = None
                else:
                    graphic_review_reasons.append(f"ambiguous_figure_asset:{number}")
                    asset_id = None
                graphic_blocks.append(
                    FigureBlock(
                        id=stable_id(article_id, "figure", paragraph.id),
                        label=_present(
                            _caption_label(label_word, number),
                            paragraph.evidence_ids,
                            "numbered-caption-label",
                        ),
                        caption=caption,
                        asset_id=asset_id,
                        evidence_ids=paragraph.evidence_ids,
                    )
                )

        def graphic_number(block: FigureBlock | TableBlock) -> int:
            match = re.search(r"\d+", block.label.value or "")
            return int(match.group()) if match else 10**9

        ordered_figures = iter(
            sorted(
                (block for block in graphic_blocks if isinstance(block, FigureBlock)),
                key=graphic_number,
            )
        )
        ordered_tables = iter(
            sorted(
                (block for block in graphic_blocks if isinstance(block, TableBlock)),
                key=graphic_number,
            )
        )
        graphic_blocks = [
            next(ordered_figures) if isinstance(block, FigureBlock) else next(ordered_tables)
            for block in graphic_blocks
        ]

        def place_after_first_mention(
            block: FigureBlock | TableBlock,
            candidates: list[dict[str, object]],
        ) -> bool:
            label = block.label.value or ""
            label_match = _NUMBERED_GRAPHIC.match(label)
            if label_match is None:
                return False
            kind, number = label_match.groups()
            mention = re.compile(rf"\b{re.escape(kind)}\s*0*{int(number)}\b", re.IGNORECASE)
            for section in candidates:
                blocks = cast(list[object], section["blocks"])
                for position, existing in enumerate(blocks):
                    if not isinstance(existing, Paragraph):
                        continue
                    if not mention.search(existing.content.plain.value or ""):
                        continue
                    insertion = position + 1
                    while insertion < len(blocks) and isinstance(
                        blocks[insertion], (FigureBlock, TableBlock)
                    ):
                        insertion += 1
                    blocks.insert(insertion, block)
                    return True
                children = cast(list[dict[str, object]], section["children"])
                if place_after_first_mention(block, children):
                    return True
            return False

        placed_graphics: set[str] = set()
        unplaced_graphics: list[FigureBlock | TableBlock] = []
        for block in graphic_blocks:
            if place_after_first_mention(block, sections):
                placed_graphics.add(block.id)
            else:
                unplaced_graphics.append(block)

        def section_graphic_location(
            graphic_id: str,
            candidates: list[dict[str, object]],
        ) -> tuple[list[object], int] | None:
            for section in candidates:
                blocks = cast(list[object], section["blocks"])
                for position, existing in enumerate(blocks):
                    if (
                        isinstance(existing, (FigureBlock, TableBlock))
                        and existing.id == graphic_id
                    ):
                        return blocks, position
                children = cast(list[dict[str, object]], section["children"])
                if location := section_graphic_location(graphic_id, children):
                    return location
            return None

        def place_by_graphic_order(block: FigureBlock | TableBlock) -> bool:
            number = graphic_number(block)
            same_kind = [
                candidate
                for candidate in graphic_blocks
                if isinstance(candidate, type(block)) and candidate.id in placed_graphics
            ]
            following = min(
                (candidate for candidate in same_kind if graphic_number(candidate) > number),
                key=graphic_number,
                default=None,
            )
            if following is not None:
                location = section_graphic_location(following.id, sections)
                if location is not None:
                    blocks, position = location
                    blocks.insert(position, block)
                    return True
            preceding = max(
                (candidate for candidate in same_kind if graphic_number(candidate) < number),
                key=graphic_number,
                default=None,
            )
            if preceding is not None:
                location = section_graphic_location(preceding.id, sections)
                if location is not None:
                    blocks, position = location
                    insertion = position + 1
                    while insertion < len(blocks) and isinstance(blocks[insertion], type(block)):
                        insertion += 1
                    blocks.insert(insertion, block)
                    return True
            return False

        still_unplaced: list[FigureBlock | TableBlock] = []
        for block in sorted(unplaced_graphics, key=graphic_number):
            if place_by_graphic_order(block):
                placed_graphics.add(block.id)
                graphic_review_reasons.append(
                    f"graphic_placement_by_number:{block.kind}:{graphic_number(block)}"
                )
            else:
                still_unplaced.append(block)
        if still_unplaced and sections:
            target_blocks = cast(list[object], sections[-1]["blocks"])
            target_blocks.extend(still_unplaced)
            for block in still_unplaced:
                graphic_review_reasons.append(
                    f"graphic_placement_at_body_end:{block.kind}:{graphic_number(block)}"
                )
        elif still_unplaced:
            sections.append(
                {
                    "id": stable_id(article_id, "section", "graphic-elements"),
                    "title": _present(
                        "Elementos gráficos",
                        (),
                        "deterministic-container-label",
                    ),
                    "level": 1,
                    "blocks": still_unplaced,
                    "children": [],
                    "evidence_ids": (),
                }
            )
            graphic_review_reasons.append("graphic_container_created_for_body_without_sections")
        for table_id in sorted(set(raw_tables) - used_tables):
            graphic_review_reasons.append(f"unmatched_source_table:{table_id}")
        for _, paragraph in by_role["table-footnote"]:
            if paragraph.id not in used_table_footnotes:
                graphic_review_reasons.append(f"unmatched_table_footnote:{paragraph.id}")
        for asset_id in sorted(recognized_figure_asset_ids - used_assets):
            graphic_review_reasons.append(f"unmatched_source_figure_asset:{asset_id}")
        return (
            tuple(Section.model_validate(item) for item in sections),
            tuple(graphic_review_reasons),
        )

    def _references(
        self,
        by_role: defaultdict[str, list[tuple[RawStory, RawParagraph]]],
        text_for: object,
        article_id: str,
    ) -> tuple[Reference, ...]:
        references: list[Reference] = []
        for story, paragraph in by_role["references"]:
            value = text_for(story, paragraph)  # type: ignore[operator]
            for line in value.splitlines():
                if not line.strip():
                    continue
                source_line = line.strip()
                reference_id = stable_id(article_id, "reference", str(len(references)))
                doi_match = _REFERENCE_DOI.search(source_line)
                publication_year = _REFERENCE_PUBLICATION_YEAR.search(source_line)
                year_matches = _REFERENCE_YEAR.findall(source_line)
                year = (
                    publication_year.group(1)
                    if publication_year is not None
                    else (year_matches[-1] if year_matches else None)
                )
                if self.profile.reference_style == "vancouver":
                    parsed = parse_vancouver(source_line)
                    authors, title, source = parsed.authors, parsed.title, parsed.source
                    year = parsed.year or year
                    details = {
                        key: value
                        for key, value in (
                            ("volume", parsed.volume),
                            ("issue", parsed.issue),
                            ("first_page", parsed.first_page),
                            ("last_page", parsed.last_page or parsed.first_page),
                            ("elocation_id", parsed.elocation_id),
                        )
                        if value
                    }
                    metadata = reference_metadata(source_line, title, source)
                    if parsed.publication_type:
                        metadata = dataclasses.replace(
                            metadata,
                            publication_type=cast(ReferenceType, parsed.publication_type),
                        )
                else:
                    authors, title, source = _reference_parts(source_line)
                    details = _reference_details(source_line, year)
                    metadata = reference_metadata(source_line, title, source)
                    additions = dict(metadata.fields)
                    title = additions.pop("title", title)
                    source = additions.pop("source", source)
                    year = additions.pop("year", year)
                    details.update(additions)
                references.append(
                    Reference(
                        id=reference_id,
                        publication_type=metadata.publication_type,
                        review_reasons=metadata.review_reasons,
                        editors=tuple(
                            _present(editor, paragraph.evidence_ids, "literal-reference-editor")
                            for editor in metadata.editors
                        ),
                        mixed_citation=RichText(
                            plain=_present(
                                source_line,
                                paragraph.evidence_ids,
                                "line-break-reference-split",
                            )
                        ),
                        identifiers=(
                            (
                                Identifier(
                                    kind="doi",
                                    value=_present(
                                        doi_match.group(0).rstrip(".,;"),
                                        paragraph.evidence_ids,
                                        "deterministic-reference-doi-extraction",
                                    ),
                                ),
                            )
                            if doi_match
                            else ()
                        ),
                        year=(
                            _present(
                                year,
                                paragraph.evidence_ids,
                                "deterministic-reference-year-extraction",
                            )
                            if year
                            else None
                        ),
                        authors=tuple(
                            _present(
                                author,
                                paragraph.evidence_ids,
                                "deterministic-reference-author-split",
                            )
                            for author in authors
                        ),
                        title=(
                            _present(
                                title,
                                paragraph.evidence_ids,
                                "deterministic-reference-title-extraction",
                            )
                            if title
                            else None
                        ),
                        source=(
                            _present(
                                source,
                                paragraph.evidence_ids,
                                "deterministic-reference-source-extraction",
                            )
                            if source
                            else None
                        ),
                        **{
                            key: _present(
                                value,
                                paragraph.evidence_ids,
                                f"deterministic-reference-{key.replace('_', '-')}-extraction",
                            )
                            for key, value in details.items()
                        },
                        evidence_ids=paragraph.evidence_ids,
                    )
                )
        return tuple(references)
