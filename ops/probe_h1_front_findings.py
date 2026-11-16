"""Content-free structural inventory of the two authorized development candidates."""

import json
from pathlib import Path

from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
CASES = (
    "benchmarks/private/output/h1-publication-metadata-v1/packaged.xml",
    "benchmarks/private/output/h1-real/esa-e20240135/candidate.xml",
)


def main():
    rows = []
    for case, path in enumerate(CASES):
        tree = etree.parse(
            str(ROOT / path), etree.XMLParser(resolve_entities=False, no_network=True)
        )
        rows.append(
            {
                "case": case,
                "affiliations": [
                    {
                        "country_code": node.find("country").get("country")
                        if node.find("country") is not None
                        else None,
                        "country_is_india": node.findtext("country") == "India",
                        "country_is_brazil": node.findtext("country") in {"Brazil", "Brasil"},
                    }
                    for node in tree.xpath("//article-meta/aff")
                ],
                "contributors": [
                    {
                        "type": node.get("contrib-type"),
                        "affiliation_links": len(node.xpath("xref[@ref-type='aff']")),
                        "orcid_present": bool(node.xpath("contrib-id[@contrib-id-type='orcid']")),
                    }
                    for node in tree.xpath("//contrib")
                ],
            }
        )
    print(json.dumps(rows))


if __name__ == "__main__":
    main()
