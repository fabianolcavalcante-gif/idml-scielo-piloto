"""Bounded XML target extraction, shared with the Python 3.10 host collector."""

import re
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from typing import cast
from urllib.parse import quote


def _parse_candidate(xml: bytes) -> ET.Element:
    if not 0 < len(xml) <= 8 * 1024**2 or b"\x00" in xml:
        raise ValueError("query_xml_budget")
    text = xml.decode("utf-8-sig")
    if "<!ENTITY" in text.upper() or re.search(r"<!DOCTYPE[^>]*\[", text, re.I):
        raise ValueError("query_entities_denied")
    parser = ET.XMLPullParser(events=("start", "end"))
    root: ET.Element | None = None
    depth = count = 0
    for start in range(0, len(text), 65536):
        parser.feed(text[start : start + 65536])
        for event, node in cast(Iterable[tuple[str, ET.Element]], parser.read_events()):
            if event == "start":
                depth += 1
                count += 1
                if root is None:
                    root = node
                if depth > 128 or count > 100000:
                    raise ValueError("query_xml_complexity")
            else:
                depth -= 1
    parser.close()
    if root is None or root.tag != "article" or len(root.findall("front/article-meta")) != 1:
        raise ValueError("query_article_shape")
    return root


def parse_candidate(xml: bytes) -> ET.Element:
    try:
        return _parse_candidate(xml)
    except ET.ParseError:
        raise ValueError("query_xml_malformed") from None


def plain_name(node: ET.Element) -> str:
    names = node.findall("name")
    if len(names) != 1:
        raise ValueError("query_name_shape")
    parts = []
    for field in ("given-names", "surname"):
        values = names[0].findall(field)
        if len(values) != 1 or len(values[0]) or not (values[0].text or "").strip():
            raise ValueError("query_name_shape")
        parts.append((values[0].text or "").strip())
    return " ".join(parts)


def endpoint(kind: str, identifier: str) -> tuple[str, str]:
    if kind == "crossref" and re.fullmatch(
        r"10\.[0-9]{4,9}/[-._;()/:A-Za-z0-9]{1,180}", identifier
    ):
        return "api.crossref.org", "/works/" + quote(identifier, safe="")
    if kind == "orcid" and re.fullmatch(r"[0-9]{4}-[0-9]{4}-[0-9]{4}-[0-9]{3}[0-9X]", identifier):
        total = 0
        for digit in identifier.replace("-", "")[:-1]:
            total = (total + int(digit)) * 2
        check = (12 - total % 11) % 11
        if identifier[-1] == ("X" if check == 10 else str(check)):
            return "pub.orcid.org", f"/v3.0/{identifier}/person"
    raise ValueError("query_identifier_invalid")


def query_targets(xml: bytes) -> list[dict[str, str]]:
    root = parse_candidate(xml)
    dois = root.findall("front/article-meta/article-id[@pub-id-type='doi']")
    if len(dois) != 1 or len(dois[0]):
        raise ValueError("query_doi_not_unique")
    doi = (dois[0].text or "").strip().lower()
    endpoint("crossref", doi)
    result = [dict(kind="crossref", identifier=doi)]
    seen = set()
    nodes = root.findall(".//contrib-id[@contrib-id-type='orcid']")
    for contributor in root.findall(".//contrib"):
        ids = contributor.findall("contrib-id[@contrib-id-type='orcid']")
        if not ids:
            continue
        if len(ids) != 1 or len(ids[0]):
            raise ValueError("query_orcid_shape")
        identifier = (ids[0].text or "").strip()
        for prefix in ("https://orcid.org/", "http://orcid.org/"):
            identifier = identifier.removeprefix(prefix)
        endpoint("orcid", identifier)
        if identifier in seen:
            raise ValueError("query_orcid_duplicate")
        seen.add(identifier)
        result.append(dict(kind="orcid", identifier=identifier, name=plain_name(contributor)))
    if len(nodes) != len(seen) or len(result) > 17:
        raise ValueError("query_targets_unqualified")
    return result
