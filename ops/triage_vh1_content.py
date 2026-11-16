"""Bind every raw content finding to prior source review, without changing its severity."""

import copy
import json
import unicodedata
from collections import Counter
from datetime import UTC, datetime

from lxml import etree

from idml_foundation.ai.security import payload_digest
from idml_foundation.domain.corpus import load_manifest
from idml_foundation.mathml import canonical_mathml, mathml_semantically_equivalent
from idml_foundation.pipeline.idml_parser import IdmlParser
from ops.audit_vh1_reference_types import CANDIDATES
from ops.gate_phase7_7c06 import _single_artifact
from ops.gate_vh1_reference_types import FINAL, REPORT, ROOT, evaluate, inputs, sha
from ops.qualify_vh1_reference_types import CASES, trees, write

AUDIT = "benchmarks/qualification/reports/vh1-reference-types-audit-v1.json"
REVIEW = "benchmarks/private/formula-review-20261008/corrections.json"
FORMULA_PROOF = "benchmarks/qualification/reports/vh1-formula-revisions-linux-v1.json"
GLYPH_PROOF = "benchmarks/qualification/reports/vh1-glyphs-linux-v1.json"
OUTPUT = "benchmarks/qualification/reports/vh1-content-triage-v1.json"
MATH = "{http://www.w3.org/1998/Math/MathML}math"


def fragment(node):
    math = copy.deepcopy(node.find(MATH))
    if math is None:
        raise ValueError("triage_mathml_missing")
    # Only the builder-generated root identifier is omitted from comparison.
    identifier = node.get("id", "")
    if node.tag == "inline-formula":
        identifier = identifier.removeprefix("e-")
    if math.get("id") != "m-" + identifier:
        raise ValueError("triage_mathml_id")
    del math.attrib["id"]
    return canonical_mathml(
        etree.tostring(math, encoding="unicode"), display=node.tag == "disp-formula"
    )


def formula_decision(case, entry, reviewed, pdf_sha256):
    if (
        reviewed["case_id"] != entry["case_id"]
        or sha(entry["mathml"].encode()) != entry["mathml_sha256"]
    ):
        raise ValueError("triage_formula_identity")
    qualification = entry["qualification"]
    revised = qualification.get("method") == "development-visual-source-review-1.0"
    if revised:
        if (
            qualification["source_pdf_sha256"] != pdf_sha256
            or qualification["previous_mathml_sha256"] != reviewed["before_sha256"]
            or qualification["corrected_mathml_sha256"] != entry["mathml_sha256"]
            or qualification["human_review_required"] is not True
            or qualification["gold_exposed_to_agent"] is not False
            or qualification["autonomous_application"] is not False
            or reviewed["status"] not in {"source_correction", "glyph_or_style_review_pending"}
        ):
            raise ValueError("triage_revision_unbound")
        disposition = "source_corrected_gold_difference"
    else:
        if entry["mathml_sha256"] != reviewed["before_sha256"]:
            raise ValueError("triage_unreviewed_mathml")
        if reviewed["status"] == "reviewed_no_confirmed_transcription_defect":
            disposition = "source_reviewed_gold_difference"
        elif (
            reviewed["status"] == "glyph_or_style_review_pending"
            and case == "esa-e20240135"
            and entry["case_id"] == "esa-math-notes-inline-005"
        ):
            disposition = "scientific_glyph_abstention"
        else:
            raise ValueError("triage_source_review_pending")
    return {
        "disposition": disposition,
        "case_id": entry["case_id"],
        "mathml_sha256": entry["mathml_sha256"],
        "source_pdf_sha256": pdf_sha256,
        "page_index": reviewed["page_index"],
        "review_entry_sha256": payload_digest(reviewed),
        "qualification_sha256": payload_digest(qualification),
        "human_review_required": True,
        "scientific_fidelity_approved": False,
    }


def check_complete(findings, decisions):
    expected = Counter(payload_digest(f) for f in findings if f["blocking"])
    actual = Counter(d["raw_finding_sha256"] for d in decisions)
    if expected != actual or any(
        d["human_review_required"] is not True or d["scientific_fidelity_approved"] is not False
        for d in decisions
    ):
        raise ValueError("triage_incomplete_or_approved")
    return dict(Counter(d["disposition"] for d in decisions))


def main():
    native, previous = inputs()
    if not evaluate(native, previous, lambda p: (ROOT / p).read_bytes())["passed"]:
        raise ValueError("native_checkpoint_not_current")
    audit = json.loads((ROOT / AUDIT).read_bytes())
    review_raw = (ROOT / REVIEW).read_bytes()
    review = json.loads(review_raw)
    formula_proof = json.loads((ROOT / FORMULA_PROOF).read_bytes())
    glyph_proof = json.loads((ROOT / GLYPH_PROOF).read_bytes())
    if sha(review_raw) != formula_proof["qualification"]["audit_sha256"] or review["gold_read"]:
        raise ValueError("source_review_not_pinned")
    if audit["native_report_sha256"] != sha(REPORT.read_bytes()):
        raise ValueError("triage_stale_audit")
    sources = (
        AUDIT,
        FORMULA_PROOF,
        GLYPH_PROOF,
        "profiles/esa-aop-1.1.json",
        "ops/triage_vh1_content.py",
        "ops/audit_vh1_reference_types.py",
        "src/idml_foundation/release/semantic_fidelity.py",
        "src/idml_foundation/mathml.py",
    )
    result = {
        "version": "vh1-content-triage-1.0",
        "created_at": datetime.now(UTC).isoformat(),
        "source_sha256": {p: sha((ROOT / p).read_bytes()) for p in sources},
        "source_review_sha256": sha(review_raw),
        "native_report_sha256": sha(REPORT.read_bytes()),
        "converter_invoked": False,
        "raw_findings_modified": False,
        "scientific_fidelity_approved": False,
        "formal_xml_approved": False,
        "active_application_changed": False,
        "human_review_required": True,
        "content_emitted": False,
        "cases": {},
    }
    for case, name in CASES.items():
        detail = native["qualification"]["cases"][case]
        data = (CANDIDATES / case / "candidate.xml").read_bytes()
        catalog_raw = (CANDIDATES / case / "formula_catalog.json").read_bytes()
        if sha(data) != FINAL[case][0] or sha(catalog_raw) != detail["catalog_sha256"]:
            raise ValueError("triage_candidate_changed")
        if (
            detail["catalog_sha256"]
            != glyph_proof["qualification"]["cases"][case]["catalog_sha256"]
        ):
            raise ValueError("triage_catalog_not_source_qualified")
        catalog = json.loads(catalog_raw)
        entries = {e["case_id"]: e for e in catalog["entries"]}
        reviews = {r["case_id"]: r for r in review["cases"][case]["entries"]}
        if review["cases"][case]["source_pdf_sha256"] != detail["source_pdf_sha256"]:
            raise ValueError("triage_pdf_changed")
        manifest = load_manifest(ROOT / f"corpus/manifests/{case}.json")
        path = ROOT / name
        source = _single_artifact(path.parent, manifest, "source_idml").read_bytes()
        if sha(source) != detail["source_idml_sha256"]:
            raise ValueError("triage_idml_changed")
        stories = [
            "".join(r.text for r in s.runs)
            for s in IdmlParser().parse(source, logical_name=path.name).stories
        ]
        gold = _single_artifact(path.parent, manifest, "approved_xml_reference").read_bytes()
        raw = audit["cases"][case]["raw_comparison"]
        if (raw["candidate_xml_sha256"], raw["reference_xml_sha256"]) != (sha(data), sha(gold)):
            raise ValueError("triage_comparison_changed")
        old, new = trees(gold, data)
        nodes = new.xpath(".//inline-formula | .//disp-formula")
        ordinals, formulas = Counter(), {}
        for position, node in enumerate(nodes, 1):
            ordinals[node.tag] += 1
            kind = "observed" if node.tag == "disp-formula" else "inline"
            key = f"esa-math-notes-{kind}-{ordinals[node.tag]:03}"
            entry = entries[key]
            if fragment(node) != entry["mathml"]:
                raise ValueError("triage_formula_position_or_content")
            formulas[position] = (node, entry)
        decisions = []
        for finding in raw["findings"]:
            if not finding["blocking"]:
                continue
            pos = finding["actual_position"]
            if finding["domain"] == "formula_content":
                node, entry = formulas[pos]
                decision = formula_decision(
                    case, entry, reviews[entry["case_id"]], detail["source_pdf_sha256"]
                )
                old_node = old.xpath(".//inline-formula | .//disp-formula")[
                    finding["expected_position"] - 1
                ]
                old_math = copy.deepcopy(old_node.find(MATH))
                old_math.attrib.pop("id", None)
                decision["existing_mathml_normalizer_agrees"] = mathml_semantically_equivalent(
                    etree.tostring(old_math, encoding="unicode"),
                    entry["mathml"],
                    display=node.tag == "disp-formula",
                )
                decision["formula_id"] = node.get("id")
            elif finding["domain"] == "metadata" and case.endswith("86") and pos in {1, 2}:
                expr = (
                    "front/journal-meta/journal-title-group/journal-title"
                    if pos == 1
                    else "front/article-meta/title-group/article-title"
                )
                a, b = ["".join(t.find(expr).itertext()) for t in (old, new)]
                if pos == 1:
                    profile = json.loads((ROOT / "profiles/esa-aop-1.1.json").read_bytes())
                    plain = "".join(
                        c for c in unicodedata.normalize("NFD", b) if not unicodedata.combining(c)
                    )
                    if b != profile["journal_title"] or a != plain:
                        raise ValueError("triage_journal_not_profile_spelling")
                    disposition = "profile_spelling_difference"
                else:
                    if "".join(a.split()) != "".join(b.split()) or not any(
                        " ".join(b.split()) in " ".join(s.split()) for s in stories
                    ):
                        raise ValueError("triage_title_not_literal_idml")
                    disposition = "source_preserved_word_boundary"
                decision = {
                    "disposition": disposition,
                    "source_idml_sha256": sha(source),
                    "human_review_required": True,
                    "scientific_fidelity_approved": False,
                }
            else:
                raise ValueError("triage_unreviewed_domain_or_position")
            decisions.append(
                {
                    **decision,
                    "raw_finding_sha256": payload_digest(finding),
                    "domain": finding["domain"],
                    "actual_position": pos,
                    "expected_sha256": finding["expected_sha256"],
                    "actual_sha256": finding["actual_sha256"],
                }
            )
        counts = check_complete(raw["findings"], decisions)
        result["cases"][case] = {
            "candidate_sha256": sha(data),
            "raw_comparison_passed": raw["passed"],
            "raw_blocking_findings": raw["blocking_findings"],
            "classification_counts": counts,
            "decisions": decisions,
            "all_raw_blocking_findings_classified": True,
        }
        print(json.dumps({"case": case, "classifications": counts}), flush=True)
    write(ROOT / OUTPUT, result)


if __name__ == "__main__":
    main()
