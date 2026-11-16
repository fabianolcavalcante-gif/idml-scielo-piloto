import copy

import pytest
from lxml import etree

from ops.qualify_vh1_references import inspect_delta, verify_delta

BEFORE = b"""<article><front><title>Same title</title></front><body>
<p id="p">Same science <xref ref-type="bibr" rid="r1">Doe (2010)</xref>.</p>
</body><back><ref-list><ref id="r1"><label>1</label>
<mixed-citation>DOE, H. J. Title. Source, p. 1-2, 2010.</mixed-citation>
<element-citation publication-type="journal"><person-group person-group-type="author">
<name><surname>DOE</surname><given-names>H</given-names></name></person-group>
<article-title>J. Title</article-title><source>1-2</source><year>2010</year>
<fpage>1</fpage><lpage>2</lpage></element-citation></ref></ref-list></back></article>"""
AFTER = (
    BEFORE.replace(b">H<", b">H. J.<")
    .replace(b">J. Title<", b">Title<")
    .replace(b"<source>1-2</source>", b"<source>Source</source>")
)


def test_exact_reviewed_fields_preserve_the_rest_of_the_xml():
    delta = verify_delta(BEFORE, AFTER, inspect_delta(BEFORE, AFTER))
    assert delta["changed_references"] == 1
    assert len(delta["fields"]) == 3
    assert delta["all_other_xml_unchanged"]
    assert delta["mixed_citations_unchanged"]


@pytest.mark.parametrize(
    "mutation",
    [
        "body",
        "xref",
        "title",
        "year",
        "page",
        "mixed",
        "id",
        "author",
        "source",
        "publication_type",
        "missing",
        "duplicate",
        "tail",
        "invention",
    ],
)
def test_unreviewed_reference_or_unrelated_mutations_fail(mutation):
    tree = etree.fromstring(AFTER)
    changes = {
        "body": ("body/p", "Changed science"),
        "title": ("front/title", "Other title"),
        "year": (".//year", "2024"),
        "page": (".//lpage", "3"),
        "mixed": (".//mixed-citation", "Other citation"),
        "author": (".//given-names", "H."),
        "source": (".//source", "Title"),
        "invention": (".//source", "Invented journal"),
    }
    if mutation in changes:
        path, value = changes[mutation]
        tree.find(path).text = value
    elif mutation == "xref":
        tree.find(".//xref").set("rid", "r2")
    elif mutation == "id":
        tree.find(".//ref").set("id", "r2")
    elif mutation == "publication_type":
        tree.find(".//element-citation").set("publication-type", "book")
    elif mutation == "missing":
        node = tree.find(".//source")
        node.getparent().remove(node)
    elif mutation == "duplicate":
        node = tree.find(".//ref")
        node.getparent().append(copy.deepcopy(node))
    elif mutation == "tail":
        tree.find(".//article-title").tail = "Changed"
    with pytest.raises(ValueError):
        verify_delta(BEFORE, etree.tostring(tree), inspect_delta(BEFORE, AFTER))


def test_reviewer_contract_cannot_omit_a_change():
    with pytest.raises(ValueError, match="unreviewed_reference_fields"):
        verify_delta(BEFORE, AFTER, inspect_delta(BEFORE, AFTER)[:-1])
