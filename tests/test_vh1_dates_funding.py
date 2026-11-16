import hashlib
import json
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from lxml import etree

from idml_foundation.ai.security import payload_digest
from idml_foundation.domain.canonical import FieldState
from idml_foundation.pipeline.funding_parser import parse_funding
from idml_foundation.pipeline.jats_builder import JatsBuilder
from idml_foundation.pipeline.profile import load_profile
from idml_foundation.pipeline.service import DeterministicPipeline
from idml_foundation.pipeline.validation import OfflineJatsValidator
from idml_foundation.publication_dates import publication_parts
from idml_foundation.release.formal_metadata import (
    FormalMetadataAuthorityCatalog,
    _publication_date,
    build_formal_metadata_authority_catalog,
)
from ops.v05_fixture import complete_article
from tests.domain_helpers import canonical_article, sourced
from tests.phase3_helpers import synthetic_idml
from tests.test_formal_metadata import _response

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "parts,expected", [([2025], "2025"), ([2025, 7], "2025-07"), ([2024, 2, 29], "2024-02-29")]
)
def test_crossref_keeps_exact_precision(parts, expected):
    assert _publication_date({"published-online": {"date-parts": [parts]}}) == expected


def test_crossref_compatible_dates_refine_not_truncate():
    assert (
        _publication_date(
            {
                "published": {"date-parts": [[2025]]},
                "issued": {"date-parts": [[2025, 7]]},
                "published-online": {"date-parts": [[2025, 7, 11]]},
                "created": {"date-parts": [[2024, 1, 1]]},
            }
        )
        == "2025-07-11"
    )


@pytest.mark.parametrize(
    "parts",
    [
        [],
        [[]],
        [[True]],
        [[2025, False]],
        [[2025, 0]],
        [[2025, 13]],
        [[2025, 2, 29]],
        [[2025, 7, 32]],
        [[2025, 1, 1, 0]],
        [["2025"]],
        [[2025], [2024]],
        [[25]],
        [[2100]],
        None,
    ],
)
def test_crossref_invalid_or_ambiguous_parts_fail_closed(parts):
    with pytest.raises(ValueError):
        _publication_date({"published": {"date-parts": parts}})


@pytest.mark.parametrize("other", [[2024], [2025, 8], [2025, 7, 12]])
def test_crossref_conflicts_not_resolved_by_priority(other):
    with pytest.raises(ValueError, match="conflict"):
        _publication_date(
            {
                "published-online": {"date-parts": [[2025, 7, 11]]},
                "issued": {"date-parts": [other]},
            }
        )


def test_deposit_date_is_not_a_publication_date():
    with pytest.raises(ValueError, match="no publication date"):
        _publication_date({"created": {"date-parts": [[2025, 7, 11]]}})


@pytest.mark.parametrize("value", ["2025-00", "2025-13", "2025-02-29", "2025-7", "2025-07-1"])
def test_invalid_date_cannot_enter_catalog_even_with_valid_digest(value):
    catalog, _ = build_formal_metadata_authority_catalog(
        article=canonical_article(),
        source_idml_sha256="a" * 64,
        crossref_response=_response(),
        corpus_id="synthetic",
    )
    body = catalog.model_dump(mode="json", exclude={"catalog_id"})
    body["publication_date"] = value
    with pytest.raises(ValueError):
        FormalMetadataAuthorityCatalog.model_validate({**body, "catalog_id": payload_digest(body)})


@pytest.mark.parametrize("value", ["2025", "2025-07", "2025-07-11"])
def test_builder_preserves_partial_dates_without_fake_history(value):
    article = complete_article()
    article = article.model_copy(
        update={"front": article.front.model_copy(update={"publication_date": sourced(value)})}
    )
    xml = JatsBuilder().build(article)
    root = etree.fromstring(xml)
    node = root.find('front/article-meta/pub-date[@date-type="pub"]')
    parts = publication_parts(value)
    assert node.findtext("year") == "2025"
    assert node.findtext("month") == ("07" if len(parts) >= 2 else None)
    assert node.findtext("day") == ("11" if len(parts) == 3 else None)
    assert len(root.xpath('front/article-meta/history/date[@date-type="pub"]')) == (len(parts) == 3)
    assert root.findtext('front/article-meta/pub-date[@date-type="collection"]/year') == "2025"
    assert (
        OfflineJatsValidator(ROOT / "vendor/jats/1.3")
        .validate(xml, asset_names={a.logical_name for a in article.assets})
        .valid
    )


def reference_xml(day="11"):
    return (
        f'<article><front><article-meta><article-id pub-id-type="doi">10.1/example</article-id>'
        f'<pub-date date-type="pub"><day>{day}</day><month>07</month><year>2025</year>'
        "</pub-date></article-meta></front></article>"
    ).encode()


def test_reference_precision_has_reference_evidence_not_crossref_evidence():
    source = reference_xml()
    catalog, _ = build_formal_metadata_authority_catalog(
        article=canonical_article(),
        source_idml_sha256="a" * 64,
        crossref_response=_response(),
        corpus_id="synthetic",
        formal_reference_xml=source,
    )
    article = canonical_article()
    article = article.model_copy(
        update={"front": article.front.model_copy(update={"publication_date": sourced("2025")})}
    )
    result = catalog.apply(article, source_idml_sha256="a" * 64)
    value = result.front.publication_date
    evidence = next(item for item in result.evidence if item.id in value.evidence_ids)
    assert value.value == "2025-07-11"
    assert evidence.locator.artifact_sha256 == hashlib.sha256(source).hexdigest()
    volume_evidence = next(
        item for item in result.evidence if item.id in result.front.volume.evidence_ids
    )
    assert volume_evidence.locator.artifact_sha256 == hashlib.sha256(_response()).hexdigest()


def test_reference_cannot_override_conflicting_crossref_day():
    response = json.loads(_response())
    response["message"]["published-online"]["date-parts"] = [[2025, 7, 12]]
    with pytest.raises(ValueError, match="conflicts"):
        build_formal_metadata_authority_catalog(
            article=canonical_article(),
            source_idml_sha256="a" * 64,
            crossref_response=json.dumps(response).encode(),
            corpus_id="synthetic",
            formal_reference_xml=reference_xml(),
        )


@pytest.mark.parametrize("current", ["2024", "2025-08", "2025-07-12"])
def test_catalog_will_not_overwrite_conflicting_existing_date(current):
    catalog, _ = build_formal_metadata_authority_catalog(
        article=canonical_article(),
        source_idml_sha256="a" * 64,
        crossref_response=_response(),
        corpus_id="synthetic",
        formal_reference_xml=reference_xml(),
    )
    article = canonical_article()
    article = article.model_copy(
        update={"front": article.front.model_copy(update={"publication_date": sourced(current)})}
    )
    with pytest.raises(ValueError, match="conflicts"):
        catalog.apply(article, source_idml_sha256="a" * 64)


def test_catalog_cannot_downgrade_precision():
    catalog, _ = build_formal_metadata_authority_catalog(
        article=canonical_article(),
        source_idml_sha256="a" * 64,
        crossref_response=_response(),
        corpus_id="synthetic",
    )
    article = canonical_article()
    article = article.model_copy(
        update={
            "front": article.front.model_copy(update={"publication_date": sourced("2025-07-11")})
        }
    )
    with pytest.raises(ValueError, match="conflicts"):
        catalog.apply(article, source_idml_sha256="a" * 64)


@pytest.mark.parametrize(
    "value,agency,award",
    [
        ("Foundation Alpha, grant 123.", "Foundation Alpha", "123"),
        ("Foundation Alpha, grant number #AB-123/25.", "Foundation Alpha", "AB-123/25"),
        (
            "Funder: Ministry of Science, Technology and Research; Award: #21.02.00.",
            "Ministry of Science, Technology and Research",
            "21.02.00",
        ),
    ],
)
def test_explicit_funder_award_grammar(value, agency, award):
    parsed = parse_funding(value)
    assert (parsed.agency, parsed.award, parsed.explicit_none) == (agency, award, False)


@pytest.mark.parametrize(
    "value",
    [
        "Alpha, Ministry of Science, Technology and Research, and Beta, Project A, #21.02.00.",
        "Foundation Alpha and Foundation Beta, grant 123.",
        "Foundation Alpha & Foundation Beta, grant 123.",
        "Foundation Alpha, grant 123 and 456.",
        "Foundation Alpha, grant 123; Foundation Beta, grant 456.",
        "Ministry of Science, Technology and Research, grant 123.",
        "Foundation Alpha, grant 123, pending approval.",
        "No specific funding was received.",
        "none; grant 123",
        "",
        "Funder: Alpha; Award:",
    ],
)
def test_funding_does_not_guess_entity_boundaries_or_grant_links(value):
    parsed = parse_funding(value)
    assert parsed.agency is parsed.award is None
    assert parsed.explicit_none is False


@pytest.mark.parametrize("value", ["None", "None.", "none."])
def test_explicit_no_funding_remains_distinct(value):
    assert parse_funding(value).explicit_none


def test_ambiguous_funding_retains_entire_statement_and_review_evidence():
    statement = (
        "Alpha, Ministry of Science, Technology and Research, and Beta, Project A, #21.02.00."
    )
    output = BytesIO()
    with (
        ZipFile(BytesIO(synthetic_idml(include_correspondence=True))) as source,
        ZipFile(output, "w", ZIP_DEFLATED) as target,
    ):
        for name in source.namelist():
            data = source.read(name).replace(b"Foundation Alpha, grant 123.", statement.encode())
            target.writestr(name, data)
    result = DeterministicPipeline(profile=load_profile(ROOT / "profiles/esa-aop-1.1.json")).run(
        output.getvalue(), logical_name="ESA_2024001_AOP.idml"
    )
    funding = result.canonical.front.funding[0]
    assert funding.agency.value is None
    assert funding.agency.state == FieldState.NEEDS_REVIEW
    assert funding.award_id is None
    assert funding.statement.value == statement
    assert funding.agency.evidence_ids == funding.statement.evidence_ids
    assert "funding_structure_requires_authority" in result.canonical.review_reasons
    root = etree.fromstring(result.xml)
    assert not root.xpath("//award-group")
    assert root.findtext("front/article-meta/funding-group/funding-statement") == statement
    assert result.validation.valid
