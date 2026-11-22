"""Operator-safe reasons for modern validator transport failures.

Validator diagnostics may contain article text or environment details, so only fixed,
project-authored codes are surfaced; everything else becomes 'unclassified'.
"""

import re
from typing import Final

_KNOWN: Final = frozenset(
    {
        "external evidence mismatch",
        "untrusted validator broker",
        "validator output budget",
        "validator transport requires Linux peer credentials",
        "scoped_validation_candidate_mismatch",
        "scoped_validation_evidence_missing",
        "scoped_validation_evidence_invalid",
        "scoped_validation_binding_invalid",
        "scoped_validation_checks_invalid",
        "scoped_validation_checks_incomplete",
        "validation_scope_invalid",
        "validation_profile_not_qualified",
    }
)


def validator_failure_reason(exc: BaseException) -> str:
    """Short code for why a validator run is unavailable (no paths, no article content)."""
    if isinstance(exc, FileNotFoundError):
        return "broker-socket-missing"
    if isinstance(exc, ConnectionRefusedError):
        return "broker-not-listening"
    if isinstance(exc, TimeoutError):
        return "broker-timeout"
    if isinstance(exc, PermissionError):
        return "broker-permission-denied"
    if isinstance(exc, ConnectionError | BrokenPipeError):
        return "broker-connection-closed"
    if isinstance(exc, KeyError):
        return "broker-error-envelope"
    message = str(exc).strip()
    if message in _KNOWN:
        return re.sub(r"[^a-z0-9]+", "-", message.casefold()).strip("-")
    return "unclassified"
