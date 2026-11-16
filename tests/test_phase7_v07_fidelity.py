from __future__ import annotations

import json

import pytest
from lxml import etree

from idml_foundation.release.semantic_fidelity import (
    SemanticChangeKind,
    XmlSemanticComparator,
    extract_semantic_fields,
)


def _article(*paragraphs: str, title: str = "Reliable XML conversion") -> bytes:
    body = "".join(f"<p>{paragraph}</p>" for paragraph in paragraphs)
    return f"""<article>
      <front>
        <journal-meta><journal-title-group><journal-title>ESA</journal-title>
        </journal-title-group></journal-meta>
        <article-meta>
          <article-id pub-id-type="doi">10.1000/example</article-id>
          <title-group><article-title>{title}</article-title></title-group>
          <contrib-group><contrib contrib-type="author"><name>
            <surname>Silva</surname><given-names>Ana</given-names>
          </name></contrib></contrib-group>
          <aff id="aff1"><institution content-type="original">Institute Alpha</institution>
          </aff>
        </article-meta>
      </front>
      <body>
        <sec><title>Introduction</title>{body}
          <fig id="fig1"><label>Figure 1</label><caption><p>Flow diagram</p></caption>
            <graphic href="figure.jpg"/></fig>
          <table-wrap id="tbl1"><label>Table 1</label><caption><p>Measurements</p></caption>
            <table><tbody><tr><td>Alpha</td><td>Beta</td></tr></tbody></table>
          </table-wrap>
          <disp-formula id="eq1"><label>(1)</label><tex-math>E = mc^2</tex-math>
          </disp-formula>
          <p>See <xref ref-type="bibr" rid="ref1">reference</xref>.</p>
        </sec>
      </body>
      <back><ref-list><ref id="ref1"><mixed-citation>Silva A. Source title. 2024.
      </mixed-citation></ref></ref-list><fn-group><fn><p>Funding note</p></fn></fn-group></back>
    </article>""".encode()


def _domain(report: object, name: str) -> object:
    return next(item for item in report.domains if item.domain == name)  # type: ignore[attr-defined]


def test_identical_xml_passes_without_emitting_article_content() -> None:
    secret = "sensitive source phrase for privacy regression"
    payload = _article(secret)

    report = XmlSemanticComparator().compare(payload, payload)

    assert report.passed is True
    assert report.blocking_findings == 0
    assert report.findings == ()
    assert report.cross_references.decision == "pass"
    serialized = json.dumps(report.model_dump(mode="json"))
    assert secret not in serialized
    assert report.content_emitted is False


def test_whitespace_only_change_is_nonblocking_normalization() -> None:
    reference = _article("Whitespace   is preserved in the reference")
    candidate = _article("Whitespace is preserved in the reference")

    report = XmlSemanticComparator().compare(reference, candidate)

    assert report.passed is True
    assert report.blocking_findings == 0
    assert {finding.kind for finding in report.findings} == {SemanticChangeKind.NORMALIZATION}
    assert _domain(report, "body").normalized == 1  # type: ignore[attr-defined]


def test_editorial_punctuation_in_reference_is_nonblocking_normalization() -> None:
    reference = _article("Stable body").replace(b"Source title. 2024.", b"Source title, 2024")
    candidate = _article("Stable body")

    report = XmlSemanticComparator().compare(reference, candidate)

    assert report.passed is True
    reference_score = _domain(report, "references")
    assert reference_score.normalized == 1  # type: ignore[attr-defined]
    assert reference_score.altered == 0  # type: ignore[attr-defined]


def test_equivalent_structured_conflict_and_funding_notes_compare_equal() -> None:
    original_note = b"<fn-group><fn><p>Funding note</p></fn></fn-group>"
    reference = _article("Stable body").replace(
        original_note,
        b"<fn-group>"
        b"<fn><p>Conflicts of interest: None declared.</p></fn>"
        b"<fn><p>Funding: Foundation Alpha.</p></fn>"
        b"</fn-group>",
    )
    candidate = (
        _article("Stable body")
        .replace(
            b"</article-meta>",
            b"<funding-group><funding-statement>Foundation Alpha.</funding-statement>"
            b"</funding-group></article-meta>",
        )
        .replace(
            original_note,
            b"<sec><title>Conflicts of interest</title><p>None declared.</p></sec>",
        )
    )

    report = XmlSemanticComparator().compare(reference, candidate)

    notes = _domain(report, "notes")
    assert notes.passed is True  # type: ignore[attr-defined]
    assert notes.exact == 2  # type: ignore[attr-defined]


def test_inline_table_markup_does_not_create_semantic_whitespace() -> None:
    reference = _article("Stable body").replace(
        b"<td>Alpha</td>",
        b"<td>kgO<sub>2</sub>/h</td>",
    )
    candidate = _article("Stable body").replace(
        b"<td>Alpha</td>",
        b"<td>kgO2/h</td>",
    )

    report = XmlSemanticComparator().compare(reference, candidate)

    tables = _domain(report, "tables")
    assert tables.passed is True  # type: ignore[attr-defined]
    assert tables.exact == 1  # type: ignore[attr-defined]


def test_formula_content_is_not_double_counted_as_body_text() -> None:
    reference = _article("Rate measured").replace(
        b"Rate measured",
        b"Rate <inline-formula><tex-math>x</tex-math></inline-formula> measured",
    )
    candidate = _article("Rate measured")

    report = XmlSemanticComparator().compare(reference, candidate)

    body = _domain(report, "body")
    formulas = _domain(report, "formulas")
    assert body.passed is True  # type: ignore[attr-defined]
    assert formulas.omissions == 1  # type: ignore[attr-defined]


def test_inline_markup_punctuation_is_a_body_normalization_not_displacement() -> None:
    reference = _article("See Silva <italic>et al</italic>., 2024.")
    candidate = _article("See Silva et al., 2024.")

    report = XmlSemanticComparator().compare(reference, candidate)

    body = _domain(report, "body")
    assert body.passed is True  # type: ignore[attr-defined]
    assert body.normalized == 1  # type: ignore[attr-defined]
    assert body.displacements == 0  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("reference_paragraphs", "candidate_paragraphs", "expected_kind"),
    [
        (
            ("First source statement with unique evidence.",),
            (),
            SemanticChangeKind.OMISSION,
        ),
        (
            (),
            ("Entirely invented statement without source support.",),
            SemanticChangeKind.INVENTION,
        ),
        (
            ("A stable paragraph contains the original result.",),
            ("A stable paragraph contains the revised result.",),
            SemanticChangeKind.ALTERATION,
        ),
        (
            ("A paragraph that must occur exactly once.",),
            (
                "A paragraph that must occur exactly once.",
                "A paragraph that must occur exactly once.",
            ),
            SemanticChangeKind.DUPLICATION,
        ),
        (
            (
                "Alpha paragraph reports the first distinct outcome.",
                "Beta paragraph reports the second distinct outcome.",
            ),
            (
                "Beta paragraph reports the second distinct outcome.",
                "Alpha paragraph reports the first distinct outcome.",
            ),
            SemanticChangeKind.DISPLACEMENT,
        ),
    ],
)
def test_semantic_mutations_are_detected(
    reference_paragraphs: tuple[str, ...],
    candidate_paragraphs: tuple[str, ...],
    expected_kind: SemanticChangeKind,
) -> None:
    report = XmlSemanticComparator().compare(
        _article(*reference_paragraphs),
        _article(*candidate_paragraphs),
    )

    assert report.passed is False
    assert expected_kind in {finding.kind for finding in report.findings}
    assert report.blocking_findings >= 1


def test_cross_reference_drift_blocks_report_even_when_text_is_equal() -> None:
    reference = _article("A cited finding")
    candidate = reference.replace(b'rid="ref1"', b'rid="ref2"').replace(b'id="ref1"', b'id="ref2"')
    candidate = candidate.replace(b"<ref-list>", b'<ref-list><ref id="ref1"/>')

    report = XmlSemanticComparator().compare(reference, candidate)

    assert report.passed is False
    assert report.cross_references.decision == "needs_review"


@pytest.mark.parametrize("threshold", [0.0, -0.1, 1.1])
def test_invalid_alignment_threshold_is_rejected(threshold: float) -> None:
    with pytest.raises(ValueError, match="alignment_threshold"):
        XmlSemanticComparator().compare(_article("A"), _article("A"), alignment_threshold=threshold)


@pytest.mark.parametrize("payload", [b"", b"<article>"])
def test_empty_or_malformed_xml_is_rejected(payload: bytes) -> None:
    with pytest.raises((ValueError, etree.XMLSyntaxError)):
        XmlSemanticComparator().compare(payload, _article("Valid"))


def test_semantic_extraction_separates_content_domains() -> None:
    root = etree.fromstring(_article("Primary body content"))

    domains = extract_semantic_fields(root)

    assert tuple(domains) == (
        "metadata",
        "authors",
        "affiliations",
        "structure",
        "body",
        "references",
        "figures",
        "tables",
        "formulas",
        "formula_content",
        "notes",
        "media",
    )
    assert len(domains["body"]) == 2
    assert all(
        field.sha256 and field.token_count >= 1 for fields in domains.values() for field in fields
    )
