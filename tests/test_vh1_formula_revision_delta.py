"""Independent preservation tests; scientific source strings stay in the private corpus."""

import hashlib

import pytest
from lxml import etree

from ops.qualify_vh1_formula_revisions import math_bytes, verify_delta

MATH = (
    '<m:math xmlns:m="http://www.w3.org/1998/Math/MathML" display="block" id="m1">'
    "<m:mi>H</m:mi><m:mi>a</m:mi><m:mi>k</m:mi></m:math>"
)


def fixture():
    old = (
        '<article><p>preserved prose</p><disp-formula id="f1">'
        + MATH
        + '</disp-formula><p><xref ref-type="disp-formula" rid="f1">1</xref></p></article>'
    ).encode()
    new = old.replace(b">a<", b">g<")

    def digest(xml):
        root = etree.fromstring(xml)
        return hashlib.sha256(math_bytes(root[1][0])).hexdigest()

    changes = [{"before_sha256": digest(old), "after_sha256": digest(new)}]
    return old, new, changes


def test_g_a_correction_is_detected_and_only_reviewed_change_is_allowed():
    old, new, changes = fixture()
    assert verify_delta(old, new, changes)["all_other_xml_unchanged"]
    assert len(verify_delta(old, new, changes)["changes"]) == 1
    with pytest.raises(ValueError, match="formula_delta_outside_review"):
        verify_delta(old, old, changes)


@pytest.mark.parametrize(
    "mutation",
    [
        "prose",
        "other_symbol",
        "id",
        "formula_id",
        "link",
        "display",
        "missing",
        "extra",
        "tail",
        "math_attribute",
    ],
)
def test_unreviewed_changes_are_rejected(mutation):
    old, new, changes = fixture()
    root = etree.fromstring(new)
    math = root[1][0]
    if mutation == "prose":
        root[0].text = "changed"
    elif mutation == "other_symbol":
        math[0].text = "Z"
    elif mutation == "id":
        math.set("id", "m2")
    elif mutation == "formula_id":
        root[1].set("id", "f2")
    elif mutation == "link":
        root[2][0].set("rid", "f2")
    elif mutation == "display":
        math.set("display", "inline")
    elif mutation == "missing":
        root.remove(root[1])
    elif mutation == "extra":
        root.append(etree.fromstring(MATH.encode()))
    elif mutation == "tail":
        math.tail = "new words"
    elif mutation == "math_attribute":
        math.set("mathvariant", "bold")
    with pytest.raises(ValueError):
        verify_delta(old, etree.tostring(root), changes)


def test_math_delta_requires_exact_multiplicity_and_expected_after_hash():
    old, new, changes = fixture()
    for wrong in ([], changes + changes, [{**changes[0], "after_sha256": "0" * 64}]):
        with pytest.raises(ValueError):
            verify_delta(old, new, wrong)
