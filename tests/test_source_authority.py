from __future__ import annotations

import hashlib

import pytest

from idml_foundation.release.semantic_fidelity import XmlSemanticComparator
from idml_foundation.release.source_authority import (
    build_source_authority_qualification,
)


def _article(journal: str, title: str, target: str) -> bytes:
    return f"""<article><front>
      <journal-meta><journal-title-group><journal-title>{journal}</journal-title>
      </journal-title-group></journal-meta><article-meta>
      <article-id pub-id-type="doi">10.1000/example</article-id>
      <article-id pub-id-type="other">00212</article-id>
      <title-group><article-title>{title}</article-title>
      <trans-title-group><trans-title>Titulo secundario</trans-title></trans-title-group>
      </title-group></article-meta></front><body><sec><title>Body</title>
      <p>Source text <xref ref-type="bibr" rid="{target}">citation</xref>.</p>
      </sec></body><back><ref-list>
      <ref id="ref1"><mixed-citation>First source.</mixed-citation></ref>
      <ref id="ref2"><mixed-citation>Second source.</mixed-citation></ref>
      </ref-list></back></article>""".encode()


def _crossref_evidence(source_hash: str, reference_hash: str) -> dict[str, object]:
    return {
        "version": "esa-crossrefs-1.0",
        "corpus_id": "esa-fixture",
        "source_idml_sha256": source_hash,
        "approved_xml_sha256": reference_hash,
        "runtime_uses_approved_xml": False,
        "generated_xml_valid": True,
        "target_deltas": {
            "expected_deficits": [{"reference_ordinal": 1, "occurrences": 1}],
            "actual_surpluses": [{"reference_ordinal": 2, "occurrences": 1}],
        },
        "technical_adjudication_candidates": [{"code": "target-conflict"}, {"code": "audit"}],
    }


def test_source_authority_qualifies_only_exact_audited_differences() -> None:
    source_hash = "a" * 64
    reference = _article("Journal without accent", "Titlewithout space", "ref1")
    candidate = _article("Journal with accent", "Title with space", "ref2")
    semantic = XmlSemanticComparator().compare(reference, candidate)
    evidence = _crossref_evidence(source_hash, hashlib.sha256(reference).hexdigest())
    qualification, public = build_source_authority_qualification(
        report=semantic,
        corpus_id="esa-fixture",
        journal_profile_id="esa-aop-1.0.0",
        source_idml_sha256=source_hash,
        journal_title="Journal with accent",
        primary_article_title="Title with space",
        crossref_evidence=evidence,
        crossref_evidence_sha256="b" * 64,
    )

    reconciled, counts = qualification.apply(semantic, source_idml_sha256=source_hash)

    assert reconciled.passed is True
    assert reconciled.blocking_findings == 0
    assert reconciled.cross_references.decision == "source_qualified"
    assert counts == {"metadata_differences": 2, "bibliographic_occurrences": 1}
    assert public["restricted_content_emitted"] is False


def test_source_authority_fails_closed_when_comparison_changes() -> None:
    source_hash = "a" * 64
    reference = _article("Journal without accent", "Titlewithout space", "ref1")
    candidate = _article("Journal with accent", "Title with space", "ref2")
    semantic = XmlSemanticComparator().compare(reference, candidate)
    qualification, _ = build_source_authority_qualification(
        report=semantic,
        corpus_id="esa-fixture",
        journal_profile_id="esa-aop-1.0.0",
        source_idml_sha256=source_hash,
        journal_title="Journal with accent",
        primary_article_title="Title with space",
        crossref_evidence=_crossref_evidence(
            source_hash,
            hashlib.sha256(reference).hexdigest(),
        ),
        crossref_evidence_sha256="b" * 64,
    )
    changed = XmlSemanticComparator().compare(
        reference,
        _article("Another journal", "Title with space", "ref2"),
    )

    with pytest.raises(ValueError, match="metadata differences changed"):
        qualification.apply(changed, source_idml_sha256=source_hash)
