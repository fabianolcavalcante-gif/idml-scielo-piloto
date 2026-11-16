from types import SimpleNamespace

import pytest

from ops.doi_validation_evidence import observe_registered_doi, registered_doi_evidence


@pytest.mark.parametrize(
    "raw,count,passed",
    [
        ([], 0, False),
        ([{"title": "other", "response": "OK"}], 0, False),
        ([{"title": "registered DOI", "response": "OK"}], 1, True),
        ([{"title": "registered DOI", "response": "WARNING"}], 1, False),
        (
            [
                {"title": "registered DOI", "response": "OK"},
                {"title": "registered DOI", "response": "ERROR"},
            ],
            2,
            False,
        ),
        ({"rows": [{"status": "OK", "data": {"title": "registered DOI"}}]}, 1, True),
        (
            {"rows": [{"status": "ERROR", "data": {"title": "registered DOI", "response": "OK"}}]},
            1,
            False,
        ),
        ({"rows": [{"status": "OK", "data": None}]}, 0, False),
    ],
)
def test_explicit_native_result_required(raw, count, passed):
    assert registered_doi_evidence(raw) == {"native_doi_rows": count, "native_doi_passed": passed}


def test_observer_preserves_native_result_identity_and_restores_on_failure():
    answer = {"valid": True}
    original = lambda _: answer  # noqa: E731
    module = SimpleNamespace(check_doi_is_registered=original)
    with pytest.raises(RuntimeError):
        with observe_registered_doi(module) as outcomes:
            assert module.check_doi_is_registered({}) is answer
            answer["valid"] = False
            assert module.check_doi_is_registered({}) is answer
            assert outcomes == [True, False]
            raise RuntimeError("synthetic failure")
    assert module.check_doi_is_registered is original
