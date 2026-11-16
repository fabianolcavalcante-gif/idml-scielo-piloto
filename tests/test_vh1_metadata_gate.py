import copy
import json

import pytest

from ops.gate_vh1_metadata import REPORTS, ROOT, evaluate
from ops.qualify_vh1_metadata import sha, verify_delta


@pytest.mark.parametrize("change", ["none", "swap", "authenticated", "name", "body", "partial"])
def test_orcid_delta_rejects_misattribution_and_unrelated_edits(change):
    names = (
        ("Daniel Jadyr Leite", "Costa", "0000-0003-1136-7986"),
        ("Giovanna", "Collyer", "0000-0002-3963-5973"),
        ("Wilson Tadeu Lopes da", "Silva", "0000-0002-0839-9947"),
    )
    before = (
        "<article><front><article-meta><contrib-group>"
        + "".join(
            f'<contrib contrib-type="author"><name><surname>{family}</surname>'
            f"<given-names>{given}</given-names></name></contrib>"
            for given, family, _ in names
        )
        + "</contrib-group></article-meta></front><body><p>Science</p></body></article>"
    )
    after = before
    for _, family, identifier in names:
        target = f'<contrib contrib-type="author"><name><surname>{family}</surname>'
        after = after.replace(
            target,
            '<contrib contrib-type="author">'
            f'<contrib-id contrib-id-type="orcid" authenticated="false">'
            f"{identifier}</contrib-id><name><surname>{family}</surname>",
        )
    if change == "swap":
        after = after.replace(names[0][2], names[1][2])
    elif change == "authenticated":
        after = after.replace('authenticated="false"', 'authenticated="true"')
    elif change == "name":
        after = after.replace("Giovanna", "G.")
    elif change == "body":
        after = after.replace("Science", "Changed")
    elif change == "partial":
        after = after.replace(names[0][2], "")
    if change == "none":
        assert (
            verify_delta(before.encode(), after.encode(), articlemeta_orcids=True)[
                "verified_author_orcids"
            ]
            == 3
        )
    else:
        with pytest.raises(ValueError, match="unexpected_metadata_delta"):
            verify_delta(before.encode(), after.encode(), articlemeta_orcids=True)


def read(name="vh1-metadata-linux-v7.json"):
    return json.loads((REPORTS / name).read_bytes())


def check(report):
    return evaluate(
        report,
        read("vh1-editorial-linux-v1.json"),
        (ROOT / "config/validator-registry-vh1-scoped.json").read_bytes(),
        lambda path: (ROOT / path).read_bytes(),
        read("vh1-metadata-linux-v6.json"),
    )


def test_qualified_correction_passes_but_not_whole_xml():
    result = check(read())
    assert result["passed"] is True, result
    assert result["formal_xml_approved"] is False


def test_rejected_partial_date_experiment_is_not_current_qualification():
    assert check(read("vh1-metadata-linux-v1.json"))["passed"] is False


def test_previous_metadata_build_is_not_current_qualification():
    assert check(read("vh1-metadata-linux-v2.json"))["passed"] is False
    assert check(read("vh1-metadata-linux-v3.json"))["passed"] is False
    assert check(read("vh1-metadata-linux-v4.json"))["passed"] is False
    assert check(read("vh1-metadata-linux-v5.json"))["passed"] is False
    assert check(read("vh1-metadata-linux-v6.json"))["passed"] is False


@pytest.mark.parametrize(
    "change", ["none", "agency", "award", "statement", "body", "extra", "baseline"]
)
def test_verified_funding_delta_cannot_copy_awards_or_change_disclosure(monkeypatch, change):
    import ops.qualify_vh1_metadata as qualifier

    # Public tests use synthetic text; the private lab checks the actual declaration/hash.
    statement = b"Source financing declaration."
    monkeypatch.setattr(
        qualifier,
        "sha",
        lambda raw: (
            "2193d3d76c7f2f9155be71a559c4c5f927022f3a4ebc2ff78833590a5dcaa72e"
            if raw == statement
            else sha(raw)
        ),
    )
    before = (
        b"<article><front><article-meta><funding-group><funding-statement>"
        + statement
        + b"</funding-statement></funding-group></article-meta></front>"
        b"<body><p>Science</p></body></article>"
    )
    award = (
        b"<award-group><funding-source>Brazilian Agricultural Research Corporation</funding-source>"
        b"<award-id>21.17.02.001.05.00</award-id></award-group>"
    )
    after = before.replace(b"<funding-statement>", award + b"<funding-statement>")
    if change == "agency":
        after = after.replace(
            b"Brazilian Agricultural Research Corporation", b"Brazilian Development Bank"
        )
    elif change == "award":
        after = after.replace(b"21.17.02.001.05.00", b"16.2.0225.1")
    elif change == "statement":
        after = after.replace(statement, b"Changed declaration")
    elif change == "body":
        after = after.replace(b"Science", b"Changed science")
    elif change == "extra":
        after = after.replace(b"</award-group>", b"<award-id>123</award-id></award-group>")
    elif change == "baseline":
        before = before.replace(statement, b"Other declaration")
    if change == "none":
        assert verify_delta(before, after, verified_funding=True)["verified_funding_pairs"] == 1
    else:
        with pytest.raises(ValueError):
            verify_delta(before, after, verified_funding=True)


@pytest.mark.parametrize("change", ["source", "catalog", "review", "hash", "preserved"])
def test_verified_funding_gate_requires_evidence_and_human_review(change):
    report = read()
    metadata = report["qualification"]["cases"]["esa-e20240086"]
    funding = metadata["verified_funding"]
    if change == "source":
        funding["source"]["url"] = "https://example.com/unrelated"
    elif change == "catalog":
        metadata["files"]["verified_funding_catalog.json"] = "0" * 64
    elif change == "review":
        funding["human_review_required"] = False
    elif change == "hash":
        funding["source"]["sha256"] = "0" * 64
    else:
        funding["other_funders_preserved_in_statement"] = False
    assert check(report)["passed"] is False


@pytest.mark.parametrize("change", ["none", "region", "city", "science", "partial", "baseline"])
def test_location_delta_preserves_address_and_rejects_region_as_state(change):
    before = (
        b'<article><front><article-meta><aff id="a1">'
        b'<institution content-type="orgname">University of Tokyo</institution>'
        b'<addr-line><named-content content-type="city">Tokyo</named-content></addr-line>'
        b'<country country="JP">Japan</country></aff></article-meta></front>'
        b"<body><p>Science</p></body></article>"
    )
    after = before.replace(
        b"</addr-line>", b'<named-content content-type="state">Tokyo</named-content></addr-line>'
    )
    if change == "region":
        after = after.replace(b'"state">Tokyo', b'"state">Kanto')
    elif change == "city":
        after = after.replace(b'"city">Tokyo', b'"city">Meguro-ku')
    elif change == "science":
        after = after.replace(b"Science", b"Changed")
    elif change == "partial":
        after = before
    elif change == "baseline":
        before = before.replace(b'"city">Tokyo', b'"city">Other')
    if change == "none":
        assert (
            verify_delta(before, after, institution_locations=True)["verified_institution_states"]
            == 1
        )
    else:
        with pytest.raises(ValueError):
            verify_delta(before, after, institution_locations=True)


@pytest.mark.parametrize("change", ["source", "catalog", "review", "evidence", "delta"])
def test_location_gate_requires_curated_sources_and_complete_delta(change):
    report = read()
    metadata = report["qualification"]["cases"]["esa-e20240086"]
    locations = metadata["institution_locations"]
    if change == "source":
        locations["sources"]["tokyo_department"]["url"] = "https://example.com/contact"
    elif change == "catalog":
        metadata["files"]["institution_location_catalog.json"] = "0" * 64
    elif change == "review":
        locations["human_review_required"] = False
    elif change == "evidence":
        locations["evidence_sha256"] = "0" * 64
    else:
        metadata["delta"]["verified_institution_states"] = 0
    assert check(report)["passed"] is False


@pytest.mark.parametrize(
    "change", ["none", "publication", "history", "science", "author", "invented_revision"]
)
def test_articlemeta_delta_allows_only_the_three_independently_confirmed_dates(change):
    before = (
        b'<article><front><article-meta><pub-date date-type="pub"><year>2025</year>'
        b"</pub-date><contrib-group><contrib><name>Author</name></contrib></contrib-group>"
        b'<history><date date-type="received" iso-8601-date="2024-06-09">'
        b"<day>09</day><month>06</month><year>2024</year></date>"
        b'<date date-type="accepted" iso-8601-date="2025-09-03">'
        b"<day>03</day><month>09</month><year>2025</year></date></history>"
        b"</article-meta></front><body><p>Science</p></body></article>"
    )
    after = (
        b'<article><front><article-meta><pub-date date-type="pub" iso-8601-date="2025-07-07">'
        b"<day>07</day><month>07</month><year>2025</year></pub-date>"
        b"<contrib-group><contrib><name>Author</name></contrib></contrib-group>"
        b'<history><date date-type="received" iso-8601-date="2024-09-06">'
        b"<day>06</day><month>09</month><year>2024</year></date>"
        b'<date date-type="accepted" iso-8601-date="2025-03-09">'
        b"<day>09</day><month>03</month><year>2025</year></date>"
        b'<date date-type="pub" iso-8601-date="2025-07-07">'
        b"<day>07</day><month>07</month><year>2025</year></date></history>"
        b"</article-meta></front><body><p>Science</p></body></article>"
    )
    if change == "publication":
        after = after.replace(b"2025-07-07", b"2025-07-02")
    elif change == "history":
        after = after.replace(b"2024-09-06", b"2024-06-09")
    elif change == "science":
        after = after.replace(b"Science", b"Changed")
    elif change == "author":
        after = after.replace(b"Author", b"Someone else")
    elif change == "invented_revision":
        after = after.replace(b"</history>", b'<date date-type="rev-recd"/></history>')
    if change == "none":
        assert verify_delta(before, after, articlemeta_dates=True)["articlemeta_date_fields"] == 3
    else:
        with pytest.raises(ValueError, match="unexpected_metadata_delta"):
            verify_delta(before, after, articlemeta_dates=True)


@pytest.mark.parametrize("change", ["none", "statement", "body", "grant", "wrong_binding"])
def test_deferring_funding_never_changes_statement_body_or_invents_award(change):
    statement = "Alpha, Beta, Project A, #21.02.00."
    before = (
        "<article><front><article-meta><funding-group>"
        "<award-group><funding-source>Alpha</funding-source></award-group>"
        f"<funding-statement>{statement}</funding-statement>"
        "</funding-group></article-meta></front><body><p>Science</p></body></article>"
    ).encode()
    after = before.replace(
        b"<award-group><funding-source>Alpha</funding-source></award-group>", b""
    )
    binding = sha(statement.encode())
    if change == "statement":
        after = after.replace(b"Alpha, Beta", b"Alpha")
    elif change == "body":
        after = after.replace(b"Science", b"Changed")
    elif change == "grant":
        after = after.replace(
            b"<funding-statement>", b"<award-id>21.02.00</award-id><funding-statement>"
        )
    elif change == "wrong_binding":
        binding = "0" * 64
    if change == "none":
        assert (
            verify_delta(before, after, deferred_statement_sha256=binding)[
                "funding_structure_deferred"
            ]
            == 1
        )
    else:
        with pytest.raises(ValueError):
            verify_delta(before, after, deferred_statement_sha256=binding)


@pytest.mark.parametrize(
    "change",
    [
        "source",
        "image",
        "candidate",
        "binding",
        "missing_doi",
        "new_finding",
        "missing_tool",
        "duplicate_case",
        "invented_date",
        "approval",
        "funding_status_mismatch",
        "wrong_date_authority",
        "wrong_date_catalog",
        "date_review_hidden",
        "date_source_mismatch",
        "orcid_snapshot",
        "orcid_unavailable",
        "orcid_authentication",
        "orcid_false_positive",
    ],
)
def test_metadata_gate_rejects_stale_tampered_and_regressive_evidence(change):
    report = read()
    row = report["cases"][0]["validators"][0]
    if change == "source":
        report["qualification"]["source_sha256"] = {}
    elif change == "image":
        row["image_id"] = "sha256:" + "0" * 64
    elif change == "candidate":
        row["candidate_sha256"] = "0" * 64
    elif change == "binding":
        row["authority_evidence"]["binding"]["grant_sha256"] = "0" * 64
    elif change == "missing_doi":
        row["authority_evidence"]["checks"]["doi"] = []
    elif change == "new_finding":
        row["findings"][0]["code"] = "unexpected-new-rule"
    elif change == "missing_tool":
        report["cases"][0]["validators"].pop()
    elif change == "duplicate_case":
        report["cases"][1] = copy.deepcopy(report["cases"][0])
    elif change == "invented_date":
        report["qualification"]["cases"]["esa-e20240086"]["delta"]["publication_year_added"] = 1
    elif change == "funding_status_mismatch":
        report["qualification"]["cases"]["esa-e20240086"]["funding_structure_review_required"] = (
            True
        )
    elif change == "wrong_date_authority":
        report["qualification"]["cases"]["esa-e20240086"]["articlemeta_dates"][
            "snapshot_sha256"
        ] = "0" * 64
    elif change == "wrong_date_catalog":
        report["qualification"]["cases"]["esa-e20240086"]["files"][
            "articlemeta_date_catalog.json"
        ] = "0" * 64
    elif change == "date_review_hidden":
        report["qualification"]["cases"]["esa-e20240086"]["articlemeta_dates"][
            "human_review_required"
        ] = False
    elif change == "date_source_mismatch":
        report["qualification"]["cases"]["esa-e20240086"]["articlemeta_dates"][
            "source_idml_sha256"
        ] = "0" * 64
    elif change == "orcid_snapshot":
        report["qualification"]["cases"]["esa-e20240086"]["articlemeta_orcids"][
            "evidence_sha256"
        ] = "0" * 64
    elif change == "orcid_unavailable":
        report["qualification"]["cases"]["esa-e20240086"]["articlemeta_orcids"]["persons"][
            "0000-0003-1136-7986"
        ]["status"] = "unavailable"
    elif change == "orcid_authentication":
        report["qualification"]["cases"]["esa-e20240086"]["articlemeta_orcids"][
            "authenticated_ownership_claimed"
        ] = True
    elif change == "orcid_false_positive":
        row["authority_evidence"]["checks"]["orcid"] = []
    else:
        report["formal_xml_approved"] = True
    assert check(report)["passed"] is False
