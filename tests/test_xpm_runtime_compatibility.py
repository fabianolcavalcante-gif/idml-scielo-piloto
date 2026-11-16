"""Integrated diagnostics must preserve raw errors, scope and publication gates."""

import copy
import json
from datetime import timedelta
from io import BytesIO
from zipfile import ZipFile

import pytest

from idml_foundation.release.orcid_query_diagnostics import crossref_author_links
from idml_foundation.release.xpm_query_semantics import QueryEvidence
from idml_foundation.services.package_validation import assess_package
from idml_foundation.services.xpm_execution import assess_xpm_execution
from idml_foundation.services.xpm_query_targets import parse_candidate
from tests.test_package_formal_validation import completed
from tests.test_xpm_compatibility import row
from tests.test_xpm_execution import execution
from tests.test_xpm_query_semantics import ORCID, XML, assess, sample, sha

OTHER_ORCID = "0000-0001-5109-3700"


def replace_body(evidence, index, body):
    payload = json.dumps(body)
    evidence["receipts"][index].update(payload=payload, response_sha256=sha(payload.encode()))


@pytest.mark.parametrize("prefix", ["", "http://orcid.org/", "https://orcid.org/"])
@pytest.mark.parametrize("authenticated", [False, True, "true"])
def test_exact_deposit_link_never_authenticates_or_overrides_public_nonmatch(prefix, authenticated):
    scope, _, now, evidence = sample()
    body = json.loads(evidence["receipts"][0]["payload"])
    body["message"]["author"][0].update(
        ORCID=prefix + ORCID, **{"authenticated-orcid": authenticated}
    )
    replace_body(evidence, 0, body)
    person = json.loads(evidence["receipts"][1]["payload"])
    person["name"].pop("family-name")
    replace_body(evidence, 1, person)
    result = assess(scope, now, evidence)
    assert result["checks"][1]["status"] == "conflict"
    assert result["checks"][1]["public_name_check"] == "public-name-incomplete"
    assert result["crossref_author_links"]["checks"][0]["status"] == "matched"
    assert not result["crossref_author_links"]["authenticated_ownership"]
    assert not result["selected_checks_matched"] and not result["authenticated_orcid_ownership"]
    assert ORCID not in json.dumps(result) and "Ana" not in json.dumps(result)


@pytest.mark.parametrize(
    "value,state",
    [
        (None, "not-deposited"),
        ("", "not-deposited"),
        (False, "conflict"),
        ({"value": ORCID}, "conflict"),
        (OTHER_ORCID, "conflict"),
        ("https://evil.test/" + ORCID, "conflict"),
        (ORCID[:-1] + "0", "conflict"),
    ],
)
def test_deposit_links_fail_closed_without_promoting_missing_data(value, state):
    scope, _, now, evidence = sample()
    body = json.loads(evidence["receipts"][0]["payload"])
    body["message"]["author"][0]["ORCID"] = value
    replace_body(evidence, 0, body)
    result = assess(scope, now, evidence)
    assert result["crossref_author_links"]["checks"][0]["status"] == state
    assert result["selected_checks_matched"] == (state == "not-deposited")


@pytest.mark.parametrize("field", ["DOI", "title", "author"])
def test_bad_crossref_binding_cannot_corroborate_orcid(field):
    scope, _, now, evidence = sample()
    body = json.loads(evidence["receipts"][0]["payload"])
    body["message"]["author"][0]["ORCID"] = ORCID
    body["message"][field] = "wrong"
    replace_body(evidence, 0, body)
    result = assess(scope, now, evidence)
    assert result["crossref_author_links"]["status"] == "unavailable"
    assert not result["crossref_author_links"]["checks"]


@pytest.mark.parametrize(
    "change,diagnostic",
    [
        ("family", "public-name-not-exact"),
        ("visibility", "public-name-unavailable"),
        ("path", "public-record-invalid"),
        ("credit", "exact-public-name-match"),
    ],
)
def test_public_name_diagnostics(change, diagnostic):
    scope, _, now, evidence = sample()
    person = json.loads(evidence["receipts"][1]["payload"])
    if change == "family":
        person["name"]["family-name"]["value"] = "Different"
    elif change == "visibility":
        person["name"]["visibility"] = "private"
    elif change == "path":
        person["path"] = "/wrong/person"
    else:
        person["name"]["family-name"] = None
        person["name"]["credit-name"] = {"value": "Ana Silva"}
    replace_body(evidence, 1, person)
    assert assess(scope, now, evidence)["checks"][1]["public_name_check"] == diagnostic


def integrated():
    scope, _, now, evidence = sample()
    xml = XML.replace(b"<article>", b'<article specific-use="sps-1.10" dtd-version="1.3">')
    stream = BytesIO()
    with ZipFile(stream, "w") as archive:
        archive.writestr("article.xml", xml)
    package = stream.getvalue()
    scope.update(xml_sha256=sha(xml), package_sha256=sha(package))
    report = (
        "<html><body><!-- 4.0.096 22/04/2019 -->"
        "Total of blocking errors: 1 Total of fatal errors: 1 "
        "Total of errors: 3 Total of warnings: 1 <table>"
        + row("Journal", 1).replace("10.1590/synthetic", "10.1234/test")
        + row("Title", 2).replace("10.1590/synthetic", "10.1234/test")
        + '<tr class="error"><td>Real remaining error</td></tr></table></body></html>'
    ).encode()
    evidence.update(scope=scope, report_sha256=sha(report))
    response = execution(package, scope)
    response = response.model_copy(
        update={
            "report": report,
            "attestation": response.attestation.model_copy(update={"report_sha256": sha(report)}),
        }
    )
    return xml, package, scope, evidence, response, now


def run_integrated(data):
    xml, package, scope, evidence, response, _ = data
    response = response.model_copy(
        update={"query_evidence": QueryEvidence.model_validate(evidence)}
    )
    return assess_xpm_execution(
        xml=xml, package=package, expected_scope=scope, executor=lambda *_: response
    )


def test_doi_rules_composed_with_current_execution_preserve_raw_and_scopes():
    result = run_integrated(integrated())
    derived = result["compatibility"]
    assert result["counts"] == dict(blocking_errors=1, fatal_errors=1, errors=3, warnings=1)
    assert derived["unresolved_counts"] == dict(
        blocking_errors=1, fatal_errors=1, errors=1, warnings=1
    )
    assert len(derived["exceptions"]) == 2
    assert not result["raw_passed"] and not result["required_queries_complete"]
    assert not derived["homologation_ready"] and not derived["release_approved"]
    assert derived["pending_rule_families"] == ["sps-date", "doctype-jats", "wayta"]
    serialized = json.dumps(result)
    assert "synthetic-only" not in serialized and "<html>" not in serialized


@pytest.mark.parametrize(
    "change", ["hash", "scope", "report", "expired", "future", "origin", "title", "unavailable"]
)
def test_invalid_query_cannot_enable_runtime_compatibility(change):
    data = integrated()
    evidence = data[3]
    receipt = evidence["receipts"][0]
    if change == "hash":
        receipt["payload"] += " "
    elif change == "scope":
        evidence["scope"] = {**evidence["scope"], "xml_sha256": "a" * 64}
    elif change == "report":
        evidence["report_sha256"] = "b" * 64
    elif change in {"expired", "future"}:
        receipt["retrieved_at"] = (
            data[5] + timedelta(hours=-25 if change == "expired" else 25)
        ).isoformat()
    elif change == "origin":
        receipt["url"] = "https://evil.test/"
    elif change == "title":
        body = json.loads(receipt["payload"])
        body["message"]["title"] = ["Other title"]
        replace_body(evidence, 0, body)
    else:
        receipt.update(status="unavailable", payload=None, response_sha256=None)
    result = run_integrated(data)
    assert result["counts"]["errors"] == 3
    assert result.get("compatibility", {}).get("status") != "assessed"


def test_deposited_identifier_conflict_blocks_even_clean_xpm_and_matching_public_name():
    scope, package, _, evidence = sample()
    body = json.loads(evidence["receipts"][0]["payload"])
    body["message"]["author"][0]["ORCID"] = OTHER_ORCID
    replace_body(evidence, 0, body)
    response = execution(package, scope)
    evidence["report_sha256"] = sha(response.report)
    response = response.model_copy(
        update={"query_evidence": QueryEvidence.model_validate(evidence)}
    )
    result = assess_package(
        xml=XML,
        package=package,
        expected_scope=scope,
        executor=completed,
        xpm_executor=lambda *_: response,
    )
    assert result["xpm"]["raw_passed"]
    assert result["state"] == "blocked"
    assert "xpm-authority-response-conflict" in result["reasons"]
    assert not result["ready_for_scielo"]


def test_receipt_order_does_not_change_corroboration():
    scope, _, now, evidence = sample()
    result = assess(scope, now, evidence)
    swapped = copy.deepcopy(evidence)
    swapped["receipts"].reverse()
    assert assess(scope, now, swapped)["crossref_author_links"] == result["crossref_author_links"]


def test_duplicate_names_do_not_allow_positional_identity_assumptions():
    root = parse_candidate(XML)
    group = root.find("front/article-meta/contrib-group")
    second = copy.deepcopy(group[0])
    second.find("contrib-id").text = OTHER_ORCID
    group.append(second)
    links = crossref_author_links(root, {"author": [{"ORCID": ORCID}, {"ORCID": OTHER_ORCID}]})
    assert len(links) == 2
    assert all(c["status"] == "unavailable" for c in links)


def test_orcid_swap_is_not_accepted_as_set_membership():
    root = parse_candidate(XML)
    group = root.find("front/article-meta/contrib-group")
    second = copy.deepcopy(group[0])
    second.find("name/given-names").text = "Beatriz"
    second.find("contrib-id").text = OTHER_ORCID
    group.append(second)
    links = crossref_author_links(root, {"author": [{"ORCID": OTHER_ORCID}, {"ORCID": ORCID}]})
    assert all(c["status"] == "conflict" for c in links)


def test_editor_orcid_cannot_inherit_author_deposit_link():
    root = parse_candidate(XML)
    root.find("front/article-meta/contrib-group/contrib").set("contrib-type", "editor")
    assert crossref_author_links(root, {"author": []}) == []


@pytest.mark.parametrize("change", ["profile", "tool", "image", "report_hash"])
def test_runtime_compatibility_never_bypasses_existing_execution_pins(change):
    data = integrated()
    xml, package, scope, evidence, response, now = data
    if change == "profile":
        scope["journal_profile_id"] = "other-journal-1.0"
    elif change == "image":
        response = response.model_copy(update={"image": "sha256:" + "f" * 64})
    else:
        key = "tool_sha256" if change == "tool" else "report_sha256"
        response = response.model_copy(
            update={"attestation": response.attestation.model_copy(update={key: "f" * 64})}
        )
    result = run_integrated((xml, package, scope, evidence, response, now))
    assert result.get("compatibility", {}).get("status") != "assessed"
