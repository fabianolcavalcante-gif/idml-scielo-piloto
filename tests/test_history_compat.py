import copy
import json
from types import SimpleNamespace

import pytest
from lxml import etree

from idml_foundation.release.validation_engine import ValidationEngine
from ops.history_compat import (
    EXPECTED_RULES,
    REVISION_TYPES,
    effective_parameters,
    history_parameters,
    verify_native_config,
)


def tree(profile="sps-1.10", version="1.3"):
    return etree.fromstring(
        f'<article specific-use="{profile}" dtd-version="{version}"><front/></article>'.encode()
    )


def parameters():
    return {"history_dates_rules": copy.deepcopy(EXPECTED_RULES), "unrelated": {"level": "ERROR"}}


def native_stub(xml, params):
    for entry in params["history_dates_rules"]["date_list"]:
        if entry["required"]:
            yield {
                "title": "required date: " + entry["type"],
                "item": "history",
                "validation_type": "exist",
                "response": "CRITICAL",
                "message": "Required date missing",
            }
    yield {"title": "year presence for rev-recd", "response": "CRITICAL", "message": "missing"}


def test_only_two_flags_change_and_input_is_preserved():
    params = parameters()
    before = copy.deepcopy(params)
    adjusted = effective_parameters(params)
    expected = copy.deepcopy(params)
    for row in expected["history_dates_rules"]["date_list"]:
        if row["type"] in REVISION_TYPES:
            row["required"] = False
    assert adjusted == expected
    assert params == before
    adjusted["unrelated"]["level"] = "WARNING"
    assert params == before


@pytest.mark.parametrize(
    "change", ["missing", "severity", "pub", "accepted", "received", "extra", "int", "duplicate"]
)
def test_unqualified_or_editorial_overrides_fail_closed(change):
    params = parameters()
    if change == "missing":
        del params["history_dates_rules"]
    elif change == "severity":
        params["history_dates_rules"]["error_level"] = "WARNING"
    elif change == "extra":
        params["history_dates_rules"]["new_option"] = True
    elif change == "duplicate":
        params["history_dates_rules"]["date_list"].append({"type": "rev-recd", "required": True})
    else:
        key = "rev-request" if change == "int" else change
        for row in params["history_dates_rules"]["date_list"]:
            if row["type"] == key:
                row["required"] = 1 if change == "int" else False
    with pytest.raises(ValueError, match="unqualified_parameters"):
        effective_parameters(params)


@pytest.mark.parametrize("profile,version", [("sps-1.9", "1.3"), ("sps-1.10", "1.2"), ("", "1.3")])
def test_wrong_profile_never_uses_compatibility(profile, version):
    module = SimpleNamespace(validate_history=native_stub)
    with history_parameters(module), pytest.raises(ValueError, match="unqualified_profile"):
        list(module.validate_history(tree(profile, version), parameters()))
    assert module.validate_history is native_stub


@pytest.mark.parametrize("element_tree", [False, True])
def test_native_dates_severity_xml_and_parameters_preserved(element_tree):
    module = SimpleNamespace(validate_history=native_stub)
    xml = tree()
    before = etree.tostring(xml)
    params = parameters()
    with history_parameters(module) as proof:
        result = list(module.validate_history(xml.getroottree() if element_tree else xml, params))
    assert module.validate_history is native_stub
    assert etree.tostring(xml) == before
    assert params == parameters()
    assert [r["title"] for r in result] == [
        "required date: received",
        "required date: accepted",
        "required date: pub",
        "year presence for rev-recd",
    ]
    assert all(r["response"] == "CRITICAL" for r in result)
    assert proof["absence_is_not_proof_of_no_revision"] is True
    assert len(proof["invocations"][0]["default_failures"]) == 6
    assert len(proof["invocations"][0]["effective_failures"]) == 4
    # Diagnostic raw pass must not be double-counted by application normalization.
    run = ValidationEngine().external_run(
        before,
        {"findings": result, "history_policy_evidence": proof},
        name="packtools",
        version="test",
        tool_sha256="a" * 64,
    )
    assert len(run.issues) == 4


@pytest.mark.parametrize("failure", ["native", "delta", "caller"])
def test_failure_restores_hook_and_never_returns_partial_pass(failure):
    calls = []

    def native(xml, params):
        calls.append(params)
        if failure == "native":
            raise RuntimeError("failed")
        rows = list(native_stub(xml, params))
        if failure == "delta" and len(calls) == 2:
            rows[-1]["response"] = "OK"
        yield from rows

    module = SimpleNamespace(validate_history=native)
    with pytest.raises((ValueError, RuntimeError)), history_parameters(module):
        list(module.validate_history(tree(), parameters()))
        if failure == "caller":
            raise RuntimeError("caller failed")
    assert module.validate_history is native


def test_nested_installation_denied():
    module = SimpleNamespace(validate_history=native_stub)
    with (
        history_parameters(module),
        pytest.raises(ValueError, match="already_installed"),
        history_parameters(module),
    ):
        pass
    assert module.validate_history is native_stub


@pytest.mark.parametrize(
    "raw", [b"{}", b"not json", json.dumps({"history_dates_rules": EXPECTED_RULES}).encode()]
)
def test_native_file_hash_is_not_replaceable_by_same_values(raw):
    with pytest.raises(ValueError, match="configuration_changed"):
        verify_native_config(raw)
