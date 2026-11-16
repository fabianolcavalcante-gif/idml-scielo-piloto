"""Independent XML/package boundary tests, without private scientific corpus."""

from io import BytesIO
from zipfile import ZipFile

import pytest
from lxml import etree

from ops.qualify_vh1_formula_links import EXPECTED, verify_delta, verify_package


def documents():
    old = etree.Element("article")
    new = etree.Element("article")
    for paragraph, target, text in EXPECTED:
        for root in (old, new):
            p = etree.SubElement(root, "p", id=paragraph)
            p.text = "before "
            # Exercise unwrapping after an existing sibling as well as at p.text.
            if text == "12":
                etree.SubElement(p, "italic").text = "retained"
                p[-1].tail = " "
            if root is new:
                xref = etree.SubElement(p, "xref", rid=target, attrib={"ref-type": "disp-formula"})
                xref.text, xref.tail = text, ": after"
            elif len(p):
                p[-1].tail += text + ": after"
            else:
                p.text += text + ": after"
            formula = etree.SubElement(root, "disp-formula", id=target)
            etree.SubElement(formula, "math").text = "x=y"
    return old, new


def verify(old, new):
    return verify_delta(etree.tostring(old), etree.tostring(new), first=True)


def test_only_five_literal_links_are_accepted():
    proof = verify(*documents())
    assert len(proof["added_links"]) == 5
    assert proof["mathml_unchanged"] and proof["all_other_xml_unchanged"]


@pytest.mark.parametrize(
    "mutation",
    [
        "text",
        "math",
        "label",
        "id",
        "target",
        "kind",
        "anchor",
        "nested",
        "extra_attribute",
        "missing",
        "duplicate",
        "existing",
        "missing_destination",
        "duplicate_destination",
        "extra_link",
    ],
)
def test_other_xml_edits_are_rejected(mutation):
    old, new = documents()
    p = new.find("p")
    x = p.find("xref")
    f = new.find("disp-formula")
    if mutation == "text":
        p.text += "changed"
    elif mutation == "math":
        f.find("math").text = "x=z"
    elif mutation == "label":
        etree.SubElement(f, "label").text = "99"
    elif mutation == "id":
        p.set("id", "other")
    elif mutation == "target":
        x.set("rid", EXPECTED[1][1])
    elif mutation == "kind":
        x.set("ref-type", "fig")
    elif mutation == "anchor":
        x.text = "invented"
    elif mutation == "nested":
        etree.SubElement(x, "bold").text = "extra"
    elif mutation == "extra_attribute":
        x.set("specific-use", "extra")
    elif mutation == "missing":
        p.remove(x)
    elif mutation == "duplicate":
        etree.SubElement(p, "xref", rid=x.get("rid"))
    elif mutation == "existing":
        etree.SubElement(old.find("p"), "xref", rid=x.get("rid"))
    elif mutation == "missing_destination":
        new.remove(f)
    elif mutation == "duplicate_destination":
        etree.SubElement(new, "disp-formula", id=f.get("id"))
    elif mutation == "extra_link":
        etree.SubElement(p, "xref", rid="extra").text = "unexpected"
    with pytest.raises(ValueError):
        verify(old, new)


def test_control_article_must_be_completely_unchanged():
    xml = b"<article><p>unchanged</p></article>"
    assert verify_delta(xml, xml, first=False)["added_links"] == []
    with pytest.raises(ValueError, match="non_link_xml_change"):
        verify_delta(xml, xml.replace(b"unchanged", b"changed"), first=False)


def archive(files):
    stream = BytesIO()
    with ZipFile(stream, "w") as package:
        for name, data in files.items():
            package.writestr(name, data)
    return stream.getvalue()


def test_only_xml_and_conversion_manifest_can_change_in_package():
    files = {
        "article.xml": b"xml",
        "conversion-manifest.json": b"{}",
        "article.pdf": b"pdf",
        "fig.tif": b"image",
    }
    changed = {**files, "article.xml": b"new XML", "conversion-manifest.json": b"new manifest"}
    assert set(verify_package(archive(files), archive(changed))) == {"article.pdf", "fig.tif"}
    for invalid in ({**changed, "fig.tif": b"changed"}, {**changed, "extra": b"file"}):
        with pytest.raises(ValueError):
            verify_package(archive(files), archive(invalid))
