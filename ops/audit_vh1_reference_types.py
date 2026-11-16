"""Audit all source-bound references after freezing candidates; never change XML."""

import json
from collections import Counter
from datetime import UTC, datetime

from lxml import etree

from idml_foundation.domain.corpus import load_manifest
from idml_foundation.pipeline.idml_parser import IdmlParser
from idml_foundation.release.semantic_fidelity import XmlSemanticComparator
from ops.audit_vh1_references import adjudicate
from ops.gate_phase7_7c06 import _single_artifact
from ops.gate_vh1_reference_types import FINAL, REPORT, ROOT, sha
from ops.qualify_vh1_reference_types import BASELINE, CASES, CONTRACT, trees, verify_delta, write

CANDIDATES = ROOT / "benchmarks/private/output/vh1-reference-types-20261014T104156Z"


def inventory(before, after, source_stories):
    old, new = trees(before, after)
    refs = [r.findall("back/ref-list/ref") for r in (old, new)]
    rows, types = [], Counter()
    normalized_stories = [" ".join(s.split()) for s in source_stories]
    for position, (a, b) in enumerate(zip(*refs, strict=True), 1):
        if a.get("id") != b.get("id"):
            raise ValueError("reference_identity_changed")
        mixed = "".join(b.find("mixed-citation").itertext())
        if not any(" ".join(mixed.split()) in s for s in normalized_stories):
            raise ValueError("reference_not_in_idml")
        # Do not allow title/type repair to change these established identities.
        for path in (
            "mixed-citation",
            "element-citation/year",
            "element-citation/pub-id",
            "element-citation/ext-link",
            "element-citation/person-group[@person-group-type='author']",
        ):
            nodes = [[etree.tostring(n, method="c14n") for n in r.findall(path)] for r in (a, b)]
            if nodes[0] != nodes[1]:
                raise ValueError("protected_reference_field_changed")
        structured = b.find("element-citation")
        if structured is None:
            raise ValueError("structured_reference_missing")
        spans = []
        for node in structured.iter():
            if node.text and node.text.strip():
                start = mixed.find(node.text)
                if start < 0:
                    raise ValueError("structured_text_not_literal")
                spans.append(
                    {
                        "tag": node.tag,
                        "start": start,
                        "end": start + len(node.text),
                        "sha256": sha(node.text.encode()),
                    }
                )
        kind = structured.get("publication-type")
        types[kind] += 1
        rows.append(
            {
                "position": position,
                "id": b.get("id"),
                "publication_type": kind,
                "mixed_citation_sha256": sha(mixed.encode()),
                "source_spans": spans,
                "access_dates": len(structured.findall("date-in-citation")),
                "type_review_required": kind == "other",
            }
        )
    return {
        "references": rows,
        "types": dict(types),
        "reference_count": len(rows),
        "literal_text_coverage_only_not_semantic_approval": True,
        "unresolved_type_positions": [r["position"] for r in rows if r["type_review_required"]],
    }


def main():
    candidates = {c: (CANDIDATES / c / "candidate.xml").read_bytes() for c in CASES}
    if any(sha(data) != FINAL[c][0] for c, data in candidates.items()):
        raise ValueError("candidate_not_frozen")
    contract = json.loads((ROOT / CONTRACT).read_bytes())
    report = {
        "version": "vh1-reference-types-audit-1.0",
        "created_at": datetime.now(UTC).isoformat(),
        "native_report_sha256": sha(REPORT.read_bytes()),
        "converter_invoked": False,
        "gold_used_only_for_postbuild_evaluation": True,
        "content_emitted": False,
        "scientific_fidelity_approved": False,
        "formal_xml_approved": False,
        "active_application_changed": False,
        "source_sha256": {
            p: sha((ROOT / p).read_bytes())
            for p in (
                "ops/audit_vh1_reference_types.py",
                "ops/audit_vh1_references.py",
                "src/idml_foundation/release/semantic_fidelity.py",
                "src/idml_foundation/pipeline/idml_parser.py",
            )
        },
        "cases": {},
    }
    for case, relative in CASES.items():
        path = ROOT / relative
        manifest = load_manifest(ROOT / f"corpus/manifests/{case}.json")
        source = _single_artifact(path.parent, manifest, "source_idml").read_bytes()
        if sha(source) != contract["source_idml_sha256"][case]:
            raise ValueError("source_changed")
        raw = IdmlParser().parse(source, logical_name=path.name)
        stories = ["".join(run.text for run in story.runs) for story in raw.stories]
        before = (BASELINE / case / "candidate.xml").read_bytes()
        audit = inventory(before, candidates[case], stories)
        if audit["unresolved_type_positions"] != contract["unresolved_types"][case]:
            raise ValueError("unreviewed_classification")
        delta = verify_delta(before, candidates[case], contract["cases"][case])
        # Gold is read only after both output hashes were frozen and source checked.
        gold = _single_artifact(path.parent, manifest, "approved_xml_reference").read_bytes()
        comparison = XmlSemanticComparator().compare(gold, candidates[case])
        decisions = (
            adjudicate(*trees(gold, candidates[case]), stories) if case.endswith("86") else []
        )
        report["cases"][case] = {
            "candidate_sha256": sha(candidates[case]),
            "source_idml_sha256": sha(source),
            "inventory": audit,
            "delta": delta,
            "raw_comparison": comparison.model_dump(mode="json"),
            "bibliographic_adjudication": decisions,
        }
        print(
            json.dumps(
                {
                    "case": case,
                    "types": audit["types"],
                    "raw_blocking_findings": comparison.blocking_findings,
                }
            ),
            flush=True,
        )
    write(ROOT / "benchmarks/qualification/reports/vh1-reference-types-audit-v1.json", report)


if __name__ == "__main__":
    main()
