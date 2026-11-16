import copy

import pytest

from ops.qualify_vh1_final_validation import inspect_delta, verify_delta
from ops.triage_vh1_final_warnings import CODES, classify, structural_evidence

OLD = (
    b'<article><front><article-meta><aff id="a"><institution content-type="original">'
    b"Example, Graduate School of X, Department of Y - City.</institution>"
    b'<institution content-type="orgdiv1">Graduate School of X, Department of Y</institution>'
    b"</aff></article-meta></front><body><p>Preserve</p></body></article>"
)
NEW = OLD.replace(
    b'content-type="orgdiv1">Graduate School of X, Department of Y',
    b'content-type="orgdiv1">Graduate School of X</institution>'
    b'<institution content-type="orgdiv2">Department of Y',
)


def test_only_source_literal_hierarchy_delta_is_allowed():
    expected = inspect_delta(OLD, NEW)
    assert verify_delta(OLD, NEW, expected)["all_other_xml_unchanged"]
    assert verify_delta(OLD, OLD, [])["changed_affiliations"] == 0


@pytest.mark.parametrize(
    "mutation",
    [
        "text",
        "original",
        "id",
        "type",
        "extra_attribute",
        "missing_division",
        "duplicate",
        "other_xml",
        "unknown_change",
    ],
)
def test_delta_rejects_loss_and_unrelated_changes(mutation):
    expected = inspect_delta(OLD, NEW)
    candidate = NEW
    if mutation == "text":
        candidate = candidate.replace(b">Department of Y<", b">Department of Z<")
    elif mutation == "original":
        candidate = candidate.replace(b"Y - City", b"Y - Other City")
    elif mutation == "id":
        candidate = candidate.replace(b'id="a"', b'id="b"')
    elif mutation == "type":
        candidate = candidate.replace(b"orgdiv2", b"orgdiv3")
    elif mutation == "extra_attribute":
        candidate = candidate.replace(
            b'content-type="orgdiv2"', b'content-type="orgdiv2" invented="yes"'
        )
    elif mutation == "missing_division":
        candidate = OLD
    elif mutation == "duplicate":
        candidate = candidate.replace(
            b"</aff>", b'<institution content-type="orgdiv2">Department of Y</institution></aff>'
        )
    elif mutation == "other_xml":
        candidate = candidate.replace(b"Preserve", b"Changed")
    else:
        expected = []
    with pytest.raises(ValueError):
        verify_delta(OLD, candidate, expected)


XML = (
    '<article><front><article-meta><aff id="a"><institution content-type="original">'
    "Example, Department of X \u2013 City.</institution>"
    '<institution content-type="orgname">Example</institution>'
    '<institution content-type="orgdiv1">Department of X</institution>'
    '</aff></article-meta></front><body><sec id="s"><title>Methods</title>'
    '<sec id="child"><title>Detail</title><p>Present</p></sec></sec></body></article>'
).encode()


def runs():
    return [
        dict(
            name=name,
            counts={"warning": 3},
            findings=[
                dict(code=code, response="warning", message="private-marker") for code in codes
            ],
        )
        for name, codes in CODES.items()
    ]


def test_classification_preserves_findings_and_does_not_accept_them():
    native = runs()
    original = copy.deepcopy(native)
    result = classify(XML, native)
    assert native == original
    assert result["all_warnings_classified"]
    for run in result["validators"]:
        assert all(
            d["severity_retained"] == "warning" and not d["accepted_for_release"]
            for d in run["decisions"]
        )
    assert "private-marker" not in str(result)
    assert "Department of X" not in str(result)


@pytest.mark.parametrize(
    "mutation",
    ["unknown", "error", "missing", "duplicate", "count", "tool_missing", "tool_duplicate"],
)
def test_unclassified_or_missing_finding_is_never_accepted(mutation):
    native = runs()
    if mutation == "unknown":
        native[0]["findings"][0]["code"] = "unknown"
    elif mutation == "error":
        native[0]["findings"][0]["response"] = "error"
    elif mutation == "missing":
        native[0]["findings"].pop()
    elif mutation == "duplicate":
        native[0]["findings"].append(copy.deepcopy(native[0]["findings"][0]))
    elif mutation == "count":
        native[0]["counts"]["warning"] = 0
    elif mutation == "tool_missing":
        native.pop()
    else:
        native[1]["name"] = native[0]["name"]
    with pytest.raises(ValueError):
        classify(XML, native)


@pytest.mark.parametrize(
    "mutation",
    [
        "org_missing",
        "two_divisions",
        "source_changed",
        "app_link",
        "empty_app_group",
        "empty_sec",
        "title_missing",
        "child_empty",
        "child_title_missing",
        "other_child",
    ],
)
def test_specific_structural_evidence_required_for_warning_classification(mutation):
    xml = XML
    if mutation == "org_missing":
        xml = xml.replace(b'content-type="orgname"', b'content-type="unknown"')
    elif mutation == "two_divisions":
        xml = xml.replace(b">Department of X<", b">School of Y, Department of X<")
    elif mutation == "source_changed":
        xml = xml.replace(b"Example, Department", b"Other, Department")
    elif mutation == "app_link":
        xml = xml.replace(
            b"</article>", b'<back><p><xref ref-type="app" rid="missing"/></p></back></article>'
        )
    elif mutation == "empty_app_group":
        xml = xml.replace(b"</article>", b"<back><app-group/></back></article>")
    elif mutation == "empty_sec":
        xml = xml.replace(b'<sec id="child"><title>Detail</title><p>Present</p></sec>', b"")
    elif mutation == "title_missing":
        xml = xml.replace(b"<title>Methods</title>", b"")
    elif mutation == "child_empty":
        xml = xml.replace(b"<p>Present</p>", b"")
    elif mutation == "child_title_missing":
        xml = xml.replace(b"<title>Detail</title>", b"")
    else:
        xml = xml.replace(b"<title>Methods</title>", b"<title>Methods</title><fig/>")
    with pytest.raises(ValueError):
        structural_evidence(xml)
