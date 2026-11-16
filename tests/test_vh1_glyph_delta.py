import copy

import pytest
from lxml import etree

from ops.qualify_vh1_formula_revisions import math_bytes, sha
from ops.qualify_vh1_glyphs import NS, POSITIONS, unwrap, verify_delta


def fixture():
    root = etree.Element("article", nsmap={"m": NS["m"]})
    body = etree.SubElement(root, "body")
    for identifier, counts in POSITIONS.items():
        p = etree.SubElement(body, "p", id=identifier)
        p.text = "\u0404 \u00d8 text "
        for value, count in counts.items():
            for _ in range(count):
                etree.SubElement(p, "sub").text = value
        etree.SubElement(p, "sub").text = "i"
    formula = etree.SubElement(body, "inline-formula", id="formula-1")
    math = etree.SubElement(formula, "{" + NS["m"] + "}math", display="inline", id="math-1")
    etree.SubElement(math, "{" + NS["m"] + "}mi").text = "A"
    before = etree.tostring(root)
    updated = copy.deepcopy(root)
    for p in updated.xpath(".//p"):
        for node in list(p.findall("sub")):
            if node.text != "i":
                unwrap(node)
    new_math = updated.xpath(".//m:math", namespaces=NS)[0]
    new_math[0].set("mathvariant", "script")
    changes = [{"before_sha256": sha(math_bytes(math)), "after_sha256": sha(math_bytes(new_math))}]
    return before, updated, changes


def test_only_fourteen_source_normal_runs_and_reviewed_formula_change():
    before, updated, changes = fixture()
    result = verify_delta(before, etree.tostring(updated), changes, first=False)
    assert len(result["source_normal_positions"]) == 14
    assert len(result["changes"]) == 1
    assert result["all_other_xml_unchanged"]


@pytest.mark.parametrize(
    "mutation",
    [
        "retain_sub",
        "remove_index",
        "text",
        "cyrillic",
        "empty_set",
        "math",
        "tail",
        "parent",
        "id",
        "duplicate",
        "header",
        "extra_style",
    ],
)
def test_scientific_or_unreviewed_change_rejected(mutation):
    before, updated, changes = fixture()
    p = updated.find("body/p")
    if mutation == "retain_sub":
        etree.SubElement(p, "sub").text = "\u2190"
    elif mutation == "remove_index":
        unwrap(p.find("sub"))
    elif mutation in {"text", "cyrillic", "empty_set"}:
        p.text = p.text.replace(
            {"text": "text", "cyrillic": "\u0404", "empty_set": "\u00d8"}[mutation], "changed"
        )
    elif mutation == "math":
        updated.xpath(".//m:mi", namespaces=NS)[0].text = "B"
    elif mutation == "tail":
        p.tail = "extra"
    elif mutation == "parent":
        p.set("id", "other")
    elif mutation == "id":
        updated.xpath(".//m:math", namespaces=NS)[0].set("id", "other")
    elif mutation == "duplicate":
        updated.find("body").append(copy.deepcopy(p))
    elif mutation == "header":
        etree.SubElement(updated, "front")
    elif mutation == "extra_style":
        p.set("style", "other")
    with pytest.raises(ValueError):
        verify_delta(before, etree.tostring(updated), changes, first=False)


def test_unchanged_first_article_is_required():
    xml = b"<article><body><p>unchanged</p></body></article>"
    assert verify_delta(xml, xml, [], first=True)["source_normal_positions"] == []
    with pytest.raises(ValueError):
        verify_delta(xml, xml.replace(b"unchanged", b"changed"), [], first=True)


@pytest.mark.parametrize("mutation", ["count", "nested", "attribute", "duplicate_parent"])
def test_baseline_positions_cannot_be_ambiguous(mutation):
    before, updated, changes = fixture()
    old = etree.fromstring(before)
    p = old.find("body/p")
    node = p.find("sub")
    if mutation == "count":
        p.remove(node)
    elif mutation == "nested":
        etree.SubElement(node, "italic").text = "extra"
    elif mutation == "attribute":
        node.set("id", "extra")
    else:
        old.find("body").append(copy.deepcopy(p))
    with pytest.raises(ValueError):
        verify_delta(etree.tostring(old), etree.tostring(updated), changes, first=False)
