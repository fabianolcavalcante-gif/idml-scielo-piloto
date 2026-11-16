import hashlib
import json

import pytest

from idml_foundation.ai.evidence import reassemble_evidence
from idml_foundation.ai.real_domain_corpus import build_real_domain_corpus
from tests.phase3_helpers import synthetic_idml


def _gold_xml() -> bytes:
    return b"""<?xml version="1.0" encoding="UTF-8"?>
<article xmlns:mml="http://www.w3.org/1998/Math/MathML">
  <body>
    <sec><title>Introduction</title>
      <sec><title>Nested method details</title>
        <disp-formula id="DM1"><mml:math><mml:mi>x</mml:mi><mml:mo>=</mml:mo>
          <mml:mn>1</mml:mn></mml:math></disp-formula>
      </sec>
    </sec>
  </body>
</article>
"""


def test_real_domain_builder_uses_authorized_structure_and_formula_gap() -> None:
    source = synthetic_idml(include_subsection=True, include_formula=True)
    dataset, report = build_real_domain_corpus(
        idml_data=source,
        approved_xml=_gold_xml(),
        logical_name="ESA_2024001_AOP.idml",
        corpus_id="esa-fixture",
        source_idml_sha256=hashlib.sha256(source).hexdigest(),
    )

    assert dataset["version"] == "idml-agent-real-domain-eval-1.2"
    assert [case["domain"] for case in dataset["cases"]] == ["structure", "math_notes"]
    structure, formula = dataset["cases"]
    assert structure["current_value"] != structure["expected_value"]
    assert reassemble_evidence(structure["evidence"]) == structure["expected_value"]
    assert formula["current_value"] == "Equations.pdf"
    assert reassemble_evidence(formula["evidence"]) == formula["expected_value"]
    assert formula["fixture_provenance"]["application_ready"] is True
    assert formula["expected_value"].startswith("<mml:math xmlns:mml=")
    assert formula["atomic_formula"]["current_representation"] == "image"
    assert formula["atomic_formula"]["required_patch_paths"] == [
        formula["field_path"],
        formula["field_path"].removesuffix("/source/value") + "/representation",
    ]
    assert report["math_notes"]["display_formula_pairing_complete"] is True
    assert report["math_notes"]["native_mathml_transcription_complete"] is False
    assert report["math_notes"]["atomic_mathml_transition_supported"] is True
    assert report["math_notes"]["atomic_mathml_candidate_valid"] is True
    assert report["math_notes"]["atomic_mathml_candidate_display_count"] == 1
    serialized_report = json.dumps(report)
    assert "Nested method details" not in serialized_report
    assert "Equations.pdf" not in serialized_report


def test_real_domain_builder_rejects_source_hash_mismatch() -> None:
    source = synthetic_idml(include_subsection=True, include_formula=True)

    with pytest.raises(ValueError, match="source IDML hash mismatch"):
        build_real_domain_corpus(
            idml_data=source,
            approved_xml=_gold_xml(),
            logical_name="ESA_2024001_AOP.idml",
            corpus_id="esa-fixture",
            source_idml_sha256="0" * 64,
        )
