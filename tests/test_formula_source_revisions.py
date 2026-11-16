import copy
import hashlib
from datetime import UTC, datetime

import pytest

from idml_foundation.ai.formula_catalog import (
    FormulaTranscriptionCatalog,
    FormulaTranscriptionEntry,
    build_formula_transcription_catalog,
    revise_formula_catalog,
)
from idml_foundation.ai.security import payload_digest
from idml_foundation.pipeline.service import DeterministicPipeline
from tests.test_formula_catalog import MATHML, _qualified_fixture


def sha(data):
    return hashlib.sha256(data).hexdigest()


def fixture():
    source, dataset, result = _qualified_fixture()
    old, _ = build_formula_transcription_catalog(
        dataset=dataset,
        dataset_sha256="a" * 64,
        journal_profile_id="esa-aop-1.0.0",
        results=(result,),
    )
    entry = old.entries[0]
    corrected = MATHML.replace("<mml:mn>2</mml:mn>", "<mml:mn>3</mml:mn>")
    pdf, png = b"%PDF-1.7 synthetic authorized fixture", b"\x89PNG\r\n\x1a\nsynthetic crop"
    revision = {
        "method": "development-visual-source-review-1.0",
        "previous_catalog_id": old.catalog_id,
        "previous_mathml": entry.mathml,
        "previous_mathml_sha256": entry.mathml_sha256,
        "previous_qualification": entry.qualification.model_dump(mode="json"),
        "corrected_mathml_sha256": sha(corrected.encode()),
        "source_idml_sha256": sha(source),
        "source_pdf_sha256": sha(pdf),
        "page_index": 0,
        "box": {"x": 1, "y": 2, "width": 100, "height": 50},
        "crop_sha256": sha(png),
        "reviewed_at": datetime.now(UTC).isoformat(),
        "reason_code": "symbol_mismatch",
        "human_review_required": True,
        "gold_exposed_to_agent": False,
        "autonomous_application": False,
    }
    updated = {
        **entry.model_dump(mode="json"),
        "mathml": corrected,
        "mathml_sha256": sha(corrected.encode()),
        "qualification": revision,
    }
    return old, source, pdf, png, updated


def build(values):
    old, source, pdf, png, updated = values
    entry = FormulaTranscriptionEntry.model_validate(updated)
    return revise_formula_catalog(
        old, source_idml=source, source_pdf=pdf, corrections=(entry,), crops={entry.case_id: png}
    )


def test_new_version_preserves_original_and_pending_human_review():
    values = fixture()
    old, source, _, _, _ = values
    original = old.model_dump_json()
    revised = build(values)
    assert old.model_dump_json() == original
    assert revised.catalog_id != old.catalog_id
    assert revised.version == "formula-transcription-catalog-1.1"
    assert revised.entries[0].qualification.previous_qualification == old.entries[0].qualification
    assert revised == FormulaTranscriptionCatalog.model_validate_json(revised.model_dump_json())
    pipeline = DeterministicPipeline(formula_catalog=revised)
    a, b = (pipeline.run(source, logical_name="ESA_2024001_AOP.idml") for _ in range(2))
    assert a.xml == b.xml
    assert b"<mml:mn>3</mml:mn>" in a.xml
    assert any(
        r.startswith("source_revised_formula_transcriptions_pending_human:")
        for r in a.canonical.review_reasons
    )
    assert any(e.source_kind == "pdf" and e.locator.page_index == 0 for e in a.canonical.evidence)
    raw = a.canonical.model_dump_json()
    assert "source-revised-visual-mathml" in raw
    assert "original AI provenance retained" in raw


@pytest.mark.parametrize(
    "mutation",
    [
        "parent",
        "old_math",
        "old_hash",
        "new_hash",
        "pdf",
        "idml",
        "crop",
        "human",
        "gold",
        "automatic",
        "method",
        "critic",
        "confidence",
        "source_path",
        "target_hash",
        "page",
        "box_negative",
        "box_empty",
        "box_large",
        "box_nan",
        "naive_date",
        "same_math",
    ],
)
def test_tampered_source_correction_is_rejected(mutation):
    values = list(fixture())
    entry = values[-1]
    r = entry["qualification"]
    if mutation in {"parent", "old_hash", "new_hash", "pdf", "idml", "crop"}:
        key = {
            "parent": "previous_catalog_id",
            "old_hash": "previous_mathml_sha256",
            "new_hash": "corrected_mathml_sha256",
            "pdf": "source_pdf_sha256",
            "idml": "source_idml_sha256",
            "crop": "crop_sha256",
        }[mutation]
        r[key] = "0" * 64
    elif mutation == "old_math":
        r["previous_mathml"] = r["previous_mathml"].replace(">2<", ">9<")
        r["previous_mathml_sha256"] = sha(r["previous_mathml"].encode())
    elif mutation in {"human", "gold", "automatic"}:
        key = {
            "human": "human_review_required",
            "gold": "gold_exposed_to_agent",
            "automatic": "autonomous_application",
        }[mutation]
        r[key] = not r[key]
    elif mutation == "method":
        r["method"] = "expert-accepted"
    elif mutation == "critic":
        r["previous_qualification"]["run_id"] = "invented-run-id"
    elif mutation == "confidence":
        entry["confidence"] = 1.0
    elif mutation == "source_path":
        entry["source_path"] = entry["source_path"].replace("/body/0/", "/body/1/")
        entry["representation_path"] = entry["representation_path"].replace("/body/0/", "/body/1/")
    elif mutation == "target_hash":
        entry["current_value_sha256"] = "0" * 64
    elif mutation == "page":
        r["page_index"] = -1
    elif mutation.startswith("box_"):
        key, value = {
            "box_negative": ("x", -1),
            "box_empty": ("width", 0),
            "box_large": ("width", 300000),
            "box_nan": ("x", float("nan")),
        }[mutation]
        r["box"][key] = value
    elif mutation == "naive_date":
        r["reviewed_at"] = "2026-10-08T12:00:00"
    elif mutation == "same_math":
        entry["mathml"] = r["previous_mathml"]
        entry["mathml_sha256"] = r["corrected_mathml_sha256"] = r["previous_mathml_sha256"]
    with pytest.raises(ValueError):
        build(values)


@pytest.mark.parametrize(
    "mutation",
    [
        "source",
        "pdf",
        "crop",
        "empty",
        "duplicate",
        "unknown",
        "missing_crop",
        "original_qualification",
    ],
)
def test_revision_builder_fails_closed(mutation):
    old, source, pdf, png, updated = fixture()
    entry = FormulaTranscriptionEntry.model_validate(updated)
    entries, crops = (entry,), {entry.case_id: png}
    if mutation == "source":
        source += b"changed"
    elif mutation == "pdf":
        pdf += b"changed"
    elif mutation == "crop":
        crops[entry.case_id] += b"changed"
    elif mutation == "empty":
        entries, crops = (), {}
    elif mutation == "duplicate":
        entries = (entry, entry)
    elif mutation == "unknown":
        entry = FormulaTranscriptionEntry.model_validate({**updated, "case_id": "unknown-case-001"})
        entries, crops = (entry,), {entry.case_id: png}
    elif mutation == "missing_crop":
        crops = {}
    elif mutation == "original_qualification":
        entries = old.entries
    with pytest.raises(ValueError):
        revise_formula_catalog(
            old, source_idml=source, source_pdf=pdf, corrections=entries, crops=crops
        )


@pytest.mark.parametrize(
    "mutation", ["downgrade", "source", "upgrade_without_revision", "empty_revision"]
)
def test_catalog_version_and_source_binding(mutation):
    values = fixture()
    revised = build(values)
    raw = copy.deepcopy(revised.model_dump(mode="json", exclude={"catalog_id"}))
    if mutation == "downgrade":
        raw["version"] = "formula-transcription-catalog-1.0"
    elif mutation == "source":
        raw["source_idml_sha256"] = "0" * 64
    else:
        raw["entries"][0]["qualification"] = (
            values[0].entries[0].qualification.model_dump(mode="json")
        )
        if mutation == "empty_revision":
            raw["entries"] = []
    with pytest.raises(ValueError):
        FormulaTranscriptionCatalog.model_validate({**raw, "catalog_id": payload_digest(raw)})
