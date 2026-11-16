"""Synthetic positive/negative checks of the pinned upstream affiliation rule."""

import hashlib
import inspect
import json

from lxml import etree
from packtools.sps.models.article_contribs import XMLContribs
from packtools.sps.validation.article_contribs import ContribValidation, TextContribsValidation


def main():
    rows = []
    for present in (True, False):
        validator = ContribValidation(
            {"contrib_full_name": "Synthetic Author", "affs": [{"id": "aff1"}] if present else []},
            {},
        )
        results = list(validator.validate_affiliations())
        rows.append(
            {
                "affiliation_present": present,
                "responses": [result.get("response") for result in results],
            }
        )
    xml_cases = []
    for rid in ("aff1", "missing"):
        tree = etree.fromstring(
            (
                '<article><front><article-meta><contrib-group><contrib contrib-type="author">'
                "<name><surname>Example</surname><given-names>A</given-names></name>"
                f'<xref ref-type="aff" rid="{rid}">1</xref></contrib></contrib-group>'
                '<aff id="aff1"><institution content-type="orgname">Example</institution>'
                "</aff></article-meta></front></article>"
            ).encode()
        )
        xml_cases.append(
            {
                "target_exists": rid == "aff1",
                "model_resolved_affiliations": sum(
                    len(item.get("affs", [])) for item in XMLContribs(tree).all_contribs
                ),
                "rule_responses": [
                    item.get("response")
                    for item in TextContribsValidation(tree, {}).validate()
                    if item.get("title") == "affiliation"
                ],
            }
        )
    print(
        json.dumps(
            {
                "scope": "synthetic direct upstream rule, no private corpus",
                "rule_source_sha256": hashlib.sha256(
                    inspect.getsource(ContribValidation.validate_affiliations).encode()
                ).hexdigest(),
                "cases": rows,
                "xml_cases": xml_cases,
            }
        )
    )


if __name__ == "__main__":
    main()
