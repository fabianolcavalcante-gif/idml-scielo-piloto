"""Field-level comparison of a generated JATS XML against the XML published by SciELO.

The published XML is a *measurement key only*: it is never an input to the converter.
Scores are in [0, 1]; ``None`` means the field is absent from the key (not applicable).

Usage:
    python -m ops.benchmark_published_xml CANDIDATE.xml PUBLISHED.xml [--json OUT.json]
    python -m ops.benchmark_published_xml --pairs pairs.json --json OUT.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter
from collections.abc import Iterable
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from lxml import etree

_PARSER = etree.XMLParser(
    resolve_entities=False, load_dtd=False, no_network=True, recover=False, huge_tree=False
)
_XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"
_WORD = re.compile(r"\w+", re.UNICODE)


def _local(element: etree._Element) -> str:
    return etree.QName(element).localname if isinstance(element.tag, str) else ""


def _norm(value: str | None) -> str:
    text = unicodedata.normalize("NFKC", value or "").casefold()
    return " ".join(_WORD.findall(text))


def _text(element: etree._Element | None) -> str:
    return _norm("".join(element.itertext())) if element is not None else ""


def _find(root: etree._Element, *path: str) -> list[etree._Element]:
    nodes = [root]
    for name in path:
        nodes = [child for node in nodes for child in node.iter() if _local(child) == name]
    return nodes


def _main_article_parts(root: etree._Element) -> tuple[etree._Element, list[etree._Element]]:
    subs = [e for e in root.iter() if _local(e) == "sub-article"]
    for sub in subs:
        parent = sub.getparent()
        if parent is not None:
            parent.remove(sub)
    return root, subs


def _ratio(a: str, b: str) -> float:
    if not a and not b:
        return 1.0
    return SequenceMatcher(None, a, b, autojunk=False).ratio()


def _f1(candidate: Iterable[str], key: Iterable[str]) -> float | None:
    c, k = Counter(candidate), Counter(key)
    if not k:
        return None if not c else 0.0
    hit = sum((c & k).values())
    if not c or not hit:
        return 0.0
    precision, recall = hit / sum(c.values()), hit / sum(k.values())
    return 2 * precision * recall / (precision + recall)


def _count(candidate: int, key: int) -> float | None:
    if key == 0:
        return None if candidate == 0 else 0.0
    return max(0.0, 1 - abs(candidate - key) / key)


def extract(xml: bytes) -> dict[str, Any]:
    root = etree.fromstring(xml, parser=_PARSER)
    lang = root.get(_XML_LANG, "")
    main, subs = _main_article_parts(root)

    def first(*path: str) -> etree._Element | None:
        found = _find(main, *path)
        return found[0] if found else None

    contribs = []
    for contrib in _find(main, "contrib-group", "contrib"):
        surname, given = (_find(contrib, n) for n in ("surname", "given-names"))
        contribs.append(
            f"{_text(surname[0]) if surname else ''}|{_text(given[0]) if given else ''}"
        )
    history = {
        d.get("date-type", ""): "-".join(
            _text(next(iter(_find(d, part)), None)).zfill(2) for part in ("year", "month", "day")
        )
        for d in _find(main, "history", "date")
    }
    main_abstracts = _find(main, "abstract")
    abstracts = {lang: _text(main_abstracts[0])} if main_abstracts else {}
    abstracts.update({e.get(_XML_LANG, ""): _text(e) for e in _find(main, "trans-abstract")})
    keywords = {
        g.get(_XML_LANG, ""): sorted(_text(k) for k in _find(g, "kwd"))
        for g in _find(main, "kwd-group")
    }
    refs = []
    for ref in _find(main, "ref-list", "ref"):
        citation = next(iter(_find(ref, "element-citation")), None)

        def field(name: str, node: etree._Element | None = citation) -> str:
            found = _find(node, name) if node is not None else []
            return _text(found[0]) if found else ""

        refs.append(
            dict(
                mixed=_text(next(iter(_find(ref, "mixed-citation")), None)),
                surname=field("surname"),
                year=field("year"),
                source=field("source"),
                title=field("article-title"),
            )
        )
    body = first("body")
    tables = _find(main, "table-wrap")
    return dict(
        lang=lang,
        doi=_text(
            next((e for e in _find(main, "article-id") if e.get("pub-id-type") == "doi"), None)
        ),
        elocation=_text(first("elocation-id")),
        title=_text(first("title-group", "article-title")),
        trans_titles={
            e.getparent().get(_XML_LANG, ""): _text(e) for e in _find(main, "trans-title")
        },
        contribs=contribs,
        orcids=sorted(
            _norm(e.text) for e in _find(main, "contrib-id") if e.get("contrib-id-type") == "orcid"
        ),
        aff_countries=sorted(e.get("country", "") for e in _find(main, "aff", "country")),
        aff_count=len(_find(main, "aff")),
        abstracts=abstracts,
        keywords=keywords,
        history=history,
        sections=[
            _text(next(iter(_find(s, "title")), None))
            for s in (body if body is not None else main).iterchildren()
            if _local(s) == "sec"
        ],
        body_words=_WORD.findall(_text(body)) if body is not None else [],
        tables=len(tables),
        table_labels=sorted(_text(next(iter(_find(t, "label")), None)) for t in tables),
        table_words=[
            w
            for t in tables
            for td in _find(t, "td") + _find(t, "th")
            for w in _WORD.findall(_text(td))
        ],
        thead=sum(1 for t in tables if _find(t, "thead")),
        figures=len(_find(main, "fig")),
        disp_formulas=len(_find(main, "disp-formula")),
        inline_formulas=len(_find(main, "inline-formula")),
        mathml=sum(1 for e in main.iter() if _local(e) == "math"),
        refs=refs,
        xrefs=dict(Counter(e.get("ref-type", "") for e in _find(main, "xref"))),
        sub_articles=sorted(f"{s.get('article-type', '')}:{s.get(_XML_LANG, '')}" for s in subs),
    )


def compare(candidate: dict[str, Any], key: dict[str, Any]) -> dict[str, float | None]:
    def langs_text(c: dict[str, str], k: dict[str, str]) -> float | None:
        if not k:
            return None if not c else 0.0
        return sum(_ratio(c.get(lang, ""), text) for lang, text in k.items()) / len(k)

    ref_pairs = list(zip(candidate["refs"], key["refs"], strict=False))
    n_refs = max(len(key["refs"]), 1)

    def ref_field(name: str) -> float | None:
        if not key["refs"]:
            return None
        return sum(1.0 for c, k in ref_pairs if k[name] and c[name] == k[name]) / max(
            sum(1 for k in key["refs"] if k[name]), 1
        )

    xref_types = set(candidate["xrefs"]) | set(key["xrefs"])
    return {
        "lang": float(candidate["lang"] == key["lang"]),
        "doi": float(candidate["doi"] == key["doi"]) if key["doi"] else None,
        "elocation": float(candidate["elocation"] == key["elocation"])
        if key["elocation"]
        else None,
        "title": _ratio(candidate["title"], key["title"]),
        "trans_titles": langs_text(candidate["trans_titles"], key["trans_titles"]),
        "contribs": _f1(candidate["contribs"], key["contribs"]),
        "orcids": _f1(candidate["orcids"], key["orcids"]),
        "aff_count": _count(candidate["aff_count"], key["aff_count"]),
        "aff_countries": _f1(candidate["aff_countries"], key["aff_countries"]),
        "abstracts": langs_text(candidate["abstracts"], key["abstracts"]),
        "keywords": (
            None
            if not key["keywords"]
            else sum(
                _f1(candidate["keywords"].get(lang, []), words) or 0.0
                for lang, words in key["keywords"].items()
            )
            / len(key["keywords"])
        ),
        "history": (
            None
            if not key["history"]
            else sum(candidate["history"].get(t) == v for t, v in key["history"].items())
            / len(key["history"])
        ),
        "sections": _ratio(" / ".join(candidate["sections"]), " / ".join(key["sections"])),
        "body_text": _f1(candidate["body_words"], key["body_words"]),
        "tables": _count(candidate["tables"], key["tables"]),
        "table_text": _f1(candidate["table_words"], key["table_words"]),
        "table_thead": _count(candidate["thead"], key["thead"]),
        "figures": _count(candidate["figures"], key["figures"]),
        "disp_formulas": _count(candidate["disp_formulas"], key["disp_formulas"]),
        "mathml": _count(candidate["mathml"], key["mathml"]),
        "refs": _count(len(candidate["refs"]), len(key["refs"])),
        "ref_text": (
            None
            if not key["refs"]
            else sum(_ratio(c["mixed"], k["mixed"]) for c, k in ref_pairs) / n_refs
        ),
        "ref_surname": ref_field("surname"),
        "ref_year": ref_field("year"),
        "ref_source": ref_field("source"),
        "ref_title": ref_field("title"),
        "xrefs": (
            None
            if not key["xrefs"]
            else sum(
                _count(candidate["xrefs"].get(t, 0), key["xrefs"].get(t, 0)) or 0.0
                for t in xref_types
            )
            / len(xref_types)
        ),
        "sub_articles": _f1(candidate["sub_articles"], key["sub_articles"]),
    }


def score(candidate_xml: bytes, published_xml: bytes) -> dict[str, float | None]:
    return compare(extract(candidate_xml), extract(published_xml))


def summarize(scores: dict[str, float | None]) -> float:
    values = [v for v in scores.values() if v is not None]
    return sum(values) / len(values) if values else 0.0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("candidate", nargs="?", type=Path)
    parser.add_argument("published", nargs="?", type=Path)
    parser.add_argument(
        "--pairs", type=Path, help='JSON: [{"case": ..., "candidate": ..., "published": ...}]'
    )
    parser.add_argument("--json", type=Path)
    args = parser.parse_args(argv)
    if args.pairs:
        pairs = json.loads(args.pairs.read_text(encoding="utf-8"))
    elif args.candidate and args.published:
        pairs = [
            {
                "case": args.candidate.stem,
                "candidate": str(args.candidate),
                "published": str(args.published),
            }
        ]
    else:
        parser.error("give CANDIDATE PUBLISHED or --pairs")
    report = {}
    for pair in pairs:
        scores = score(Path(pair["candidate"]).read_bytes(), Path(pair["published"]).read_bytes())
        report[pair["case"]] = {"overall": round(summarize(scores), 4), "fields": scores}
    fields = sorted({f for r in report.values() for f in r["fields"]})
    width = max(len(c) for c in report) + 2
    print("campo".ljust(16) + "".join(c[:width].rjust(width) for c in report))
    for name in ["overall", *fields]:
        row = []
        for result in report.values():
            value = result["overall"] if name == "overall" else result["fields"][name]
            row.append(("-" if value is None else f"{value:.2f}").rjust(width))
        print(name.ljust(16) + "".join(row))
    if args.json:
        args.json.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
