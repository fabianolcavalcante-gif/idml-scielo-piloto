from __future__ import annotations

import hashlib

import pytest
from lxml import etree

from idml_foundation.ai.evidence import evidence_reference
from idml_foundation.ai.formula_catalog import (
    _strip_qualified_script_suffixes,
    build_formula_transcription_catalog,
)
from idml_foundation.ai.real_domain_corpus import build_real_domain_corpus
from idml_foundation.ai.security import payload_digest
from idml_foundation.ai.visual_formula_corpus import (
    PdfFormulaCrop,
    attach_visual_formula_evidence,
)
from idml_foundation.domain.canonical import Section
from idml_foundation.domain.common import stable_id
from idml_foundation.pipeline.service import DeterministicPipeline
from idml_foundation.release.semantic_fidelity import XmlSemanticComparator
from tests.phase3_helpers import synthetic_idml

MATHML = (
    '<mml:math xmlns:mml="http://www.w3.org/1998/Math/MathML" display="block">'
    "<mml:mi>x</mml:mi><mml:mo>=</mml:mo><mml:mn>2</mml:mn></mml:math>"
)
GOLD_MATHML = MATHML.replace("<mml:mn>2</mml:mn>", "<mml:mn>1</mml:mn>")


def test_qualified_formula_removes_multinode_script_suffix_duplicate() -> None:
    mathml = (
        '<mml:math xmlns:mml="http://www.w3.org/1998/Math/MathML">'
        "<mml:msubsup><mml:mi>C</mml:mi><mml:mi>k</mml:mi>"
        "<mml:mo>*</mml:mo></mml:msubsup></mml:math>"
    )
    payload = {
        "body": [
            {
                "blocks": [
                    {
                        "content": {
                            "plain": {"value": "k* after", "transformation": "source"},
                            "inlines": [
                                {
                                    "kind": "inline_formula",
                                    "text": "",
                                    "formula_source": {"value": mathml},
                                },
                                {"kind": "subscript", "text": "k"},
                                {"kind": "text", "text": "* after"},
                            ],
                        }
                    }
                ]
            }
        ]
    }

    _strip_qualified_script_suffixes(
        payload,
        [("/body/0/blocks/0/content/inlines/0/formula_source/value", mathml)],
    )

    content = payload["body"][0]["blocks"][0]["content"]
    assert content["plain"]["value"] == " after"
    assert content["plain"]["transformation"] == (
        "qualified-formula-removes-source-script-duplicate"
    )
    assert content["inlines"] == [
        {
            "kind": "inline_formula",
            "text": "",
            "formula_source": {"value": mathml},
        },
        {"kind": "text", "text": " after"},
    ]


def _gold_xml() -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<article xmlns:mml="http://www.w3.org/1998/Math/MathML"><body><sec>'
        "<title>Introduction</title><sec><title>Nested method details</title>"
        f'<disp-formula id="DM1"><label>(1)</label>{GOLD_MATHML}</disp-formula>'
        "</sec></sec></body></article>"
    ).encode()


def _qualified_fixture() -> tuple[bytes, dict[str, object], dict[str, object]]:
    source = synthetic_idml(include_subsection=True, include_formula=True)
    dataset, _ = build_real_domain_corpus(
        idml_data=source,
        approved_xml=_gold_xml(),
        logical_name="ESA_2024001_AOP.idml",
        corpus_id="esa-fixture",
        source_idml_sha256=hashlib.sha256(source).hexdigest(),
    )
    formula_case = next(case for case in dataset["cases"] if case["domain"] == "math_notes")
    dataset = attach_visual_formula_evidence(
        dataset,
        case_id=formula_case["case_id"],
        image_data=b"\x89PNG\r\n\x1a\nqualified-formula",
        source_pdf_name="fixture.pdf",
        crop=PdfFormulaCrop(page_index=0, bbox=(10.0, 20.0, 110.0, 70.0)),
    )
    formula_case = next(case for case in dataset["cases"] if case["domain"] == "math_notes")
    source_path, representation_path = formula_case["atomic_formula"]["required_patch_paths"]
    evidence_id = formula_case["evidence"]["evidence_id"]
    proposal = {
        "schema_version": "agent-proposal-1.1",
        "domain": "math_notes",
        "patch": [
            {
                "op": "replace",
                "path": source_path,
                "value": MATHML,
                "evidence_ids": [evidence_id],
            },
            {
                "op": "replace",
                "path": representation_path,
                "value": "mathml",
                "evidence_ids": [evidence_id],
            },
        ],
        "confidence": 0.98,
        "evidence": [evidence_reference(formula_case["evidence"])],
        "alternatives": ["Retain the source image pending final human validation."],
        "reason": "The authenticated visual evidence supports this exact formula transcription.",
        "needs_human": True,
    }
    proposal_sha256 = payload_digest(proposal)
    result = {
        "run_id": "formula-test-001",
        "dataset_version": dataset["version"],
        "corpus_id": dataset["corpus_id"],
        "model": "openai/gpt-5.4-mini",
        "human_review_required": True,
        "application_flags_enabled": False,
        "total_cost_microusd": 123,
        "cases": [
            {
                "case_id": formula_case["case_id"],
                "status": "completed",
                "critic_verdicts": {"xml_critic": "pass", "editorial_critic": "pass"},
                "final_decision": "accepted_for_human_review",
                "adjudicator_decision": "accept",
                "quality": {},
                "roles": [
                    {"role": "proposer", "cost_microusd": 40, "output": proposal},
                    {
                        "role": "xml_critic",
                        "cost_microusd": 20,
                        "output": {"proposal_sha256": proposal_sha256},
                    },
                    {
                        "role": "editorial_critic",
                        "cost_microusd": 20,
                        "output": {"proposal_sha256": proposal_sha256},
                    },
                    {
                        "role": "adjudicator",
                        "cost_microusd": 43,
                        "output": {
                            "decision": "accept",
                            "agreement": "unanimous_accept",
                            "false_consensus_risk": False,
                            "reason_codes": ["EVIDENCE_SUPPORTED"],
                        },
                    },
                ],
            }
        ],
    }
    return source, dataset, result


def test_catalog_applies_complete_evidence_bound_formula_transition() -> None:
    source, dataset, result = _qualified_fixture()
    catalog, report = build_formula_transcription_catalog(
        dataset=dataset,
        dataset_sha256=payload_digest(dataset),
        journal_profile_id="esa-aop-1.0.0",
        results=(result,),
    )

    pipeline_result = DeterministicPipeline(formula_catalog=catalog).run(
        source,
        logical_name="ESA_2024001_AOP.idml",
    )
    root = etree.fromstring(pipeline_result.xml)

    assert root.xpath("count(body//disp-formula/*[local-name()='math'])") == 1.0
    assert root.xpath("count(body//disp-formula/graphic)") == 0.0
    assert pipeline_result.validation.valid is True
    assert report["formula_cases"] == 1
    assert report["visual_source_overrides"] == 1
    assert report["critic_passes"] == 2
    assert report["human_review_required"] is True
    assert any(
        reason.startswith("ai_qualified_formula_transcriptions_pending_human:")
        for reason in pipeline_result.canonical.review_reasons
    )

    semantic = XmlSemanticComparator().compare(_gold_xml(), pipeline_result.xml)
    reconciled, qualified = catalog.reconcile_semantic_report(semantic)
    formula_content = next(
        score for score in reconciled.domains if score.domain == "formula_content"
    )
    assert qualified == 1
    assert formula_content.passed is True
    assert not any(
        finding.blocking and finding.domain == "formula_content" for finding in reconciled.findings
    )


def test_catalog_relocates_formula_by_authenticated_ordinal_after_hierarchy_change() -> None:
    source, dataset, result = _qualified_fixture()
    catalog, _ = build_formula_transcription_catalog(
        dataset=dataset,
        dataset_sha256=payload_digest(dataset),
        journal_profile_id="esa-aop-1.0.0",
        results=(result,),
    )
    original = DeterministicPipeline().run(source, logical_name="ESA_2024001_AOP.idml")
    top = original.canonical.body[0]
    subsection = top.children[0]
    nested = Section(
        id=stable_id(original.canonical.article_id, "section", "relocated-formula"),
        title=subsection.title.model_copy(update={"value": "Relocated formula"}),
        level=3,
        blocks=subsection.blocks,
        evidence_ids=subsection.evidence_ids,
    )
    relocated = original.canonical.model_copy(
        update={
            "body": (
                top.model_copy(
                    update={
                        "children": (
                            subsection.model_copy(update={"blocks": (), "children": (nested,)}),
                        )
                    }
                ),
            )
        }
    )

    applied = catalog.apply(
        relocated,
        source_idml_sha256=hashlib.sha256(source).hexdigest(),
    )

    formula = next(
        block for block in applied.body[0].children[0].children[0].blocks if block.kind == "formula"
    )
    assert formula.kind == "formula"
    assert formula.representation.value == "mathml"
    assert formula.source.value == MATHML


def test_catalog_rejects_tampered_visual_evidence() -> None:
    _, dataset, result = _qualified_fixture()
    roles = result["cases"][0]["roles"]
    proposal = roles[0]["output"]
    proposal["evidence"][0]["image_sha256"] = "0" * 64
    roles[1]["output"]["proposal_sha256"] = payload_digest(proposal)

    with pytest.raises(ValueError, match="visual evidence"):
        build_formula_transcription_catalog(
            dataset=dataset,
            dataset_sha256=payload_digest(dataset),
            journal_profile_id="esa-aop-1.0.0",
            results=(result,),
        )


def test_catalog_rejects_incomplete_qualification() -> None:
    _, dataset, result = _qualified_fixture()
    result["cases"][0]["critic_verdicts"]["editorial_critic"] = "fail"

    with pytest.raises(ValueError, match="formula case is not qualified"):
        build_formula_transcription_catalog(
            dataset=dataset,
            dataset_sha256=payload_digest(dataset),
            journal_profile_id="esa-aop-1.0.0",
            results=(result,),
        )
