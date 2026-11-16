"""Conservative filename-only triage; never a replacement for formal validation."""

from pathlib import PurePosixPath


def classify_rendition_name(
    *, xml_name, actual_names, validator_expected, language=None, main=True
):
    names = list(actual_names)
    if len(names) != len(set(names)):
        return "ambiguous-package-members"
    if any(PurePosixPath(n).name != n or "\\" in n or n in {"", ".", ".."} for n in names):
        return "unsupported-package-layout"
    if not xml_name.endswith(".xml") or xml_name not in names:
        return "xml-unavailable"
    if not main and (not language or not language.isascii() or not language.isalpha()):
        return "translation-language-unresolved"
    sibling = xml_name[:-4] + (".pdf" if main else f"-{language}.pdf")
    expected_present = validator_expected in names
    sibling_present = sibling in names
    if expected_present and sibling_present and validator_expected != sibling:
        return "ambiguous-pdf-candidates"
    if expected_present:
        return "validator-expected-file-present"
    if sibling_present:
        return "validator-derived-name-conflict"
    return "required-pdf-unavailable"
