from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "ops"))

from validator_adapter_common import sanitize_validator_result  # noqa: E402


def test_sanitizer_uses_nested_rule_metadata_without_leaking_values() -> None:
    result = sanitize_validator_result(
        {
            "rows": [
                {
                    "status": "CRITICAL",
                    "subject": "history",
                    "message": "restricted source value",
                    "data": {
                        "title": "required date: rev-request",
                        "item": "history",
                        "sub_item": "date",
                        "validation_type": "exist",
                        "got_value": "restricted source value",
                    },
                }
            ]
        }
    )

    finding = result["findings"][0]
    assert finding["code"].startswith("history-required-date-rev-request-history-date-exist-")
    assert "restricted source value" not in str(result)


def test_nested_sps_rule_identity_is_stable_across_order() -> None:
    rows = [
        {
            "status": "ERROR",
            "subject": "References",
            "data": {
                "group": "reference",
                "title": "required year",
                "validation_type": "exist",
                "got_value": "PRIVATE",
                "message": "PRIVATE",
            },
        },
        {"status": "WARNING", "subject": "Assets", "data": {"name": "PRIVATE.jpg"}},
    ]
    first = sanitize_validator_result({"rows": rows})
    second = sanitize_validator_result({"rows": list(reversed(rows))})
    assert first == second
    assert "PRIVATE" not in str(first)
    assert all(not f["code"].startswith("rule-") for f in first["findings"])


def test_nested_sps_exceptions_remain_exceptions() -> None:
    result = sanitize_validator_result(
        {
            "rows": [],
            "exceptions": [
                {"response": "exception", "group": "reference", "message": "PRIVATE traceback"}
            ],
        }
    )
    assert result["summary"] == {"exception": 1}
    assert result["findings"][0]["response"] == "exception"
    assert result["findings"][0]["code"].startswith("reference-")
    assert "PRIVATE" not in str(result)
