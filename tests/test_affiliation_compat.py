import pytest
from lxml import etree

from ops.affiliation_compat import resolved_affiliations


@pytest.mark.parametrize(
    "rid,kind,aff,expected",
    [
        ("a", "aff", '<aff id="a"/>', [{"id": "a"}]),
        ("a b", "aff", '<aff id="a"/><aff id="b"/>', [{"id": "a"}, {"id": "b"}]),
        ("a a", "aff", '<aff id="a"/>', [{"id": "a"}]),
        ("a missing", "aff", '<aff id="a"/>', []),
        ("a", "fn", '<aff id="a"/>', []),
        ("a", "aff", '<fn id="a"/>', []),
        ("a", "aff", '<aff id="a"/><aff id="a"/>', []),
        (None, "aff", '<aff id="a"/>', []),
        (" ", "aff", '<aff id="a"/>', []),
    ],
)
def test_only_unique_typed_resolved_targets_are_passed(rid, kind, aff, expected):
    root = etree.fromstring(f"<article><front>{aff}</front></article>".encode())
    contributor = {"contrib_xref": [{"rid": rid, "ref_type": kind}]}
    before = etree.tostring(root)
    assert resolved_affiliations(root.find("front"), contributor) == expected
    assert etree.tostring(root) == before
    assert "affs" not in contributor


def test_subarticle_cannot_borrow_parent_affiliation():
    root = etree.fromstring(
        b'<article><front><aff id="a"/></front><sub-article><front-stub/></sub-article></article>'
    )
    assert (
        resolved_affiliations(
            root.find("sub-article/front-stub"), {"contrib_xref": [{"rid": "a", "ref_type": "aff"}]}
        )
        == []
    )


def test_global_duplicate_id_is_ambiguous_even_across_scopes():
    root = etree.fromstring(
        b'<article><front><aff id="a"/></front>'
        b'<sub-article><front-stub><aff id="a"/></front-stub>'
        b"</sub-article></article>"
    )
    assert (
        resolved_affiliations(
            root.find("front"), {"contrib_xref": [{"rid": "a", "ref_type": "aff"}]}
        )
        == []
    )


def test_invalid_second_reference_cannot_be_masked_by_valid_first():
    root = etree.fromstring(b'<article><front><aff id="a"/></front></article>')
    assert (
        resolved_affiliations(
            root.find("front"),
            {
                "contrib_xref": [
                    {"rid": "a", "ref_type": "aff"},
                    {"rid": "missing", "ref_type": "aff"},
                ]
            },
        )
        == []
    )
