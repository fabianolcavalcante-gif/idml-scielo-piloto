"""Native rule outputs with deterministic fake authorities; no network or corpus."""

import json
from types import SimpleNamespace

from external_verification import unavailable_dependency
from lxml import etree
from packtools.sps.validation.article_contribs import ContribValidation
from packtools.sps.validation.article_doi import ArticleDoiValidation
from packtools.sps.validation.article_toc_sections import SubjectValidation
from packtools.sps.validation.front_articlemeta_issue import IssueValidation


def main():
    rows = []
    tree = etree.fromstring(
        b"<article><front><article-meta><volume>30</volume></article-meta></front></article>"
    )

    def record(name, rule, expected):
        actual = unavailable_dependency(rule)
        nested = unavailable_dependency({"status": rule["response"], "data": rule})
        rows.append(
            {
                "case": name,
                "dependency": actual,
                "expected": expected,
                "passed": actual == expected and nested == expected,
            }
        )

    for status in ("unknown", "not-registered", "registered"):
        validator = ContribValidation(
            {"contrib_full_name": "Synthetic", "contrib_ids": {"orcid": "0000-0002-1825-0097"}},
            {"is_orcid_registered": lambda *args, status=status: {"status": status}},
        )
        record(
            "orcid-" + status,
            next(validator.validate_orcid_is_registered()),
            "orcid-registry" if status == "unknown" else None,
        )
    for available in (False, True):
        params = {"journal_data": {"issues": [{"volume": "99"}]}} if available else {}
        params["expected_issues_error_level"] = "ERROR"
        record(
            "issues-" + str(available),
            IssueValidation(tree, params).validate_expected_issues(),
            None if available else "journal-issues",
        )
        params = {"journal_data": {"toc_sections": {"en": ["Different"]}}} if available else {}
        subject = SubjectValidation({"parent_lang": "en", "subject": "Synthetic"}, params)
        # Fix the explicit native authority input without depending on constructor aliases.
        subject.expected_toc_sections = {"en": ["Different"]} if available else {}
        record(
            "sections-" + str(available),
            subject.validate_section(),
            None if available else "journal-sections",
        )
    for available in (False, True):
        validator = ArticleDoiValidation(tree, {})
        validator.doi = SimpleNamespace(data=[{"value": "10.1234/synthetic"}])
        payload = (
            {"valid": False, "registered": {"title": "different"}}
            if available
            else {"exception_type": "<class 'requests.exceptions.ConnectionError'>"}
        )
        rule = next(validator.validate_doi_registered(callable_get_data=lambda _, p=payload: p))
        record("doi-" + str(available), rule, None if available else "doi-registry")
    result = {"synthetic_only": True, "passed": all(row["passed"] for row in rows), "cases": rows}
    print(json.dumps(result))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
