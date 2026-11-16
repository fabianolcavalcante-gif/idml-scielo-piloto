from datetime import timedelta

import pytest

from idml_foundation.release.xpm_query_requirements import (
    ENDPOINT,
    NATIVE_PROOF_SHA256,
    NORMATIVE_SHA256,
    VENDOR_FILES,
    WaytaRequirementEvidence,
    WaytaServiceObservation,
    assess_wayta_requirement,
)
from tests.test_xpm_compatibility import inputs as doi_inputs  # noqa: F401
from tests.test_xpm_compatibility import rebind
from tests.test_xpm_sps_compatibility import bind_modern
from tests.test_xpm_sps_compatibility import data as sps_inputs  # noqa: F401

AFF = (
    '<aff id="a1"><institution content-type="original">University, City, Brazil</institution>'
    '<institution content-type="orgname">University</institution>'
    '<addr-line><named-content content-type="city">City</named-content>'
    '<named-content content-type="state">State</named-content></addr-line>'
    '<country country="BR">Brazil</country></aff>'
)
AUTHOR = (
    '<contrib-group><contrib contrib-type="author">'
    '<xref ref-type="aff" rid="a1"/></contrib></contrib-group>'
)


def bind_wayta(data):
    rebind(data)
    bind_modern(data)
    data["wayta_evidence"] = WaytaRequirementEvidence(
        contract_version="wayta-requirement-evidence-1.0",
        scope=data["expected_scope"],
        normative_sha256=NORMATIVE_SHA256,
        native_proof_sha256=NATIVE_PROOF_SHA256,
        vendor_sha256=VENDOR_FILES,
        service_report_sha256="c" * 64,
        observation=WaytaServiceObservation(
            contract_version="wayta-service-observation-1.0",
            endpoint=ENDPOINT,
            observed_at=data["now"],
            outcome="timeout",
            public_addresses=1,
            elapsed_seconds=8,
        ),
    )


@pytest.fixture
def data(sps_inputs):  # noqa: F811
    data = sps_inputs
    data["xml"] = data["xml"].replace(
        b"</article-meta>", (AUTHOR + AFF + "</article-meta>").encode()
    )
    data["trusted"] = data["trusted"].model_copy(update={"required_queries_complete": False})
    bind_wayta(data)
    return data


def test_qualified_wayta_is_auxiliary_without_waiving_any_error_or_query(data):
    result = assess_wayta_requirement(**data)
    assert result.requirement == "advisory_for_qualified_profile"
    assert result.affiliation_count == result.author_count == 1
    assert result.base.unresolved_counts == dict(
        blocking_errors=1, fatal_errors=1, errors=1, warnings=1
    )
    assert "required-queries-incomplete" in result.base.reasons
    assert "doctype-jats-decision-pending" in result.base.reasons
    assert not result.article_query_completed and not result.institution_identity_verified
    assert not result.release_approved and not result.homologation_ready
    assert result.mandatory_affiliation_validation_required


@pytest.mark.parametrize(
    "old,new",
    [
        ('<country country="BR">Brazil</country>', ""),
        ('country="BR"', 'country="ZZ"'),
        ('country="BR"', 'country="JP"'),
        ('country="BR"', 'country="br"'),
        ('<country country="BR">Brazil</country>', '<country country="US">United States</country>'),
        (">Brazil</country>", "></country>"),
        ('<country country="BR">Brazil</country>', '<country country="BR">Brazil</country>' * 2),
        ('<institution content-type="orgname">University</institution>', ""),
        ('<institution content-type="original">University, City, Brazil</institution>', ""),
        ('content-type="orgname"', 'content-type="normalized"'),
        (">University</institution>", "></institution>"),
        (">University</institution>", "><bold>University</bold></institution>"),
        ('content-type="orgname"', 'content-type="orgdiv3"'),
        (
            '<institution content-type="orgname">University</institution>',
            '<institution content-type="orgname">University</institution>' * 2,
        ),
        ('rid="a1"', 'rid="missing"'),
        ('rid="a1"', 'rid="a1 a2"'),
        ('ref-type="aff"', 'ref-type="other"'),
        ('<xref ref-type="aff" rid="a1"/>', ""),
        ('<xref ref-type="aff" rid="a1"/>', '<xref ref-type="aff" rid="a1"/>' * 2),
        ('id="a1"', 'id=""'),
        (' id="a1"', ""),
        ("<volume>", '<volume id="a1">'),
        (AFF, AFF * 2),
        (AFF, AFF + AFF.replace('id="a1"', 'id="a2"')),
        (AFF, ""),
        (AUTHOR, ""),
        ("</article>", "<sub-article/></article>"),
        ("</article>", "<response/></article>"),
        ("</article>", AFF.replace('id="a1"', 'id="a2"') + "</article>"),
        ('<named-content content-type="city">City</named-content>', ""),
        ('<named-content content-type="state">State</named-content>', ""),
    ],
)
def test_missing_invalid_or_unqualified_affiliations_never_get_advisory_policy(data, old, new):
    data["xml"] = data["xml"].replace(old.encode(), new.encode())
    bind_wayta(data)
    result = assess_wayta_requirement(**data)
    assert result.requirement == "undetermined"
    assert not result.homologation_ready and not result.article_query_completed


@pytest.mark.parametrize(
    "field", ["normative_sha256", "native_proof_sha256", "vendor_sha256", "scope"]
)
def test_wrong_authority_vendor_or_scope_rejected(data, field):
    evidence = data["wayta_evidence"]
    value = {} if field in {"vendor_sha256", "scope"} else "f" * 64
    data["wayta_evidence"] = evidence.model_copy(update={field: value})
    with pytest.raises(ValueError):
        assess_wayta_requirement(**data)


@pytest.mark.parametrize("delta", [timedelta(hours=-25), timedelta(seconds=1)])
def test_stale_or_future_observation_rejected(data, delta):
    evidence = data["wayta_evidence"]
    observation = evidence.observation.model_copy(update={"observed_at": data["now"] + delta})
    data["wayta_evidence"] = evidence.model_copy(update={"observation": observation})
    with pytest.raises(ValueError, match="stale_or_future"):
        assess_wayta_requirement(**data)


@pytest.mark.parametrize(
    "update",
    [
        {"endpoint": "http://wayta.scielo.org/api/v1/institution"},
        {"endpoint": "https://127.0.0.1/api/v1/institution"},
        {"article_query_performed": True},
        {"semantic_result_validated": True},
        {"http_status": 200},
        {"response_sha256": "a" * 64},
        {"observed_at": "2026-10-19T00:00:00"},
        {"outcome": "http_response"},
        {"outcome": "success"},
        {"public_addresses": 0},
        {"public_addresses": -1},
        {"public_addresses": True},
        {"elapsed_seconds": float("inf")},
        {"elapsed_seconds": 61},
    ],
)
def test_incoherent_or_forged_service_observation_rejected(data, update):
    evidence = data["wayta_evidence"]
    observation = evidence.observation.model_copy(update=update)
    data["wayta_evidence"] = evidence.model_copy(update={"observation": observation})
    with pytest.raises(ValueError):
        assess_wayta_requirement(**data)


@pytest.mark.parametrize("status", [200, 302, 404, 429, 500])
def test_even_http_200_does_not_prove_article_query_or_institution_identity(data, status):
    evidence = data["wayta_evidence"]
    observation = evidence.observation.model_copy(
        update={
            "outcome": "http_response",
            "http_status": status,
            "response_sha256": "d" * 64,
        }
    )
    data["wayta_evidence"] = evidence.model_copy(update={"observation": observation})
    result = assess_wayta_requirement(**data)
    assert result.requirement == "advisory_for_qualified_profile"
    assert result.service_observation.http_status == status
    assert not result.article_query_completed and not result.institution_identity_verified


@pytest.mark.parametrize("field", ["xml", "package", "report", "crossref"])
def test_exact_candidate_and_native_inputs_still_required(data, field):
    data[field] += b"tampered"
    with pytest.raises(ValueError):
        assess_wayta_requirement(**data)


def test_independent_validation_cannot_be_omitted(data):
    evidence = data["sps_evidence"]
    data["sps_evidence"] = evidence.model_copy(update={"runs": ()})
    with pytest.raises(ValueError, match="independent_validation_missing"):
        assess_wayta_requirement(**data)
