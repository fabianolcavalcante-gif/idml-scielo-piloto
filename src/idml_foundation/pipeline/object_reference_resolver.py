from __future__ import annotations

import re
from typing import Any

from idml_foundation.domain.canonical import (
    CanonicalArticle,
    FigureBlock,
    FormulaBlock,
    Section,
    TableBlock,
)
from idml_foundation.domain.common import stable_id

_MENTION = re.compile(
    r"(?i)\b(?P<kind>fig(?:ure)?s?|figuras?|tables?|tabelas?|charts?|quadros?|equations?)\.?\s*"
    r"(?:\(\s*)?(?P<number>[1-9]\d*)(?:\s*\))?(?:[a-z])?"
)
_TEXTUAL_INLINE_KINDS = {
    "text",
    "emphasis",
    "strong",
    "subscript",
    "superscript",
    "named_content",
}
_FORMULA_PAIR = re.compile(
    r"(?i)\bequations[ \t\u00a0]+(?P<first>[1-9]\d*)"
    r"[ \t\u00a0]+and[ \t\u00a0]+(?P<second>[1-9]\d*)"
    r"(?![\w]|\.\d|[ \t\u00a0]*(?:[-\u2013]|,[ \t\u00a0]*(?:and[ \t\u00a0]+)?\d|and\b))"
)
_FOLLOWING_FORMULA = re.compile(r"(?i)\bwe have(?=:[ \t\r\n]*\Z)")


def _link_literal_span(
    rich: dict[str, Any],
    start: int,
    end: int,
    target: str,
    *,
    article_id: str,
    path: str,
    additional_evidence: list[str] | None = None,
) -> bool:
    """Only split one plain-text inline; never overwrite links, formatting or formulae."""
    offset = 0
    inlines = rich["inlines"]
    if not inlines:
        inlines.append(
            {
                "id": stable_id(article_id, "literal-object-source", path),
                "kind": "text",
                "text": rich["plain"]["value"],
                "target_id": None,
                "evidence_ids": rich["plain"].get("evidence_ids", []),
            }
        )
    for position, inline in enumerate(inlines):
        text = inline["text"]
        if offset <= start < end <= offset + len(text):
            if inline["kind"] != "text":
                return False
            left, right = start - offset, end - offset
            locator = f"{path}:{inline['id']}:{left}:{right}:{target}"
            evidence = list(
                dict.fromkeys([*inline.get("evidence_ids", []), *(additional_evidence or [])])
            )
            linked = {
                **inline,
                "id": stable_id(article_id, "literal-object-xref", locator),
                "kind": "cross_reference",
                "text": text[left:right],
                "target_id": target,
                "evidence_ids": evidence,
            }
            parts = []
            if left:
                parts.append(
                    {
                        **inline,
                        "id": stable_id(article_id, "xref-prefix", locator),
                        "text": text[:left],
                    }
                )
            parts.append(linked)
            if right < len(text):
                parts.append(
                    {
                        **inline,
                        "id": stable_id(article_id, "xref-suffix", locator),
                        "text": text[right:],
                    }
                )
            inlines[position : position + 1] = parts
            return True
        offset += len(text)
    return False


def _formula_pair_tails(
    rich: dict[str, Any],
    *,
    targets: dict[tuple[str, int], str],
    article_id: str,
    path: str,
) -> None:
    """Qualified grammar: 'Equations N and M', not ranges or unlabelled numbers."""
    for match in _FORMULA_PAIR.finditer(rich["plain"]["value"]):
        first = targets.get(("formula", int(match["first"])))
        second = targets.get(("formula", int(match["second"])))
        if not first or not second or first == second:
            continue
        offset = 0
        for inline in rich["inlines"]:
            stop = offset + len(inline["text"])
            if offset == match.start() and stop == match.end("first"):
                if inline["kind"] == "cross_reference" and inline["target_id"] == first:
                    _link_literal_span(
                        rich,
                        match.start("second"),
                        match.end("second"),
                        second,
                        article_id=article_id,
                        path=path,
                    )
                break
            offset = stop


def _following_formulas(sections: list[dict[str, Any]], *, article_id: str) -> None:
    def empty(block: dict[str, Any]) -> bool:
        return (
            block.get("kind") == "paragraph"
            and not (block["content"]["plain"]["value"] or "").strip()
            and all(i["kind"] == "text" for i in block["content"]["inlines"])
            and not block.get("cross_references")
        )

    for section in sections:
        # Empty layout paragraphs may intervene; no content/object/section may.
        blocks = [b for b in section["blocks"] if not empty(b)]
        for index, paragraph in enumerate(blocks[:-1]):
            formula = blocks[index + 1]
            if paragraph.get("kind") != "paragraph" or formula.get("kind") != "formula":
                continue
            if not formula.get("display") or not (formula.get("label") or {}).get("value"):
                continue
            # More than one following formula is ambiguous even with a leading phrase.
            if index + 2 < len(blocks) and blocks[index + 2].get("kind") == "formula":
                continue
            rich = paragraph["content"]
            match = _FOLLOWING_FORMULA.search(rich["plain"]["value"] or "")
            if match:
                _link_literal_span(
                    rich,
                    match.start(),
                    match.end(),
                    formula["id"],
                    article_id=article_id,
                    path=paragraph["id"],
                    additional_evidence=formula.get("evidence_ids", []),
                )
        _following_formulas(section["children"], article_id=article_id)


_NAMESPACES = {"tabela": "table", "quadro": "chart", "figura": "figure"}


def _label_namespace(word: str) -> str:
    """Numbering namespace of a label word: 'Chart 1' and 'Table 1' are different objects."""
    base = word.split()[0].casefold().rstrip("s.") if word.split() else "table"
    return _NAMESPACES.get(base, base)


def _targets(article: CanonicalArticle) -> dict[tuple[str, int], str]:
    found: dict[tuple[str, int], str] = {}

    def visit(section: Section) -> None:
        for block in section.blocks:
            if isinstance(block, FigureBlock):
                kind, label = "figure", block.label.value
            elif isinstance(block, TableBlock):
                kind, label = _label_namespace(block.label.value or "table"), block.label.value
            elif isinstance(block, FormulaBlock):
                kind, label = "formula", block.label.value if block.label else None
            else:
                continue
            if label and (match := re.search(r"[1-9]\d*", label)):
                key = (kind, int(match.group(0)))
                if key in found:
                    raise ValueError(f"duplicate numbered object target: {kind} {key[1]}")
                found[key] = block.id
        for child in section.children:
            visit(child)

    for root in article.body:
        visit(root)
    return found


def _target_key(match: re.Match[str]) -> tuple[str, int]:
    source_kind = match.group("kind").casefold()
    kind = "figure" if source_kind.startswith("fig") else _label_namespace(source_kind)
    if kind == "equation":
        kind = "formula"
    return kind, int(match.group("number"))


def _split_inline(
    inline: dict[str, Any],
    *,
    targets: dict[tuple[str, int], str],
    article_id: str,
    path: str,
) -> list[dict[str, Any]]:
    text = str(inline.get("text", ""))
    matches = [match for match in _MENTION.finditer(text) if _target_key(match) in targets]
    if not matches:
        return [inline]
    result: list[dict[str, Any]] = []
    cursor = 0
    for match in matches:
        if match.start() > cursor:
            result.append(
                {
                    **inline,
                    "id": stable_id(article_id, "object-xref-text", f"{path}:{cursor}"),
                    "text": text[cursor : match.start()],
                }
            )
        target_id = targets[_target_key(match)]
        result.append(
            {
                "id": stable_id(article_id, "object-xref", f"{path}:{match.start()}:{target_id}"),
                "kind": "cross_reference",
                "text": match.group(0),
                "target_id": target_id,
                "href": None,
                "name": None,
                "attributes": {},
                "formula_source": None,
                "formula_representation": None,
                "formula_asset_id": None,
                "evidence_ids": inline.get("evidence_ids", []),
            }
        )
        cursor = match.end()
    if cursor < len(text):
        result.append(
            {
                **inline,
                "id": stable_id(article_id, "object-xref-text", f"{path}:{cursor}"),
                "text": text[cursor:],
            }
        )
    return result


def _resolve_rich(
    value: dict[str, Any],
    *,
    targets: dict[tuple[str, int], str],
    article_id: str,
    path: str,
) -> None:
    plain = value.get("plain")
    plain_data: dict[str, Any] = plain if isinstance(plain, dict) else {}
    source = plain_data.get("value")
    if not isinstance(source, str) or not source:
        return
    inlines = value.get("inlines")
    if not isinstance(inlines, list):
        return
    if not inlines:
        inlines = [
            {
                "id": stable_id(article_id, "object-xref-source", path),
                "kind": "text",
                "text": source,
                "target_id": None,
                "href": None,
                "name": None,
                "attributes": {},
                "formula_source": None,
                "formula_representation": None,
                "formula_asset_id": None,
                "evidence_ids": plain_data.get("evidence_ids", []),
            }
        ]
    resolved: list[dict[str, Any]] = []
    for position, inline in enumerate(inlines):
        if not isinstance(inline, dict) or inline.get("kind") not in _TEXTUAL_INLINE_KINDS:
            resolved.append(inline)
            continue
        resolved.extend(
            _split_inline(
                inline,
                targets=targets,
                article_id=article_id,
                path=f"{path}:{position}",
            )
        )
    if any(item.get("kind") == "cross_reference" for item in resolved):
        value["inlines"] = resolved
        _formula_pair_tails(value, targets=targets, article_id=article_id, path=path)


def _walk(
    value: Any,
    *,
    targets: dict[tuple[str, int], str],
    article_id: str,
    path: str,
) -> None:
    if isinstance(value, dict):
        if set(value) == {"plain", "inlines"}:
            _resolve_rich(value, targets=targets, article_id=article_id, path=path)
            return
        for key, child in value.items():
            _walk(
                child,
                targets=targets,
                article_id=article_id,
                path=f"{path}.{key}",
            )
        if value.get("kind") == "paragraph" and isinstance(value.get("content"), dict):
            existing = {
                item.get("target_id"): item
                for item in value.get("cross_references", [])
                if isinstance(item, dict) and item.get("target_id")
            }
            # Numbering namespaces (chart vs table) collapse to the JATS ref-type.
            target_types = {
                target_id: "table" if kind == "chart" else kind
                for (kind, _), target_id in targets.items()
            }
            declared: list[dict[str, Any]] = []
            seen: set[str] = set()
            for inline in value["content"].get("inlines", []):
                if not isinstance(inline, dict) or inline.get("kind") != "cross_reference":
                    continue
                target_id = inline.get("target_id")
                if not isinstance(target_id, str) or target_id in seen:
                    continue
                seen.add(target_id)
                if target_id in existing:
                    declared.append(existing[target_id])
                elif target_id in target_types:
                    declared.append(
                        {
                            "target_id": target_id,
                            "reference_type": target_types[target_id],
                            "label": inline.get("text"),
                            "evidence_ids": inline.get("evidence_ids", []),
                        }
                    )
            value["cross_references"] = declared
    elif isinstance(value, list):
        for position, child in enumerate(value):
            _walk(
                child,
                targets=targets,
                article_id=article_id,
                path=f"{path}[{position}]",
            )


def resolve_object_references(article: CanonicalArticle) -> CanonicalArticle:
    """Link explicit numbered object mentions without adding or changing prose."""

    targets = _targets(article)
    payload = article.model_dump(mode="json")
    _walk(payload["body"], targets=targets, article_id=article.article_id, path="body")
    _following_formulas(payload["body"], article_id=article.article_id)
    # Reconcile paragraph declarations with the new links. Existing links are not rewritten.
    _walk(payload["body"], targets=targets, article_id=article.article_id, path="body")
    return CanonicalArticle.model_validate(payload)
