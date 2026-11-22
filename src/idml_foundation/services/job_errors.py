"""Operator-safe classification of permanent job failures.

Only messages authored by this project are mapped. Anything else (library errors,
filesystem paths, article content) collapses to ``unclassified`` so that job
results never leak server paths or source text.
"""

import re
from typing import Final

_SUBJECT: Final = r"(?P<subject>[^/\\\x00-\x1f]{1,255})"

_PATTERNS: Final[tuple[tuple[re.Pattern[str], str], ...]] = (
    (re.compile(rf"missing package asset: {_SUBJECT}"), "missing_package_asset"),
    (re.compile(rf"ambiguous package figure asset: {_SUBJECT}"), "ambiguous_package_asset"),
    (
        re.compile(r"package contains assets not referenced by the XML"),
        "unreferenced_package_asset",
    ),
    (re.compile(r"asset source names must be unique"), "duplicate_asset_name"),
    (re.compile(r"canonical snapshot does not produce valid XML"), "invalid_canonical_xml"),
    (re.compile(r"packaged figure differs from supplied artifact"), "figure_mismatch"),
    (re.compile(r"supplied figure conflicts with canonical hash"), "figure_conflicts_with_source"),
    (re.compile(r"resource not found in organization"), "resource_not_found"),
    (re.compile(r"(?P<subject>[a-z_]{1,40}) not found in organization"), "input_not_found"),
    (re.compile(r"asset artifact not found in organization"), "asset_not_found"),
    (re.compile(r"canonical snapshot not found in organization"), "revision_not_found"),
    (re.compile(r"snapshot is not canonical"), "revision_not_canonical"),
    (
        re.compile(r"snapshot does not belong to the selected source artifact"),
        "revision_source_mismatch",
    ),
    (re.compile(r"idml_artifact_id is not an IDML artifact"), "not_an_idml"),
    (re.compile(r"pdf_artifact_id is not a PDF artifact"), "not_a_pdf"),
    (re.compile(r"asset_artifact_ids is invalid"), "invalid_asset_list"),
    (re.compile(r"snapshot journal profile differs from configured profile"), "profile_mismatch"),
    (re.compile(r"enrichment_bundle_changed_during_conversion"), "enrichment_changed"),
    (re.compile(r"invalid (?P<subject>[a-z_]{1,40})"), "invalid_field"),
)


def operator_error_detail(exc: BaseException) -> dict[str, str]:
    """Return ``{"reason": code[, "subject": name]}`` safe to show to the operator."""
    if isinstance(exc, FileNotFoundError):
        return {"reason": "input_file_unavailable"}
    message = str(exc).strip()
    for pattern, reason in _PATTERNS:
        match = pattern.fullmatch(message)
        if match is None:
            continue
        subject = match.groupdict().get("subject")
        return {"reason": reason, "subject": subject} if subject else {"reason": reason}
    return {"reason": "unclassified"}
