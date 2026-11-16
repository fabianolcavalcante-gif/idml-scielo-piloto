"""Require an explicit native DOI result; absence of findings is not approval."""

from contextlib import contextmanager


@contextmanager
def observe_registered_doi(module):
    """Observe native return values before SPS drops OK rows; never change results."""
    original = module.check_doi_is_registered
    outcomes = []

    def observed(*args, **kwargs):
        result = original(*args, **kwargs)
        outcomes.append(isinstance(result, dict) and result.get("valid") is True)
        return result

    module.check_doi_is_registered = observed
    try:
        yield outcomes
    finally:
        module.check_doi_is_registered = original


def registered_doi_evidence(raw):
    rows = raw.get("rows", []) if isinstance(raw, dict) else raw
    results = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        metadata = row.get("data", {}) if "status" in row else row
        if not isinstance(metadata, dict) or metadata.get("title") != "registered DOI":
            continue
        status = row.get("status", row.get("response", ""))
        results.append(str(status).casefold() == "ok")
    return {"native_doi_rows": len(results), "native_doi_passed": bool(results) and all(results)}
