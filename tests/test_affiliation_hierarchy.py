import copy
from pathlib import Path

import pytest
from lxml import etree

from idml_foundation.domain.canonical import Affiliation
from idml_foundation.pipeline.affiliation_hierarchy import institution_divisions
from idml_foundation.pipeline.jats_builder import JatsBuilder
from idml_foundation.pipeline.validation import OfflineJatsValidator
from ops.v05_fixture import complete_article


def affiliation():
    def sourced(value, transformation):
        return dict(
            value=value, state="present", evidence_ids=["source-1"], transformation=transformation
        )

    return Affiliation(
        id="aff1",
        evidence_ids=("source-1",),
        institution=sourced("Example University", "deterministic-affiliation-decomposition"),
        department=sourced(
            "Graduate School of Sciences, Department of Systems",
            "deterministic-affiliation-decomposition",
        ),
        original_text=sourced(
            "Example University, Graduate School of Sciences, Department of Systems"
            " \u2013 City, Country.",
            "line-from-affiliation-style",
        ),
    )


def test_lossless_hierarchy_rendering_does_not_mutate_canonical():
    value = affiliation()
    before = value.model_dump()
    assert institution_divisions(value) == ("Graduate School of Sciences", "Department of Systems")
    assert ", ".join(institution_divisions(value)) == value.department.value
    assert value.model_dump() == before


@pytest.mark.parametrize("field", ["institution", "department", "original_text"])
@pytest.mark.parametrize(
    "change", ["missing_evidence", "other_evidence", "state", "alternatives", "edited"]
)
def test_uncertain_or_edited_evidence_never_causes_a_split(field, change):
    data = affiliation().model_dump(mode="json")
    node = data[field]
    if change == "missing_evidence":
        node["evidence_ids"] = []
    elif change == "other_evidence":
        node["evidence_ids"] = ["unrelated"]
    elif change == "state":
        node["state"] = "needs_review"
    elif change == "alternatives":
        node["alternatives"] = ["different"]
    else:
        node["transformation"] = "human-edited"
    value = Affiliation.model_validate(data)
    assert institution_divisions(value) == (value.department.value,)


@pytest.mark.parametrize(
    "text",
    [
        "Department of Systems",
        "School of Sciences, Department of Systems",
        "Department of Systems, Graduate School of Sciences",
        "Graduate School of Sciences, Division of Systems",
        "Graduate School of Sciences, Department of Systems, Laboratory X",
        "Graduate School of Sciences; Department of Systems",
        "Graduate School of Sciences,  Department of Systems",
        "Graduate School of Sciences, Department of Systems\nOther",
    ],
)
def test_unqualified_syntax_is_preserved_without_guessing(text):
    data = affiliation().model_dump(mode="json")
    data["department"]["value"] = text
    data["original_text"]["value"] = "Example University, " + text + " \u2013 City, Country."
    value = Affiliation.model_validate(data)
    assert institution_divisions(value) == (text,)


@pytest.mark.parametrize(
    "change",
    [
        "no_original",
        "no_department",
        "empty_department",
        "no_aff_evidence",
        "wrong_original",
        "wrong_institution",
    ],
)
def test_absent_or_unbound_literal_source(change):
    data = affiliation().model_dump(mode="json")
    if change == "no_original":
        data["original_text"] = None
    elif change == "no_department":
        data["department"] = None
    elif change == "empty_department":
        data["department"].update(value=None, state="missing")
    elif change == "no_aff_evidence":
        data["evidence_ids"] = []
    elif change == "wrong_original":
        data["original_text"]["value"] += " "
        data["original_text"]["value"] = "Different " + data["original_text"]["value"]
    else:
        data["institution"]["value"] = "Different University"
    value = Affiliation.model_validate(data)
    assert institution_divisions(value) == (
        () if change in {"no_department", "empty_department"} else (value.department.value,)
    )


def test_real_builder_emits_two_levels_and_original_with_dtd_validity():
    article = complete_article()
    value = affiliation().model_copy(update={"id": article.front.affiliations[0].id})
    article = article.model_copy(
        update={"front": article.front.model_copy(update={"affiliations": (value,)})}
    )
    before = copy.deepcopy(article.model_dump())
    xml = JatsBuilder().build(article)
    root = etree.fromstring(xml)
    aff = root.find("front/article-meta/aff")
    assert aff.findtext("institution[@content-type='orgdiv2']") == "Department of Systems"
    assert aff.findtext("institution[@content-type='original']") == value.original_text.value
    assert (
        OfflineJatsValidator(Path(__file__).parents[1] / "vendor/jats/1.3")
        .validate(xml, asset_names={a.logical_name for a in article.assets})
        .valid
    )
    assert JatsBuilder().build(article) == xml
    assert article.model_dump() == before
