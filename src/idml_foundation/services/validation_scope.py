"""Server-derived validation scope, shared with the Python 3.10 Linux broker."""

import hashlib
import json
import re
from uuid import UUID

FIELDS = {
    "organization_id",
    "resource_id",
    "source_idml_sha256",
    "journal_profile_id",
    "xml_sha256",
    "package_sha256",
}


def validate_scope(scope: dict[str, str]) -> dict[str, str]:
    if not isinstance(scope, dict) or set(scope) != FIELDS:
        raise ValueError("validation_scope_invalid")
    if any(not isinstance(value, str) for value in scope.values()):
        raise ValueError("validation_scope_invalid")
    for field in ("organization_id", "resource_id"):
        if str(UUID(scope[field])) != scope[field]:
            raise ValueError("validation_scope_invalid")
    for field in ("source_idml_sha256", "xml_sha256", "package_sha256"):
        if not re.fullmatch("[0-9a-f]{64}", scope[field]):
            raise ValueError("validation_scope_invalid")
    if scope["journal_profile_id"] != "esa-aop-1.1.0":
        raise ValueError("validation_profile_not_qualified")
    return dict(scope)


def scope_digest(scope: dict[str, str]) -> str:
    return hashlib.sha256(
        json.dumps(validate_scope(scope), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
