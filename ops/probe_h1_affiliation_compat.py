"""Synthetic native positive/negative matrix; no corpus, network or report content."""

import json

from affiliation_compat import install
from lxml import etree


def cases():
    def document(xref, aff='<aff id="aff1"/>', extra=""):
        return etree.fromstring(
            (
                '<article><front><article-meta><contrib-group><contrib contrib-type="author">'
                "<name><surname>Example</surname><given-names>A</given-names></name>"
                f"{xref}</contrib></contrib-group>{aff}</article-meta></front>{extra}</article>"
            ).encode()
        )

    yield "valid", document('<xref ref-type="aff" rid="aff1"/>'), "OK"
    yield "missing-target", document('<xref ref-type="aff" rid="missing"/>'), "ERROR"
    yield "no-reference", document(""), "ERROR"
    yield "wrong-type", document('<xref ref-type="fn" rid="aff1"/>'), "ERROR"
    yield (
        "duplicate-id",
        document('<xref ref-type="aff" rid="aff1"/>', '<aff id="aff1"/><aff id="aff1"/>'),
        "ERROR",
    )
    yield "mixed-targets", document('<xref ref-type="aff" rid="aff1 missing"/>'), "ERROR"
    yield (
        "multiple-targets",
        document('<xref ref-type="aff" rid="aff1 aff2"/>', '<aff id="aff1"/><aff id="aff2"/>'),
        "OK",
    )
    yield "empty-rid", document('<xref ref-type="aff" rid=" "/>'), "ERROR"
    yield (
        "non-aff-target",
        document('<xref ref-type="aff" rid="aff1"/>', '<fn id="aff1"/>'),
        "ERROR",
    )
    yield (
        "out-of-scope",
        document(
            '<xref ref-type="aff" rid="aff1"/>',
            "",
            '<sub-article><front-stub><aff id="aff1"/></front-stub></sub-article>',
        ),
        "ERROR",
    )


def main():
    from packtools.sps.validation.article_contribs import TextContribsValidation

    fixtures = list(cases())
    before = [list(TextContribsValidation(root, {}).validate()) for _, root, _ in fixtures]
    install()
    install()  # idempotent inside an adapter process
    rows = []
    for (name, root, expected), old in zip(fixtures, before, strict=True):
        original_xml = etree.tostring(root)
        result = list(TextContribsValidation(root, {}).validate())
        responses = [item.get("response") for item in result if item.get("title") == "affiliation"]

        def other_findings(items):
            return [
                (r.get("title"), r.get("response"), r.get("item"), r.get("sub_item"))
                for r in items
                if r.get("title") != "affiliation"
            ]

        rows.append(
            {
                "case": name,
                "expected": expected,
                "responses": responses,
                "other_rule_decisions_unchanged": other_findings(old) == other_findings(result),
                "xml_unchanged": etree.tostring(root) == original_xml,
                "passed": responses == [expected],
            }
        )
    passed = all(
        r["passed"] and r["other_rule_decisions_unchanged"] and r["xml_unchanged"] for r in rows
    )
    print(json.dumps({"synthetic_only": True, "passed": passed, "cases": rows}))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
