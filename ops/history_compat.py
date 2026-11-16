"""SPS 1.10 history compatibility: only revision presence, never dates or severity.

The official specification linked by the pinned native module requires received
and accepted. It lists revisions as possible events, not universally mandatory.
Default and effective native checks both run; the XML is never edited here.
"""

import copy
import hashlib
import json
from contextlib import contextmanager

POLICY = "sps-1.10-history-presence-1.0"
SPEC_URL = (
    "https://docs.google.com/document/d/"
    "1GTv4Inc2LS_AXY-ToHT3HmO66UT0VAHWJNOIqzBNSgA/edit#heading=h.history"
)
SPEC_SHA256 = "09ade688acbf1aa6c48324b660bf4baeb9293c92ff315a2d68c371251909bbef"
SECTION_SHA256 = "111b37673931946a14ae021c1c646afa8422fa582b31e17026c02a48cf0b675e"
NATIVE_CONFIG_SHA256 = "a6a62e10d817310f922d8acbe0a99bdabdd8354f6f98e5c306ffa7593a7c4f5d"
REVISION_TYPES = frozenset({"rev-request", "rev-recd"})
EXPECTED_RULES = {
    "error_level": "CRITICAL",
    "date_list": [
        {"type": name, "required": required}
        for name, required in (
            ("preprint", False),
            ("received", True),
            ("resubmitted", False),
            ("rev-request", True),
            ("rev-recd", True),
            ("accepted", True),
            ("pub", True),
            ("corrected", False),
            ("retracted", False),
        )
    ],
}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def verify_native_config(raw):
    if hashlib.sha256(raw).hexdigest() != NATIVE_CONFIG_SHA256 or json.loads(raw) != {
        "history_dates_rules": EXPECTED_RULES
    }:
        raise ValueError("history_native_configuration_changed")


def effective_parameters(params):
    # Exact shape/types as well as values: True must not be interchangeable with 1.
    if json.dumps(params.get("history_dates_rules"), sort_keys=True) != json.dumps(
        EXPECTED_RULES, sort_keys=True
    ):
        raise ValueError("history_unqualified_parameters")
    updated = copy.deepcopy(params)
    for item in updated["history_dates_rules"]["date_list"]:
        if item["type"] in REVISION_TYPES:
            item["required"] = False
    return updated


def _failures(rows):
    # Deliberately NOT validator findings: no response/message/severity keys.
    # Consumers must not treat the diagnostic default pass as an effective pass.
    return [
        {"rule": row.get("title"), "outcome": row.get("response")}
        for row in rows
        if row.get("response") not in {"OK", "INFO", "WARNING", "not-applicable"}
    ]


@contextmanager
def history_parameters(module):
    """One synchronous candidate process; restored on success or exception."""
    original = module.validate_history
    if getattr(original, "_history_policy", None):
        raise ValueError("history_policy_already_installed")
    evidence = {
        "policy": POLICY,
        "specification_url": SPEC_URL,
        "specification_sha256": SPEC_SHA256,
        "section_sha256": SECTION_SHA256,
        "native_config_sha256": NATIVE_CONFIG_SHA256,
        "absence_is_not_proof_of_no_revision": True,
        "invocations": [],
    }

    def execute(tree, params):
        root = tree.getroot() if hasattr(tree, "getroot") else tree
        if root.get("specific-use") != "sps-1.10" or root.get("dtd-version") != "1.3":
            raise ValueError("history_unqualified_profile")
        updated = effective_parameters(params)
        default = list(original(tree, copy.deepcopy(params)))
        effective = list(original(tree, updated))
        # Only two *presence* rules may disappear. Every remaining native row
        # (including bad revision dates) must be byte-equivalent as JSON.
        retained = [
            row
            for row in default
            if not (
                row.get("title") in {"required date: " + t for t in REVISION_TYPES}
                and row.get("item") == "history"
                and row.get("validation_type") == "exist"
            )
        ]
        if digest(retained) != digest(effective):
            raise ValueError("history_unexpected_native_delta")
        evidence["invocations"].append(
            {
                "default_rows_sha256": digest(default),
                "effective_rows_sha256": digest(effective),
                "default_failures": _failures(default),
                "effective_failures": _failures(effective),
                "only_revision_presence_changed": True,
            }
        )
        yield from effective

    execute._history_policy = POLICY
    module.validate_history = execute
    try:
        yield evidence
    finally:
        module.validate_history = original
