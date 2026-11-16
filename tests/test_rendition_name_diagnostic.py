import pytest

from ops.rendition_name_diagnostic import classify_rendition_name


@pytest.mark.parametrize(
    "names,expected,result",
    [
        (["a.xml", "a.pdf"], "a_00001.pdf", "validator-derived-name-conflict"),
        (["a.xml"], "a.pdf", "required-pdf-unavailable"),
        (["a.xml", "b.pdf"], "a.pdf", "required-pdf-unavailable"),
        (["a.xml", "a.pdf"], "a.pdf", "validator-expected-file-present"),
        (["a.xml", "a.pdf", "a_00001.pdf"], "a_00001.pdf", "ambiguous-pdf-candidates"),
        (["a.xml", "a.pdf", "a.pdf"], "a.pdf", "ambiguous-package-members"),
        (["a.xml", "../a.pdf"], "a.pdf", "unsupported-package-layout"),
        (["a.pdf"], "a.pdf", "xml-unavailable"),
    ],
)
def test_filename_triage(names, expected, result):
    assert (
        classify_rendition_name(xml_name="a.xml", actual_names=names, validator_expected=expected)
        == result
    )


def test_main_pdf_does_not_satisfy_translation():
    assert (
        classify_rendition_name(
            xml_name="a.xml",
            actual_names=["a.xml", "a.pdf"],
            validator_expected="a-en.pdf",
            language="en",
            main=False,
        )
        == "required-pdf-unavailable"
    )


def test_translation_requires_known_language():
    assert (
        classify_rendition_name(
            xml_name="a.xml",
            actual_names=["a.xml", "a.pdf"],
            validator_expected="a.pdf",
            main=False,
        )
        == "translation-language-unresolved"
    )
