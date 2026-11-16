"""Synthetic native positive/negative checks, run inside each pinned candidate image."""

import copy
import hashlib
import json
from pathlib import Path

import packtools
from history_compat import EXPECTED_RULES, history_parameters, verify_native_config
from lxml import etree
from packtools.sps.validation import xml_validations


def main():
    raw = (
        Path(packtools.__file__).parent / "sps/validation_rules/history_dates_rules.json"
    ).read_bytes()
    verify_native_config(raw)
    params = {"history_dates_rules": copy.deepcopy(EXPECTED_RULES)}

    def event(kind, parts="<day>01</day><month>02</month><year>2025</year>"):
        return f'<date date-type="{kind}">{parts}</date>'

    base = event("received") + event("accepted") + event("pub")
    cases = {
        "absent_optional_revision": (base, None),
        "present_complete_revisions": (base + event("rev-request") + event("rev-recd"), None),
        "present_year_only_revision": (base + event("rev-recd", "<year>2025</year>"), None),
        "missing_received": (base.replace(event("received"), ""), "required date: received"),
        "missing_accepted": (base.replace(event("accepted"), ""), "required date: accepted"),
        "missing_pub_still_required": (base.replace(event("pub"), ""), "required date: pub"),
        "revision_without_year": (
            base + event("rev-recd", "<month>02</month>"),
            "year presence for rev-recd",
        ),
        "request_without_year": (base + event("rev-request", ""), "year presence for rev-request"),
        "incomplete_received": (
            base.replace(event("received"), event("received", "<year>2025</year>")),
            "complete date for received",
        ),
        "unknown_type": (base + event("invented"), "date-type value"),
        "missing_type": (base + "<date><year>2025</year></date>", "date-type presence"),
        "duplicate_history": (base + "</history><history>" + base, "history uniqueness"),
    }
    results = {}
    for key, (history, expected) in cases.items():
        xml = (
            '<article specific-use="sps-1.10" dtd-version="1.3" article-type="research-article">'
            "<front><article-meta><history>"
            + history
            + "</history></article-meta></front></article>"
        ).encode()
        tree = etree.fromstring(xml)
        before = etree.tostring(tree)
        native = xml_validations.validate_history
        with history_parameters(xml_validations) as evidence:
            rows = list(xml_validations.validate_history(tree, params))
        bad = [r for r in rows if r["response"] not in {"OK", "INFO"}]
        passed = (
            (
                not bad
                if expected is None
                else any(r["title"] == expected and r["response"] == "CRITICAL" for r in bad)
            )
            and before == etree.tostring(tree)
            and params == {"history_dates_rules": EXPECTED_RULES}
            and xml_validations.validate_history is native
        )
        results[key] = {"passed": passed, "evidence": evidence}
    # Translation required-date checks must retain native per-container scope.
    translated = etree.fromstring(
        (
            '<article specific-use="sps-1.10" dtd-version="1.3" article-type="research-article">'
            "<front><article-meta><history>" + base + "</history></article-meta></front>"
            '<sub-article id="translation" article-type="translation"><front-stub><history>'
            + event("accepted")
            + event("pub")
            + "</history></front-stub></sub-article></article>"
        ).encode()
    )
    with history_parameters(xml_validations):
        rows = list(xml_validations.validate_history(translated, params))
    results["translation_missing_received"] = {
        "passed": any(
            row["title"] == "required date: received"
            and row["response"] == "CRITICAL"
            and row.get("parent_id") == "translation"
            for row in rows
        )
    }
    report = {
        "passed": all(row["passed"] for row in results.values()),
        "checks": results,
        "native_config_sha256": hashlib.sha256(raw).hexdigest(),
    }
    print(json.dumps(report, sort_keys=True))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
