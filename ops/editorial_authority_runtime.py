"""Scoped parameter injection; native checks/severities/results are preserved."""

import copy
from contextlib import contextmanager


def evidence_key(row):
    if not isinstance(row, dict):
        return None
    if row.get("title") == "registered issue":
        return "issue"
    if row.get("title") == "Registered ORCID" and row.get("validation_type") == "registered":
        return "orcid"
    if row.get("title") == "table of contents section" and row.get("sub_item") == "subject":
        return "section"
    return None


@contextmanager
def editorial_parameters(module, bound):
    """Process-local only: one candidate, synchronous isolated validator process."""
    names = (
        "validate_bibliographic_strip",
        "validate_article_toc_sections",
        "validate_article_contribs",
    )
    originals = {name: getattr(module, name) for name in names}
    evidence = {"issue": [], "section": [], "orcid": [], "orcid_reasons": []}

    def lookup(identifier, name):
        value = bound.lookup_orcid(identifier, name)
        evidence["orcid_reasons"].append(value["reason"])
        return value

    def wrap(original, name):
        def execute(tree, params):
            bound.check(tree=tree)
            updated = copy.deepcopy(params)
            if name == "validate_article_contribs":
                updated["is_orcid_registered"] = lookup
            else:
                journal = copy.deepcopy(updated.get("journal_data") or {})
                # No stale/self-derived expected lists when authority is unavailable.
                journal.pop("issues", None)
                journal.pop("toc_sections", None)
                journal.update(bound.journal())
                updated["journal_data"] = journal
                if name == "validate_article_toc_sections":
                    updated["article_toc_section_rules"].pop("toc_sections", None)
            for row in original(tree, updated):
                key = evidence_key(row)
                if key:
                    evidence[key].append(row.get("response") == "OK")
                yield row

        return execute

    try:
        for name, original in originals.items():
            setattr(module, name, wrap(original, name))
        yield evidence
    finally:
        for name, original in originals.items():
            setattr(module, name, original)
