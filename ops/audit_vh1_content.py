"""Post-build reference comparison only: never load gold into the converter."""

import json
from datetime import UTC, datetime

from idml_foundation.domain.corpus import load_manifest
from idml_foundation.release.semantic_fidelity import XmlSemanticComparator
from ops.gate_phase7_7c06 import _single_artifact
from ops.gate_vh1_glyphs import FINAL, ROOT, sha
from ops.qualify_vh1_glyphs import CASES, write


def main():
    candidate_root = ROOT / "benchmarks/private/output/vh1-glyphs-20261008T201205Z"
    report = {
        "version": "vh1-content-postbuild-audit-1.0",
        "created_at": datetime.now(UTC).isoformat(),
        "gold_used_only_for_postbuild_evaluation": True,
        "converter_invoked": False,
        "scientific_fidelity_approved": False,
        "formal_xml_approved": False,
        "active_application_changed": False,
        "content_emitted": False,
        "source_sha256": {
            p: sha((ROOT / p).read_bytes())
            for p in (
                "ops/audit_vh1_content.py",
                "src/idml_foundation/release/semantic_fidelity.py",
                "src/idml_foundation/pipeline/crossref_evaluation.py",
            )
        },
        "cases": {},
    }
    # Freeze/verify both outputs before opening any reference.
    candidates = {case: (candidate_root / case / "candidate.xml").read_bytes() for case in CASES}
    if any(sha(xml) != FINAL[case][0] for case, xml in candidates.items()):
        raise ValueError("candidate_not_frozen")
    for case, path in CASES.items():
        manifest = load_manifest(ROOT / f"corpus/manifests/{case}.json")
        reference = _single_artifact((ROOT / path).parent, manifest, "approved_xml_reference")
        comparison = XmlSemanticComparator().compare(reference.read_bytes(), candidates[case])
        report["cases"][case] = comparison.model_dump(mode="json")
        print(
            json.dumps(
                {"case": case, "raw_comparator_blocking_findings": comparison.blocking_findings}
            ),
            flush=True,
        )
    write(ROOT / "benchmarks/qualification/reports/vh1-content-postbuild-audit-v1.json", report)
    print(json.dumps({"saved": True, "scientific_fidelity_approved": False}))


if __name__ == "__main__":
    main()
