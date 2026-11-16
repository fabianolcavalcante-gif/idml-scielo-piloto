import pytest

from idml_foundation.mathml import (
    MATHML_NS,
    canonical_mathml,
    mathml_semantically_equivalent,
    parse_mathml_fragment,
)

VALID = (
    f'<mml:math xmlns:mml="{MATHML_NS}"><mml:mrow><mml:mi>x</mml:mi>'
    "<mml:mo>=</mml:mo><mml:mn>1</mml:mn></mml:mrow></mml:math>"
)


def test_mathml_fragment_is_canonicalized_with_required_display() -> None:
    assert 'display="block"' in canonical_mathml(VALID, display=True)
    assert parse_mathml_fragment(VALID, display=False).get("display") == "inline"


def test_mathml_semantic_comparison_ignores_only_redundant_mrow() -> None:
    wrapped = VALID.replace("<mml:mrow>", "<mml:mrow><mml:mrow>").replace(
        "</mml:mrow></mml:math>", "</mml:mrow></mml:mrow></mml:math>"
    )
    assert mathml_semantically_equivalent(VALID, wrapped, display=True)
    changed = VALID.replace("<mml:mn>1</mml:mn>", "<mml:mn>2</mml:mn>")
    assert not mathml_semantically_equivalent(VALID, changed, display=True)


def test_mathml_semantic_comparison_normalizes_visible_parentheses_and_minus() -> None:
    fenced = (
        f'<mml:math xmlns:mml="{MATHML_NS}" display="block"><mml:mrow>'
        '<mml:mfenced open="(" close=")"><mml:mrow><mml:mi>x</mml:mi>'
        "<mml:mo>\N{MINUS SIGN}</mml:mo><mml:mi>y</mml:mi></mml:mrow></mml:mfenced>"
        "</mml:mrow></mml:math>"
    )
    explicit = (
        f'<mml:math xmlns:mml="{MATHML_NS}" display="block"><mml:mrow>'
        "<mml:mo>(</mml:mo><mml:mi>x</mml:mi><mml:mo>-</mml:mo>"
        "<mml:mi>y</mml:mi><mml:mo>)</mml:mo></mml:mrow></mml:math>"
    )
    assert mathml_semantically_equivalent(fenced, explicit, display=True)


def test_mathml_semantic_comparison_flattens_nested_sequence_around_parentheses() -> None:
    fenced = (
        f'<mml:math xmlns:mml="{MATHML_NS}" display="block"><mml:mrow>'
        "<mml:mi>z</mml:mi><mml:mo>=</mml:mo>"
        "<mml:mfenced><mml:mrow><mml:mi>x</mml:mi><mml:mo>-</mml:mo>"
        "<mml:mi>y</mml:mi></mml:mrow></mml:mfenced></mml:mrow></mml:math>"
    )
    explicit_nested = (
        f'<mml:math xmlns:mml="{MATHML_NS}" display="block"><mml:mrow>'
        "<mml:mi>z</mml:mi><mml:mo>=</mml:mo><mml:mrow><mml:mo>(</mml:mo>"
        "<mml:mi>x</mml:mi><mml:mo>\N{MINUS SIGN}</mml:mo><mml:mi>y</mml:mi>"
        "<mml:mo>)</mml:mo></mml:mrow></mml:mrow></mml:math>"
    )

    assert mathml_semantically_equivalent(fenced, explicit_nested, display=True)


def test_mathml_semantic_comparison_normalizes_visual_tokenization_and_prime_scripts() -> None:
    compact = (
        f'<mml:math xmlns:mml="{MATHML_NS}" display="block"><mml:mrow>'
        "<mml:mi>SOTR</mml:mi><mml:mo>\N{DOT OPERATOR}</mml:mo>"
        "<mml:msup><mml:msub><mml:mi>C</mml:mi><mml:mi>s</mml:mi></mml:msub>"
        "<mml:mo>\N{PRIME}</mml:mo></mml:msup></mml:mrow></mml:math>"
    )
    expanded = (
        f'<mml:math xmlns:mml="{MATHML_NS}" display="block"><mml:mrow>'
        "<mml:mi>S</mml:mi><mml:mi>O</mml:mi><mml:mi>T</mml:mi><mml:mi>R</mml:mi>"
        "<mml:mo>.</mml:mo><mml:mtext>\N{THIN SPACE}</mml:mtext>"
        "<mml:msubsup><mml:mi>C</mml:mi><mml:mi>s</mml:mi>"
        "<mml:mo>\N{PRIME}</mml:mo></mml:msubsup></mml:mrow></mml:math>"
    )

    assert mathml_semantically_equivalent(compact, expanded, display=True)
    assert not mathml_semantically_equivalent(
        compact.replace("SOTR", "sOTR"), expanded, display=True
    )


@pytest.mark.parametrize(
    "fragment,error",
    [
        ("<math><mi>x</mi></math>", "mml:math"),
        (
            f'<mml:math xmlns:mml="{MATHML_NS}" display="inline"><mml:mi>x</mml:mi></mml:math>',
            "display must be block",
        ),
        (
            f'<mml:math xmlns:mml="{MATHML_NS}"><script>alert(1)</script></mml:math>',
            "unsupported element",
        ),
        (
            f'<mml:math xmlns:mml="{MATHML_NS}"><mml:mi href="https://example.test">x</mml:mi></mml:math>',
            "unsafe attribute",
        ),
        (
            f'<mml:math xmlns:mml="{MATHML_NS}"><mml:mi>C</mml:mi>'
            "<mml:msub><mml:mi>s</mml:mi></mml:msub></mml:math>",
            "msub must contain exactly 2 child elements",
        ),
        (
            '<!DOCTYPE math [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
            f'<mml:math xmlns:mml="{MATHML_NS}"><mml:mi>&xxe;</mml:mi></mml:math>',
            "must not contain DTD",
        ),
    ],
)
def test_mathml_fragment_rejects_unsafe_or_incompatible_content(
    fragment: str,
    error: str,
) -> None:
    with pytest.raises(ValueError, match=error):
        parse_mathml_fragment(fragment, display=True)
