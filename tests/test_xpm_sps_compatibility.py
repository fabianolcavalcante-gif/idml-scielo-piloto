import json
from datetime import timedelta
from html import escape
from pathlib import Path

import pytest
from lxml import etree

from idml_foundation.release.validation_engine import UnifiedIssue, ValidatorRun
from idml_foundation.release.xpm_sps_compatibility import (
    COMBINATION_MESSAGES,
    DATE_MESSAGE,
    VALIDATORS,
    VENDOR_FILES,
    SpsCompatibilityEvidence,
    assess_xpm_sps_compatibility,
    qualified_publication_date,
)
from tests.test_xpm_compatibility import inputs as doi_inputs  # noqa: F401
from tests.test_xpm_compatibility import rebind

PUB = (
    '<pub-date publication-format="electronic" date-type="pub" '
    'iso-8601-date="2025-07-07"><day>07</day><month>07</month><year>2025</year></pub-date>'
)
COLLECTION = (
    '<pub-date publication-format="electronic" date-type="collection"><year>2025</year></pub-date>'
)
SPS_MESSAGE = (
    "For articles published on 07/07/2025, sps-1.10 is not valid. "
    "Expected SPS versions for this article: sps-1.8 or sps-1.9."
)


def native_row(label, message, snippet="", index=1, severity="blocking"):
    cls, status, code = (
        ("blockingerror", "BLOCKING ERROR", "B")
        if severity == "blocking"
        else ("error", "ERROR", "E")
    )
    return (
        f'<tr class="{cls}"><td class="td_label">{label} <a>[?]</a></td>'
        f'<td class="td_status">[{status}] [{code}{index}]</td>'
        f'<td class="td_message">{escape(message)}</td>'
        f'<td class="td_xml">{escape(snippet)}</td></tr>'
    )


def bind_modern(data):
    scope = data["expected_scope"]
    data["sps_evidence"] = SpsCompatibilityEvidence(
        contract_version="xpm-sps-compatibility-evidence-1.0",
        scope=scope,
        vendor_sha256=VENDOR_FILES,
        independent_report_sha256="b" * 64,
        runs=tuple(
            ValidatorRun(
                name=name,
                version=spec[0],
                tool_sha256=spec[1],
                candidate_sha256=scope[spec[2]],
                status="completed",
                profile_id="sps-1.10/jats-1.3",
                adapter_contract="1.1.0",
                environment="synthetic-no-native-execution",
                sanitized_output_sha256="b" * 64,
            )
            for name, spec in VALIDATORS.items()
        ),
    )


@pytest.fixture
def data(doi_inputs):  # noqa: F811 - imported pytest fixture
    data = doi_inputs
    data["xml"] = data["xml"].replace(
        b"</article-meta>", (PUB + COLLECTION + "<volume>30</volume></article-meta>").encode()
    )
    rows = (
        native_row("article/@specific-use", SPS_MESSAGE, index=4, severity="error")
        + native_row("pub-date", DATE_MESSAGE, PUB)
        + native_row("pub-date", DATE_MESSAGE, COLLECTION, index=2)
        + native_row("pub-date", sorted(COMBINATION_MESSAGES)[0], index=3)
    )
    data["report"] = (
        data["report"]
        .replace(b"</table>", rows.encode() + b"</table>")
        .replace(b"blocking errors: 1", b"blocking errors: 4")
        .replace(b"Total of errors: 3", b"Total of errors: 4")
    )
    rebind(data)
    bind_modern(data)
    return data


def test_exact_sps_dates_derive_four_exceptions_without_approval(data):
    result = assess_xpm_sps_compatibility(**data)
    assert len(result.exceptions) == 4 and len(result.base.exceptions) == 2
    assert result.base.original.blocking_errors == 4 and result.base.original.errors == 4
    assert result.unresolved_counts == dict(blocking_errors=1, fatal_errors=1, errors=1, warnings=1)
    assert not result.base.original.passed and not result.release_approved
    assert not result.homologation_ready and "doctype-jats-decision-pending" in result.reasons


@pytest.mark.parametrize(
    "old,new",
    [
        ("<day>07</day>", ""),
        ("<month>07</month>", "<month>13</month>"),
        ("<day>07</day>", "<day>32</day>"),
        ("<month>07</month>", "<month>02</month>"),
        ('date-type="pub"', 'date-type="other"'),
        ('date-type="pub"', 'date-type="pub" pub-type="epub"'),
        ('publication-format="electronic"', 'publication-format="print"'),
        ("2025-07-07", "2025-07-08"),
        (COLLECTION, COLLECTION.replace("2025", "2024")),
        (COLLECTION, COLLECTION.replace("<year>", "<day>01</day><year>")),
        (PUB, PUB + PUB),
        (COLLECTION, ""),
        ("<volume>30</volume>", "<issue>ahead</issue>"),
        ("<day>07</day>", "<day><bold>07</bold></day>"),
    ],
)
def test_real_date_errors_never_receive_sps_exception(data, old, new):
    data["xml"] = data["xml"].replace(old.encode(), new.encode())
    rebind(data)
    bind_modern(data)
    result = assess_xpm_sps_compatibility(**data)
    assert not result.exceptions
    assert result.unresolved_counts["blocking_errors"] == 4


def test_future_date_fails_even_with_successful_independent_evidence(data):
    data["now"] = data["now"].replace(year=2025, month=7, day=6)
    data["trusted"] = data["trusted"].model_copy(update={"crossref_retrieved_at": data["now"]})
    assert not assess_xpm_sps_compatibility(**data).exceptions


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate",
        "missing",
        "wrong_snippet",
        "wrong_message",
        "wrong_status",
        "hidden",
        "doctype_snippet",
    ],
)
def test_ambiguous_or_unknown_date_rows_fail_closed(data, mutation):
    row = native_row("pub-date", DATE_MESSAGE, PUB).encode()
    replacement = {
        "duplicate": row * 2,
        "missing": b"",
        "wrong_snippet": row.replace(b"2025-07-07", b"2025-07-08"),
        "wrong_message": row.replace(b"is invalid", b"is MISSING"),
        "wrong_status": row.replace(b"[BLOCKING ERROR]", b"[FATAL ERROR]"),
        "hidden": b"<template>" + row + b"</template>",
        "doctype_snippet": row.replace(b"&lt;pub-date", b"&lt;!DOCTYPE pub-date&gt;&lt;pub-date"),
    }[mutation]
    data["report"] = data["report"].replace(row, replacement)
    rebind(data)
    result = assess_xpm_sps_compatibility(**data)
    assert all(e.original_severity != "blocking" for e in result.exceptions)
    assert result.unresolved_counts["blocking_errors"] == 4


@pytest.mark.parametrize("mutation", ["date", "message", "duplicate"])
def test_version_row_requires_unique_exact_date_and_message(data, mutation):
    row = native_row("article/@specific-use", SPS_MESSAGE, index=4, severity="error").encode()
    replacement = (
        row * 2
        if mutation == "duplicate"
        else row.replace(
            b"07/07/2025" if mutation == "date" else b"sps-1.10",
            b"08/07/2025" if mutation == "date" else b"sps-1.11",
        )
    )
    data["report"] = data["report"].replace(row, replacement)
    rebind(data)
    assert all(
        e.rule_id != "xpm-sps110-version-table-1.0"
        for e in assess_xpm_sps_compatibility(**data).exceptions
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "failed"),
        ("status", "unavailable"),
        ("failure_code", "timeout"),
        ("candidate_sha256", "c" * 64),
        ("tool_sha256", "c" * 64),
        ("version", "unknown"),
        ("profile_id", "sps-1.9"),
        ("sanitized_output_sha256", "c" * 64),
        ("adapter_contract", "unknown"),
        ("environment", None),
        ("name", "unknown"),
    ],
)
def test_missing_wrong_or_failed_independent_validation_rejected(data, field, value):
    evidence = data["sps_evidence"]
    runs = (evidence.runs[0].model_copy(update={field: value}), evidence.runs[1])
    data["sps_evidence"] = evidence.model_copy(update={"runs": runs})
    with pytest.raises(ValueError, match="independent_validation"):
        assess_xpm_sps_compatibility(**data)


@pytest.mark.parametrize("severity", ["error", "critical", "blocking"])
def test_independent_real_errors_never_waived(data, severity):
    evidence = data["sps_evidence"]
    issue = UnifiedIssue(
        validator="packtools",
        severity=severity,
        category="deterministic",
        code="date-invalid",
        message="Real date error",
    )
    runs = (evidence.runs[0].model_copy(update={"issues": (issue,)}), evidence.runs[1])
    data["sps_evidence"] = evidence.model_copy(update={"runs": runs})
    with pytest.raises(ValueError, match="independent_validation"):
        assess_xpm_sps_compatibility(**data)


@pytest.mark.parametrize(
    "field",
    [
        "organization_id",
        "resource_id",
        "source_idml_sha256",
        "journal_profile_id",
        "xml_sha256",
        "package_sha256",
    ],
)
def test_independent_scope_must_be_exact(data, field):
    evidence = data["sps_evidence"]
    data["sps_evidence"] = evidence.model_copy(update={"scope": {**evidence.scope, field: "x"}})
    with pytest.raises(ValueError):
        assess_xpm_sps_compatibility(**data)


def test_vendor_identity_and_duplicate_validator_are_rejected(data):
    evidence = data["sps_evidence"]
    for update in ({"vendor_sha256": {}}, {"runs": (evidence.runs[0], evidence.runs[0])}):
        data["sps_evidence"] = evidence.model_copy(update=update)
        with pytest.raises(ValueError):
            assess_xpm_sps_compatibility(**data)


def test_query_failure_and_warning_not_silenced(data):
    data["trusted"] = data["trusted"].model_copy(update={"required_queries_complete": False})
    result = assess_xpm_sps_compatibility(**data)
    assert "required-queries-incomplete" in result.reasons
    assert result.unresolved_counts["warnings"] == result.base.original.warnings
    assert result.unresolved_counts["fatal_errors"] == result.base.original.fatal_errors


@pytest.mark.parametrize("field", ["xml", "package", "report", "crossref"])
def test_tampered_input_rejected(data, field):
    data[field] += b"tampered"
    with pytest.raises(ValueError):
        assess_xpm_sps_compatibility(**data)


def test_stale_doi_evidence_cannot_be_reused(data):
    data["now"] += timedelta(days=8)
    with pytest.raises(ValueError):
        assess_xpm_sps_compatibility(**data)


def test_native_probe_real_errors_fail_local_date_guard(data):
    path = Path(__file__).resolve().parents[1] / (
        "benchmarks/qualification/reports/vh1-xpm-sps-dates-probe-v1.json"
    )
    probe = json.loads(path.read_bytes())
    assert probe["vendor_sha256"] == VENDOR_FILES and probe["vendor_files_unchanged"]
    assert len(probe["cases"]) == 10
    for case in probe["cases"]:
        result = qualified_publication_date(etree.fromstring(case["xml"].encode()), data["now"])
        assert bool(result) == (case["case"] in {"sps110_valid", "sps19_valid", "sps20_unknown"})
    assert probe["cases"][0]["legacy_version_number"] == 1.1


def test_unknown_sps_version_not_accepted(data):
    data["xml"] = data["xml"].replace(b"sps-1.10", b"sps-2.0")
    rebind(data)
    bind_modern(data)
    with pytest.raises(ValueError, match="unqualified_profile"):
        assess_xpm_sps_compatibility(**data)


@pytest.mark.parametrize("mutation", ["native", "wrong_color", "wrong_text", "extra_attribute"])
def test_only_exact_native_space_markers_can_be_removed(data, mutation):
    encoded = escape(PUB)
    marker = '<font color="#F56991">&#183;</font>'
    decorated = "<code><br/>" + encoded.replace(" ", " " + marker + " ") + "<br/></code>"
    if mutation == "wrong_color":
        decorated = decorated.replace("#F56991", "#000000")
    elif mutation == "wrong_text":
        decorated = decorated.replace("&#183;", "INVALID")
    elif mutation == "extra_attribute":
        decorated = decorated.replace("<font ", '<font hidden="hidden" ')
    data["report"] = data["report"].replace(encoded.encode(), decorated.encode())
    rebind(data)
    result = assess_xpm_sps_compatibility(**data)
    assert sum(e.original_severity == "blocking" for e in result.exceptions) == (
        3 if mutation == "native" else 0
    )
