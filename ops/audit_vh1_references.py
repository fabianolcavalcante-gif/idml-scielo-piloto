"""Post-build comparison and source adjudication; never rewrite gold or candidate."""

import json
import re
from datetime import UTC, datetime

from lxml import etree

from idml_foundation.domain.corpus import load_manifest
from idml_foundation.pipeline.idml_parser import IdmlParser
from idml_foundation.release.semantic_fidelity import XmlSemanticComparator
from ops.gate_phase7_7c06 import _single_artifact
from ops.gate_vh1_references import FINAL, REPORT, ROOT, sha
from ops.qualify_vh1_references import CASES, write

CANDIDATES = ROOT / "benchmarks/private/output/vh1-references-20261009T104259Z"
PATTERNS = (
    (r"Boyd,\s+Torrans\s+and\s+Tucker\s*\(2018\)", 13, [11, 10]),
    (r"Boyd,\s+Torrans\s+e\s+Tucker\s*\(2018\)", 13, [11]),
    (r"P\.\s+et\s+al\.\s*\(2018\)", 37, [None, None]),
    (r"P\.\s+et\s+al\.,\s*2018", 37, [None]),
)


def text_links(root):
    refs = {r.get("id"): i for i, r in enumerate(root.findall("back/ref-list/ref"), 1)}
    chunks, links = [], []
    offset = 0

    def append(value):
        nonlocal offset
        chunks.append(value or "")
        offset += len(value or "")

    def visit(node):
        start = offset
        append(node.text)
        for child in node:
            visit(child)
            append(child.tail)
        if node.tag == "xref" and node.get("ref-type") == "bibr":
            links.append((start, offset, refs[node.get("rid")]))

    visit(root.find("body"))
    return "".join(chunks), links


def adjudicate(gold, candidate, source_stories):
    old_text, old_links = text_links(gold)
    new_text, new_links = text_links(candidate)
    rows = []
    for pattern, target, expected_old in PATTERNS:
        source_matches = [m for text in source_stories for m in re.finditer(pattern, text)]
        old = list(re.finditer(pattern, old_text))
        new = list(re.finditer(pattern, new_text))
        if not len(source_matches) == len(old) == len(new) == len(expected_old):
            raise ValueError("citation_occurrences_not_source_bound")
        for i, (left, right) in enumerate(zip(old, new, strict=True)):
            before = [r for a, b, r in old_links if left.start() <= a < b <= left.end()]
            after = [r for a, b, r in new_links if right.start() <= a < b <= right.end()]
            if before != ([] if expected_old[i] is None else [expected_old[i]]) or after != [
                target
            ]:
                raise ValueError("citation_target_not_reviewed")
            reference = candidate.findall("back/ref-list/ref")[target - 1]
            citation = "".join(reference.find("mixed-citation").itertext())
            normalized = " ".join(citation.split())
            if not any(normalized in " ".join(s.split()) for s in source_stories):
                raise ValueError("reference_not_in_source")
            if reference.findtext("element-citation/year") != "2018":
                raise ValueError("citation_year_not_matching")
            if before and gold.findall("back/ref-list/ref")[before[0] - 1].findtext(
                "element-citation/year"
            ) not in {"1998", "2010"}:
                raise ValueError("gold_conflict_changed")
            rows.append(
                {
                    "citation_sha256": sha(right.group().encode()),
                    "source_occurrence": i + 1,
                    "source_pattern_sha256": sha(pattern.encode()),
                    "candidate_target_ordinal": target,
                    "reference_sha256": sha(citation.encode()),
                    "gold_target_ordinal": expected_old[i],
                    "decision": "gold_target_year_conflict" if before else "gold_link_absent",
                    "candidate_preserved": True,
                    "source_occurrences_verified": len(source_matches),
                }
            )
    return rows


def main():
    candidates = {c: (CANDIDATES / c / "candidate.xml").read_bytes() for c in CASES}
    if any(sha(data) != FINAL[c][0] for c, data in candidates.items()):
        raise ValueError("candidate_not_frozen")
    report = {
        "version": "vh1-reference-audit-1.0",
        "created_at": datetime.now(UTC).isoformat(),
        "native_report_sha256": sha(REPORT.read_bytes()),
        "gold_used_only_for_postbuild_evaluation": True,
        "converter_invoked": False,
        "scientific_fidelity_approved": False,
        "formal_xml_approved": False,
        "active_application_changed": False,
        "content_emitted": False,
        "source_sha256": {
            p: sha((ROOT / p).read_bytes())
            for p in (
                "ops/audit_vh1_references.py",
                "src/idml_foundation/release/semantic_fidelity.py",
                "src/idml_foundation/pipeline/crossref_evaluation.py",
                "src/idml_foundation/pipeline/idml_parser.py",
            )
        },
        "cases": {},
    }
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
    for case, relative in CASES.items():
        path = ROOT / relative
        manifest = load_manifest(ROOT / f"corpus/manifests/{case}.json")
        reference = _single_artifact(path.parent, manifest, "approved_xml_reference").read_bytes()
        source = _single_artifact(path.parent, manifest, "source_idml").read_bytes()
        raw = IdmlParser().parse(source, logical_name=path.name)
        stories = ["".join(run.text for run in story.runs) for story in raw.stories]
        old, new = [etree.fromstring(data, parser) for data in (reference, candidates[case])]
        comparison = XmlSemanticComparator().compare(reference, candidates[case])
        decisions = adjudicate(old, new, stories) if case.endswith("86") else []
        if case.endswith("135") and comparison.cross_references.decision != "pass":
            raise ValueError("second_article_crossrefs_changed")
        report["cases"][case] = {
            "source_idml_sha256": sha(source),
            "raw_comparison": comparison.model_dump(mode="json"),
            "bibliographic_adjudication": decisions,
            "bibliographic_decision": "source_qualified_development" if decisions else "pass",
            "remaining_structured_reference_review": True,
        }
        print(
            json.dumps(
                {
                    "case": case,
                    "adjudicated": len(decisions),
                    "raw_blocking_findings": comparison.blocking_findings,
                }
            ),
            flush=True,
        )
    write(ROOT / "benchmarks/qualification/reports/vh1-reference-audit-v1.json", report)


if __name__ == "__main__":
    main()
