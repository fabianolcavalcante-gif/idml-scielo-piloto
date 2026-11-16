import pytest
from lxml import etree

from ops.audit_vh1_reference_metadata import inventory
from tests.test_vh1_reference_metadata_delta import AFTER


def source_text(xml=AFTER):
    return [etree.fromstring(xml).findtext(".//mixed-citation")]


def test_audit_reports_only_hashes_counts_and_source_offsets():
    result = inventory(AFTER, AFTER, source_text())
    assert result["types"] == {"journal": 1}
    assert result["reference_count"] == 1
    assert result["unresolved_type_positions"] == []
    assert "Title" not in str(result)
    assert result["literal_text_coverage_only_not_semantic_approval"]


@pytest.mark.parametrize(
    "path", [".//year", ".//person-group/name/given-names", ".//mixed-citation"]
)
def test_established_identity_fields_cannot_be_changed_by_type_repair(path):
    tree = etree.fromstring(AFTER)
    tree.find(path).text = "Changed"
    with pytest.raises(ValueError):
        inventory(AFTER, etree.tostring(tree), source_text())


def test_inventory_requires_actual_idml_text_not_only_candidate_text():
    with pytest.raises(ValueError, match="reference_not_in_idml"):
        inventory(AFTER, AFTER, ["Other story"])


def test_non_literal_new_field_cannot_be_certified():
    tree = etree.fromstring(AFTER)
    etree.SubElement(tree.find(".//element-citation"), "publisher-name").text = "Invented publisher"
    with pytest.raises(ValueError, match="structured_text_not_literal"):
        inventory(AFTER, etree.tostring(tree), source_text())


def test_unknown_type_remains_explicitly_unresolved():
    tree = etree.fromstring(AFTER)
    tree.find(".//element-citation").set("publication-type", "other")
    result = inventory(AFTER, etree.tostring(tree), source_text())
    assert result["unresolved_type_positions"] == [1]


def test_missing_or_reordered_references_do_not_pass():
    tree = etree.fromstring(AFTER)
    tree.find(".//ref").set("id", "new")
    with pytest.raises(ValueError, match="reference_identity_changed"):
        inventory(AFTER, etree.tostring(tree), source_text())
