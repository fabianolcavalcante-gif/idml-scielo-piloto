import pytest
from lxml import etree

from ops import audit_vh1_references as audit


def case():
    refs = (
        '<back><ref-list><ref id="r1"><mixed-citation>'
        "DOE, Ana; ROE, Jane. Title. Source, 2018.</mixed-citation>"
        "<element-citation><year>2018</year></element-citation></ref>"
        '<ref id="r2"><mixed-citation>DOE, Ana. Other work, 1998.</mixed-citation>'
        "<element-citation><year>1998</year></element-citation></ref></ref-list></back>"
    )
    source = ["Doe and Roe (2018)", "DOE, Ana; ROE, Jane. Title. Source, 2018."]
    old = etree.fromstring(
        '<article><body><p>Doe and Roe (<xref ref-type="bibr" rid="r2">2018</xref>)</p></body>'
        + refs
        + "</article>"
    )
    new = etree.fromstring(
        '<article><body><p>Doe and Roe (<xref ref-type="bibr" rid="r1">2018</xref>)</p></body>'
        + refs
        + "</article>"
    )
    return old, new, source


def test_postbuild_adjudication_keeps_source_qualified_target(monkeypatch):
    monkeypatch.setattr(audit, "PATTERNS", ((r"Doe and Roe \(2018\)", 1, [2]),))
    rows = audit.adjudicate(*case())
    assert len(rows) == 1
    assert rows[0]["decision"] == "gold_target_year_conflict"
    assert rows[0]["candidate_preserved"]
    assert "Title" not in str(rows)


@pytest.mark.parametrize(
    "mutation", ["source", "reference", "year", "target", "duplicate", "gold", "text"]
)
def test_adjudication_rejects_unverified_source_or_target(monkeypatch, mutation):
    monkeypatch.setattr(audit, "PATTERNS", ((r"Doe and Roe \(2018\)", 1, [2]),))
    old, new, source = case()
    if mutation == "source":
        source[0] = "Other citation"
    elif mutation == "reference":
        source[1] = "Other reference"
    elif mutation == "year":
        new.find(".//year").text = "2000"
    elif mutation == "target":
        new.find(".//xref").set("rid", "r2")
    elif mutation == "duplicate":
        source.append(source[0])
    elif mutation == "gold":
        old.find(".//xref").set("rid", "r1")
    elif mutation == "text":
        new.find(".//xref").text = "2010"
    with pytest.raises(ValueError):
        audit.adjudicate(old, new, source)
