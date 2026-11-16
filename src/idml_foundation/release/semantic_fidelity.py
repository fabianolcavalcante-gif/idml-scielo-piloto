from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, cast

from lxml import etree
from pydantic import Field

from idml_foundation.domain.common import SHA256_PATTERN, StrictModel
from idml_foundation.domain.metrics import normalize_text, text_fidelity
from idml_foundation.pipeline.crossref_evaluation import (
    CrossReferenceEvaluation,
    evaluate_cross_references,
)

_MAX_XML_BYTES = 100 * 1024 * 1024


class SemanticChangeKind(StrEnum):
    OMISSION = "omission"
    INVENTION = "invention"
    ALTERATION = "alteration"
    DUPLICATION = "duplication"
    DISPLACEMENT = "displacement"
    NORMALIZATION = "normalization"


class SemanticFinding(StrictModel):
    domain: str
    kind: SemanticChangeKind
    expected_position: int | None = Field(default=None, ge=1)
    actual_position: int | None = Field(default=None, ge=1)
    expected_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    actual_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    similarity: float = Field(ge=0, le=1)
    blocking: bool


class SemanticDomainScore(StrictModel):
    domain: str
    comparison_unit: Literal["elements", "tokens"] = "elements"
    expected: int = Field(ge=0)
    actual: int = Field(ge=0)
    exact: int = Field(ge=0)
    normalized: int = Field(ge=0)
    altered: int = Field(ge=0)
    omissions: int = Field(ge=0)
    inventions: int = Field(ge=0)
    duplications: int = Field(ge=0)
    displacements: int = Field(ge=0)
    precision: float = Field(ge=0, le=1)
    recall: float = Field(ge=0, le=1)
    f1: float = Field(ge=0, le=1)
    text_fidelity: float = Field(ge=0, le=1)
    passed: bool


class SemanticFidelityReport(StrictModel):
    report_version: str = "1.0.0"
    reference_xml_sha256: str = Field(pattern=SHA256_PATTERN)
    candidate_xml_sha256: str = Field(pattern=SHA256_PATTERN)
    alignment_threshold: float = Field(ge=0, le=1)
    domains: tuple[SemanticDomainScore, ...]
    findings: tuple[SemanticFinding, ...]
    cross_references: CrossReferenceEvaluation
    blocking_findings: int = Field(ge=0)
    content_emitted: bool = False
    passed: bool


@dataclass(frozen=True)
class _SemanticField:
    raw: str
    normalized: str
    sha256: str
    token_count: int


def _field(value: str) -> _SemanticField:
    normalized = normalize_text(value)
    return _SemanticField(
        raw=value,
        normalized=normalized,
        sha256=hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
        token_count=max(1, len(normalized.split())),
    )


def _node_text(node: etree._Element) -> str:
    return " ".join(
        value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value
        for value in node.itertext()
    )


def _values(nodes: list[etree._Element]) -> list[str]:
    return [value for node in nodes if normalize_text(value := _node_text(node))]


def _body_paragraph_text(node: etree._Element) -> str:
    values = cast(
        list[object],
        node.xpath(".//text()[not(ancestor::inline-formula) and not(ancestor::disp-formula)]"),
    )
    return " ".join(value for value in values if isinstance(value, str))


def _xpath(root: etree._Element, expression: str) -> list[etree._Element]:
    return cast(list[etree._Element], root.xpath(expression))


def _affiliation_text(node: etree._Element) -> str:
    original = node.find("institution[@content-type='original']")
    if original is not None and normalize_text(_node_text(original)):
        return _node_text(original)
    parts = _xpath(
        node,
        "institution[@content-type='orgdiv1' or @content-type='orgdiv2' or "
        "@content-type='orgname'] | addr-line | country",
    )
    return " ".join(_node_text(part) for part in parts)


def _labeled_text(node: etree._Element) -> str:
    label = normalize_text(node.findtext("label") or "")
    captions = _values(_xpath(node, "caption"))
    cleaned: list[str] = []
    for caption in captions:
        if label:
            caption = re.sub(
                rf"^\s*{re.escape(label)}\s*[-\u2013\u2014:]?\s*",
                "",
                caption,
                count=1,
                flags=re.IGNORECASE,
            )
        cleaned.append(caption)
    content = " ".join((label, *cleaned)).strip()
    return content


def _table_text(node: etree._Element) -> str:
    heading = _labeled_text(node)
    cells = [
        raw
        for cell in _xpath(node, ".//tr/*[self::th or self::td]")
        if normalize_text(
            raw := "".join(
                value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value
                for value in cell.itertext()
            )
        )
    ]
    return " ".join((heading, *cells)).strip()


def _with_note_label(label: str, value: str) -> str:
    if normalize_text(value).casefold().startswith(label.casefold()):
        return value
    return f"{label}: {value}"


def _note_values(root: etree._Element) -> list[str]:
    values: list[str] = []
    for note in _xpath(
        root,
        "front/article-meta/author-notes/fn | body//fn | back//fn",
    ):
        label = normalize_text(note.findtext("label") or "")
        semantic_label = label if re.search(r"[^\W\d_]", label) else ""
        for paragraph in _values(_xpath(note, "p")):
            values.append(" ".join((semantic_label, paragraph)).strip())
    for section in _xpath(root, "back/sec[title]"):
        title = normalize_text(section.findtext("title") or "")
        if "conflict" not in title.casefold():
            continue
        for paragraph in _values(_xpath(section, "p")):
            values.append(_with_note_label("Conflicts of interest", paragraph))
    for statement in _values(_xpath(root, "front/article-meta/funding-group/funding-statement")):
        values.append(_with_note_label("Funding", statement))

    def category(value: str) -> int:
        normalized = normalize_text(value).casefold()
        if normalized.startswith("conflicts of interest"):
            return 0
        if normalized.startswith("associate editor"):
            return 1
        if normalized.startswith("scientific editor"):
            return 2
        if normalized.startswith("funding"):
            return 3
        return 99

    ordered = sorted(
        enumerate(values),
        key=lambda item: (category(item[1]), item[0]),
    )
    unique: list[str] = []
    seen: set[str] = set()
    for _, value in ordered:
        normalized = normalize_text(value).casefold()
        if normalized not in seen:
            unique.append(value)
            seen.add(normalized)
    return unique


def _formula_parts(node: etree._Element) -> tuple[str, str | None]:
    kind = "inline" if etree.QName(node).localname == "inline-formula" else "display"
    label = normalize_text(node.findtext("label") or "")
    text_nodes = cast(list[object], node.xpath(".//text()[not(ancestor::label)]"))
    text = normalize_text(" ".join(value for value in text_nodes if isinstance(value, str)))
    representation = "mathml" if node.xpath(".//*[local-name()='math']") else "graphic"
    if node.find("tex-math") is not None:
        representation = "tex"
    identity = "|".join((kind, label))
    content = "|".join((identity, representation, text)) if representation != "graphic" else None
    return identity, content


def extract_semantic_fields(root: etree._Element) -> dict[str, tuple[_SemanticField, ...]]:
    metadata: list[str] = []
    for node in _xpath(
        root,
        "front/journal-meta/journal-title-group/journal-title | "
        "front/article-meta/title-group/article-title | "
        "front/article-meta/title-group/trans-title-group/trans-title",
    ):
        metadata.append(_node_text(node))
    for node in _xpath(root, "front/article-meta/article-id"):
        metadata.append(f"{node.get('pub-id-type', '')}:{_node_text(node)}")

    authors = _values(
        _xpath(
            root,
            "front/article-meta/contrib-group/contrib[@contrib-type='author']/*"
            "[self::name or self::collab]",
        )
    )
    affiliations = [
        raw
        for node in _xpath(root, "front/article-meta/aff")
        if normalize_text(raw := _affiliation_text(node))
    ]
    figures = [
        raw for node in _xpath(root, "body//fig") if normalize_text(raw := _labeled_text(node))
    ]
    tables = [
        raw for node in _xpath(root, "body//table-wrap") if normalize_text(raw := _table_text(node))
    ]
    formula_parts = [
        _formula_parts(node) for node in _xpath(root, "body//disp-formula | body//inline-formula")
    ]
    media = [
        etree.QName(node.getparent()).localname
        for node in _xpath(root, "body//fig//graphic | body//fig//inline-graphic")
        if node.getparent() is not None
    ]
    domains = {
        "metadata": metadata,
        "authors": authors,
        "affiliations": affiliations,
        "structure": _values(_xpath(root, "body//sec/title")),
        "body": [
            raw
            for node in _xpath(
                root,
                "body//p[not(ancestor::caption) and not(ancestor::table-wrap-foot) "
                "and not(ancestor::fn)]",
            )
            if normalize_text(raw := _body_paragraph_text(node))
        ],
        "references": _values(_xpath(root, "back/ref-list/ref/mixed-citation")),
        "figures": figures,
        "tables": tables,
        "formulas": [identity for identity, _ in formula_parts],
        "formula_content": [content for _, content in formula_parts if content is not None],
        "notes": _note_values(root),
        "media": media,
    }
    return {
        domain: tuple(_field(value) for value in values if normalize_text(value))
        for domain, values in domains.items()
    }


def _parse_xml(payload: bytes) -> etree._Element:
    if not payload or len(payload) > _MAX_XML_BYTES:
        raise ValueError("XML input must contain between 1 byte and 100 MiB")
    parser = etree.XMLParser(
        resolve_entities=False,
        load_dtd=False,
        no_network=True,
        recover=False,
        huge_tree=False,
    )
    return etree.fromstring(payload, parser=parser)


def _alignment(
    expected: tuple[_SemanticField, ...],
    actual: tuple[_SemanticField, ...],
    threshold: float,
) -> tuple[list[tuple[int, int, float]], set[int], set[int]]:
    rows = len(expected)
    columns = len(actual)
    gap = -0.25
    scores = [[0.0] * (columns + 1) for _ in range(rows + 1)]
    moves = [[""] * (columns + 1) for _ in range(rows + 1)]
    for row in range(1, rows + 1):
        scores[row][0] = row * gap
        moves[row][0] = "expected"
    for column in range(1, columns + 1):
        scores[0][column] = column * gap
        moves[0][column] = "actual"
    similarities: dict[tuple[int, int], float] = {}
    for row in range(1, rows + 1):
        for column in range(1, columns + 1):
            similarity = text_fidelity(
                expected[row - 1].normalized,
                actual[column - 1].normalized,
            )
            similarities[(row, column)] = similarity
            options: list[tuple[float, int, str]] = [
                (scores[row - 1][column] + gap, 1, "expected"),
                (scores[row][column - 1] + gap, 0, "actual"),
            ]
            if similarity >= threshold:
                options.append((scores[row - 1][column - 1] + similarity, 2, "match"))
            score, _, move = max(options, key=lambda item: (item[0], item[1]))
            scores[row][column] = score
            moves[row][column] = move

    matches: list[tuple[int, int, float]] = []
    unmatched_expected = set(range(rows))
    unmatched_actual = set(range(columns))
    row, column = rows, columns
    while row or column:
        move = moves[row][column]
        if move == "match":
            matches.append((row - 1, column - 1, similarities[(row, column)]))
            unmatched_expected.discard(row - 1)
            unmatched_actual.discard(column - 1)
            row -= 1
            column -= 1
        elif move == "expected":
            row -= 1
        elif move == "actual":
            column -= 1
        else:
            raise RuntimeError("semantic alignment backtracking failed")
    matches.reverse()
    return matches, unmatched_expected, unmatched_actual


def _finding(
    domain: str,
    kind: SemanticChangeKind,
    expected: _SemanticField | None,
    actual: _SemanticField | None,
    expected_position: int | None,
    actual_position: int | None,
    similarity: float,
) -> SemanticFinding:
    return SemanticFinding(
        domain=domain,
        kind=kind,
        expected_position=expected_position + 1 if expected_position is not None else None,
        actual_position=actual_position + 1 if actual_position is not None else None,
        expected_sha256=expected.sha256 if expected is not None else None,
        actual_sha256=actual.sha256 if actual is not None else None,
        similarity=round(similarity, 6),
        blocking=kind != SemanticChangeKind.NORMALIZATION,
    )


def _token_counter(fields: tuple[_SemanticField, ...]) -> Counter[str]:
    stream = " ".join(field.normalized for field in fields)
    return Counter(re.findall(r"\w+", stream.casefold()))


def _semantic_tokens(value: str) -> tuple[str, ...]:
    return tuple(re.findall(r"\w+", normalize_text(value).casefold()))


def _counter_field(values: Counter[str]) -> _SemanticField | None:
    if not values:
        return None
    serialized = " ".join(token for token, count in sorted(values.items()) for _ in range(count))
    return _field(serialized)


def _compare_text_stream(
    domain: str,
    expected: tuple[_SemanticField, ...],
    actual: tuple[_SemanticField, ...],
) -> tuple[SemanticDomainScore, tuple[SemanticFinding, ...]]:
    expected_raw = " ".join(field.raw for field in expected)
    actual_raw = " ".join(field.raw for field in actual)
    expected_stream = _field(expected_raw)
    actual_stream = _field(actual_raw)
    expected_tokens = _token_counter(expected)
    actual_tokens = _token_counter(actual)
    matched = sum((expected_tokens & actual_tokens).values())
    expected_total = sum(expected_tokens.values())
    actual_total = sum(actual_tokens.values())
    precision = matched / actual_total if actual_total else float(not expected_total)
    recall = matched / expected_total if expected_total else float(not actual_total)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    similarity = text_fidelity(expected_stream.normalized, actual_stream.normalized)
    missing = expected_tokens - actual_tokens
    extra = actual_tokens - expected_tokens
    duplicate = Counter(
        {
            token: count
            for token, count in extra.items()
            if token in expected_tokens and token not in missing
        }
    )
    invented = extra - duplicate
    findings: list[SemanticFinding] = []
    expected_sequence = _semantic_tokens(expected_raw)
    actual_sequence = _semantic_tokens(actual_raw)
    sequence_equivalent = expected_sequence == actual_sequence
    normalization = int(expected_raw != actual_raw and sequence_equivalent)
    displacement = int(not missing and not extra and not sequence_equivalent)
    alteration = int(bool(missing and extra))
    if normalization:
        findings.append(
            _finding(
                domain,
                SemanticChangeKind.NORMALIZATION,
                expected_stream,
                actual_stream,
                0,
                0,
                1.0,
            )
        )
    if displacement:
        findings.append(
            _finding(
                domain,
                SemanticChangeKind.DISPLACEMENT,
                expected_stream,
                actual_stream,
                0,
                0,
                similarity,
            )
        )
    if alteration:
        findings.append(
            _finding(
                domain,
                SemanticChangeKind.ALTERATION,
                expected_stream,
                actual_stream,
                0,
                0,
                similarity,
            )
        )
    missing_field = _counter_field(missing)
    if missing_field is not None:
        findings.append(
            _finding(
                domain,
                SemanticChangeKind.OMISSION,
                missing_field,
                None,
                None,
                None,
                0.0,
            )
        )
    duplicate_field = _counter_field(duplicate)
    if duplicate_field is not None:
        findings.append(
            _finding(
                domain,
                SemanticChangeKind.DUPLICATION,
                None,
                duplicate_field,
                None,
                None,
                0.0,
            )
        )
    invented_field = _counter_field(invented)
    if invented_field is not None:
        findings.append(
            _finding(
                domain,
                SemanticChangeKind.INVENTION,
                None,
                invented_field,
                None,
                None,
                0.0,
            )
        )
    blocking = sum(finding.blocking for finding in findings)
    return (
        SemanticDomainScore(
            domain=domain,
            comparison_unit="tokens",
            expected=expected_total,
            actual=actual_total,
            exact=matched,
            normalized=normalization,
            altered=alteration,
            omissions=sum(missing.values()),
            inventions=sum(invented.values()),
            duplications=sum(duplicate.values()),
            displacements=displacement,
            precision=round(precision, 6),
            recall=round(recall, 6),
            f1=round(f1, 6),
            text_fidelity=round(similarity, 6),
            passed=blocking == 0,
        ),
        tuple(findings),
    )


def _compare_domain(
    domain: str,
    expected: tuple[_SemanticField, ...],
    actual: tuple[_SemanticField, ...],
    threshold: float,
) -> tuple[SemanticDomainScore, tuple[SemanticFinding, ...]]:
    expected_hashes = tuple(item.sha256 for item in expected)
    actual_hashes = tuple(item.sha256 for item in actual)
    if expected_hashes != actual_hashes and Counter(expected_hashes) == Counter(actual_hashes):
        positions: dict[str, list[int]] = {}
        for index, digest in reversed(tuple(enumerate(actual_hashes))):
            positions.setdefault(digest, []).append(index)
        reorder_findings: list[SemanticFinding] = []
        exact = normalized = displacements = 0
        for expected_index, left in enumerate(expected):
            actual_index = positions[left.sha256].pop()
            right = actual[actual_index]
            if expected_index != actual_index:
                displacements += 1
                reorder_findings.append(
                    _finding(
                        domain,
                        SemanticChangeKind.DISPLACEMENT,
                        left,
                        right,
                        expected_index,
                        actual_index,
                        1.0,
                    )
                )
            elif left.raw == right.raw:
                exact += 1
            else:
                normalized += 1
                reorder_findings.append(
                    _finding(
                        domain,
                        SemanticChangeKind.NORMALIZATION,
                        left,
                        right,
                        expected_index,
                        actual_index,
                        1.0,
                    )
                )
        correct = exact + normalized
        precision = correct / len(actual) if actual else 1.0
        recall = correct / len(expected) if expected else 1.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        return (
            SemanticDomainScore(
                domain=domain,
                expected=len(expected),
                actual=len(actual),
                exact=exact,
                normalized=normalized,
                altered=0,
                omissions=0,
                inventions=0,
                duplications=0,
                displacements=displacements,
                precision=round(precision, 6),
                recall=round(recall, 6),
                f1=round(f1, 6),
                text_fidelity=1.0,
                passed=False,
            ),
            tuple(reorder_findings),
        )

    matches, missing, extra = _alignment(expected, actual, threshold)
    findings: list[SemanticFinding] = []
    exact = normalized = altered = 0
    weighted_similarity = 0.0
    expected_weight = sum(item.token_count for item in expected)
    for expected_index, actual_index, similarity in matches:
        left = expected[expected_index]
        right = actual[actual_index]
        weighted_similarity += similarity * left.token_count
        if left.raw == right.raw:
            exact += 1
        elif left.normalized == right.normalized or _semantic_tokens(
            left.normalized
        ) == _semantic_tokens(right.normalized):
            normalized += 1
            findings.append(
                _finding(
                    domain,
                    SemanticChangeKind.NORMALIZATION,
                    left,
                    right,
                    expected_index,
                    actual_index,
                    1.0,
                )
            )
        else:
            altered += 1
            findings.append(
                _finding(
                    domain,
                    SemanticChangeKind.ALTERATION,
                    left,
                    right,
                    expected_index,
                    actual_index,
                    similarity,
                )
            )

    expected_by_hash: dict[str, list[int]] = {}
    actual_by_hash: dict[str, list[int]] = {}
    for index in sorted(missing):
        expected_by_hash.setdefault(expected[index].sha256, []).append(index)
    for index in sorted(extra):
        actual_by_hash.setdefault(actual[index].sha256, []).append(index)
    displacements = 0
    for digest in sorted(set(expected_by_hash) & set(actual_by_hash)):
        for expected_index, actual_index in zip(
            expected_by_hash[digest], actual_by_hash[digest], strict=False
        ):
            missing.remove(expected_index)
            extra.remove(actual_index)
            displacements += 1
            weighted_similarity += expected[expected_index].token_count
            findings.append(
                _finding(
                    domain,
                    SemanticChangeKind.DISPLACEMENT,
                    expected[expected_index],
                    actual[actual_index],
                    expected_index,
                    actual_index,
                    1.0,
                )
            )

    expected_counts = Counter(item.sha256 for item in expected)
    actual_counts = Counter(item.sha256 for item in actual)
    duplications = 0
    inventions = 0
    for actual_index in sorted(extra):
        right = actual[actual_index]
        kind = (
            SemanticChangeKind.DUPLICATION
            if actual_counts[right.sha256] > expected_counts[right.sha256] > 0
            else SemanticChangeKind.INVENTION
        )
        if kind == SemanticChangeKind.DUPLICATION:
            duplications += 1
        else:
            inventions += 1
        findings.append(_finding(domain, kind, None, right, None, actual_index, 0.0))
    for expected_index in sorted(missing):
        left = expected[expected_index]
        findings.append(
            _finding(
                domain,
                SemanticChangeKind.OMISSION,
                left,
                None,
                expected_index,
                None,
                0.0,
            )
        )

    correct = exact + normalized
    precision = correct / len(actual) if actual else float(not expected)
    recall = correct / len(expected) if expected else float(not actual)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    blocking = altered + len(missing) + inventions + duplications + displacements
    score = SemanticDomainScore(
        domain=domain,
        expected=len(expected),
        actual=len(actual),
        exact=exact,
        normalized=normalized,
        altered=altered,
        omissions=len(missing),
        inventions=inventions,
        duplications=duplications,
        displacements=displacements,
        precision=round(precision, 6),
        recall=round(recall, 6),
        f1=round(f1, 6),
        text_fidelity=round(weighted_similarity / expected_weight, 6)
        if expected_weight
        else float(not actual),
        passed=blocking == 0,
    )
    return score, tuple(findings)


class XmlSemanticComparator:
    def compare(
        self,
        reference_xml: bytes,
        candidate_xml: bytes,
        *,
        alignment_threshold: float = 0.35,
    ) -> SemanticFidelityReport:
        if not 0 < alignment_threshold <= 1:
            raise ValueError("alignment_threshold must be greater than zero and at most one")
        reference_root = _parse_xml(reference_xml)
        candidate_root = _parse_xml(candidate_xml)
        reference = extract_semantic_fields(reference_root)
        candidate = extract_semantic_fields(candidate_root)
        if reference.keys() != candidate.keys():
            raise RuntimeError("semantic extraction domains do not match")
        scores: list[SemanticDomainScore] = []
        findings: list[SemanticFinding] = []
        for domain in reference:
            if domain == "body":
                score, domain_findings = _compare_text_stream(
                    domain, reference[domain], candidate[domain]
                )
            else:
                score, domain_findings = _compare_domain(
                    domain,
                    reference[domain],
                    candidate[domain],
                    alignment_threshold,
                )
            scores.append(score)
            findings.extend(domain_findings)
        cross_references = evaluate_cross_references(reference_root, candidate_root)
        blocking = sum(item.blocking for item in findings)
        passed = blocking == 0 and cross_references.decision == "pass"
        return SemanticFidelityReport(
            reference_xml_sha256=hashlib.sha256(reference_xml).hexdigest(),
            candidate_xml_sha256=hashlib.sha256(candidate_xml).hexdigest(),
            alignment_threshold=alignment_threshold,
            domains=tuple(scores),
            findings=tuple(findings),
            cross_references=cross_references,
            blocking_findings=blocking,
            passed=passed,
        )
