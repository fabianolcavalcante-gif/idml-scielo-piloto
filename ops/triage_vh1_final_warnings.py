"""Classify native warnings without accepting, deleting, or lowering their severity."""

import argparse
import json
from collections import Counter
from pathlib import Path

from lxml import etree

from ops.qualify_vh1_final_validation import ROOT, sha

CODES = {
    "packtools": {
        "aff-orgdiv2-institution-content-type-orgdiv2-exist-4bb6052e0349": "affiliation",
        "app-app-element-app-group-app-exist-6e8b29290a5b": "appendix",
        "sec-sec-content-sec-p-exist-6ca2373fbf26": "section",
    },
    "spsvalidator": {
        "aff-aff-orgdiv2-institution-content-type-orgdiv2-exist-aeb9d1e856d7": "affiliation",
        "app-app-app-element-app-group-app-exist-b70163d3b3dc": "appendix",
        "sec-sec-sec-content-sec-p-exist-1b8d5e5cd455": "section",
    },
}
SPEC_SHA = "09ade688acbf1aa6c48324b660bf4baeb9293c92ff315a2d68c371251909bbef"
SPEC = "benchmarks/private/output/vh1-history-spec-20261007T114702Z/sps-specification.txt"
OUTPUT = "benchmarks/qualification/reports/vh1-final-warnings-v2.json"


def fingerprint(value):
    return sha(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def node_proof(node):
    return {"id": node.get("id"), "subtree_sha256": sha(etree.tostring(node, method="c14n"))}


def structural_evidence(xml):
    root = etree.fromstring(
        xml, etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True)
    )
    groups = {"affiliation": [], "appendix": [], "section": []}
    for aff in root.xpath("front/article-meta/aff[not(institution[@content-type='orgdiv2'])]"):
        original, institution, division = [
            aff.findtext("institution[@content-type='" + kind + "']", "")
            for kind in ("original", "orgname", "orgdiv1")
        ]
        if not original or not institution or not division or any(c in division for c in ",;\n\r"):
            raise ValueError("affiliation_requires_specific_review")
        prefix = institution + ", " + division
        if not any(original.startswith(prefix + " " + dash + " ") for dash in ("\u2013", "\u2014")):
            raise ValueError("affiliation_not_literal")
        groups["affiliation"].append(
            {
                **node_proof(aff),
                "disposition": "single_subdivision_in_preserved_original",
                "original_sha256": sha(original.encode()),
                "missing_division_invented": False,
            }
        )
    if not root.xpath(".//app"):
        if root.xpath(".//xref[@ref-type='app' or @ref-type='app-group'] | .//app-group"):
            raise ValueError("appendix_referenced_but_missing")
        groups["appendix"].append(
            {
                "disposition": "optional_element_absent_source_review_retained",
                "absence_is_not_proof_of_source_completeness": True,
                "element_inserted": False,
            }
        )
    for sec in root.xpath(".//sec[not(p)]"):
        if (
            not sec.findtext("title")
            or not sec.findall("sec")
            or any(child.tag not in {"title", "sec"} for child in sec)
            or any(
                not child.findtext("title") or not child.xpath(".//p[normalize-space()]")
                for child in sec.findall("sec")
            )
        ):
            raise ValueError("section_not_populated_by_subsections")
        groups["section"].append(
            {
                **node_proof(sec),
                "disposition": "populated_subsections_normative_example",
                "subsections": len(sec.findall("sec")),
                "descendant_paragraphs": len(sec.findall(".//p")),
                "empty_paragraph_inserted": False,
            }
        )
    return groups


def classify(xml, runs):
    groups = structural_evidence(xml)
    if len(runs) != 2 or {r["name"] for r in runs} != set(CODES):
        raise ValueError("required_native_tools_missing")
    output = []
    for run in runs:
        mapping = CODES[run["name"]]
        counts = Counter()
        rows = []
        for finding in run["findings"]:
            if finding["response"] != "warning" or finding["code"] not in mapping:
                raise ValueError("unclassified_native_finding")
            group = mapping[finding["code"]]
            counts[group] += 1
            rows.append(
                {
                    "raw_finding_sha256": fingerprint(finding),
                    "occurrence": counts[group],
                    "group": group,
                    # Native sanitization shares a locator across multiple rows.
                    # Bind the full structural group, not an invented row-to-node mapping.
                    "structural_group_sha256": fingerprint(groups[group]),
                    "severity_retained": "warning",
                    "human_review_required": True,
                    "accepted_for_release": False,
                }
            )
        if dict(counts) != {k: len(v) for k, v in groups.items() if v}:
            raise ValueError("warning_occurrences_do_not_match_structure")
        if run["counts"] != {"warning": len(rows)}:
            raise ValueError("native_counts_mismatch")
        output.append({"name": run["name"], "decisions": rows, "counts": dict(counts)})
    return {"structural_groups": groups, "validators": output, "all_warnings_classified": True}


def main():
    from ops.gate_vh1_final_validation import REPORT, evaluate, inputs

    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()
    reader = lambda p: (ROOT / p).read_bytes()  # noqa: E731
    native, previous = inputs()
    if not evaluate(native, previous, reader)["passed"]:
        raise ValueError("native_checkpoint_invalid")
    if sha(reader(SPEC)) != SPEC_SHA:
        raise ValueError("normative_source_changed")
    cases = {}
    for case in native["cases"]:
        name = case["case"]
        detail = native["qualification"]["cases"][name]
        xml = (args.folder / name / "candidate.xml").read_bytes()
        package = (args.folder / name / "candidate.zip").read_bytes()
        if (sha(xml), sha(package)) != (detail["xml_sha256"], detail["package_sha256"]):
            raise ValueError("candidate_changed")
        cases[name] = {
            "xml_sha256": sha(xml),
            "package_sha256": sha(package),
            **classify(xml, case["validators"]),
            "authorities_completed_at_qualification": True,
            "xpm": {
                "status": "unavailable",
                "candidate_package_sha256": sha(package),
                "reasons": ["dedicated-worker-pending", "sps-1.10-compatibility-unqualified"],
            },
        }
    sources = [
        REPORT.relative_to(ROOT).as_posix(),
        "benchmarks/qualification/reports/vh1-content-triage-v1.json",
        "benchmarks/qualification/reports/vh1-xpm-download-v1.json",
        "config/validator-registry-vh1-history.json",
        "ops/triage_vh1_final_warnings.py",
    ]
    report = {
        "version": "vh1-final-warnings-1.0",
        "cases": cases,
        "source_sha256": {p: sha(reader(p)) for p in sources},
        "specification_sha256": SPEC_SHA,
        "specification_url": "https://docs.google.com/document/d/1GTv4Inc2LS_AXY-ToHT3HmO66UT0VAHWJNOIqzBNSgA/edit",
        "specification_sections": ["aff", "app-group", "sec"],
        "raw_findings_modified": False,
        "warnings_accepted_for_release": False,
        "formal_xml_approved": False,
        "scientific_fidelity_approved": False,
        "active_application_changed": False,
        "content_emitted": False,
        "vh07_complete": False,
        "release_status": "validation-unavailable",
        "remaining_ambiguous_glyphs": 1,
        "reference_locator_reviews": 2,
    }
    with (ROOT / OUTPUT).open("x", encoding="utf-8") as stream:
        json.dump(report, stream, sort_keys=True, indent=2)
    print(json.dumps({"path": OUTPUT, "sha256": sha(reader(OUTPUT)), "vh07_complete": False}))


if __name__ == "__main__":
    main()
