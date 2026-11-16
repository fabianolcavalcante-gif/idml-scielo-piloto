"""Qualification-only enrichment of upstream contributor affiliation references.

No XML edits or finding suppression. The native rule receives resolved IDs only
when all affiliation targets are unique, local to this fulltext, and present.
"""

from collections import Counter


def resolved_affiliations(front, contributor):
    root = front.getroottree().getroot()
    counts = Counter(root.xpath("//@id"))
    local = {node.get("id") for node in front.xpath(".//aff[@id]")}
    targets = []
    for reference in contributor.get("contrib_xref", []):
        if reference.get("ref_type") != "aff":
            continue
        ids = (reference.get("rid") or "").split()
        if not ids or any(target not in local or counts[target] != 1 for target in ids):
            return []
        targets.extend(ids)
    return [{"id": target} for target in dict.fromkeys(targets)]


def compatible_text_contribs(original):
    class ResolvedTextContribs(original):
        @property
        def items(self):
            for item in self.main_contribs:
                yield {**item, "affs": resolved_affiliations(self.front, item)}
            for node in self.sub_articles:
                yield from type(self)(node).items

    return ResolvedTextContribs


def install():
    from packtools.sps.validation import article_contribs

    # Patch only the validation module's model binding; native rules stay intact.
    original = article_contribs.TextContribs
    if not getattr(original, "_idml_affiliation_compat", False):
        candidate = compatible_text_contribs(original)
        candidate._idml_affiliation_compat = True
        article_contribs.TextContribs = candidate
