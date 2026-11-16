"""v1.1 client: scope comes from worker database records, never upload/job JSON."""

import hashlib
import json
import socket
import struct
from pathlib import Path
from typing import Any

from idml_foundation.release.validation_engine import (
    ValidationEngine,
    ValidatorCommand,
    ValidatorRun,
)
from idml_foundation.services.validation_scope import scope_digest, validate_scope
from idml_foundation.services.validator_transport import MAX_INPUT, receive


def check_evidence(value: Any, scope: dict[str, str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"version", "binding", "checks", "expected"}:
        raise ValueError("scoped_validation_evidence_missing")
    if value["version"] != "scoped-authority-evidence-1.0":
        raise ValueError("scoped_validation_evidence_invalid")
    binding = value["binding"]
    if not isinstance(binding, dict) or set(binding) != {
        "scope_sha256",
        "bundle_sha256",
        "grant_sha256",
    }:
        raise ValueError("scoped_validation_binding_invalid")
    if binding["scope_sha256"] != scope_digest(scope):
        raise ValueError("scoped_validation_binding_invalid")
    import re

    if any(
        not isinstance(sha, str) or not re.fullmatch("[0-9a-f]{64}", sha)
        for sha in binding.values()
    ):
        raise ValueError("scoped_validation_binding_invalid")
    expected, checks = value["expected"], value["checks"]
    if (
        not isinstance(expected, dict)
        or set(expected) != {"doi", "issue", "section", "orcid"}
        or not isinstance(checks, dict)
        or set(checks) != {*expected, "orcid_reasons"}
        or expected["doi"] != 1
        or expected["issue"] != 1
    ):
        raise ValueError("scoped_validation_checks_invalid")
    for key, count in expected.items():
        if (
            type(count) is not int
            or not 0 <= count <= 64
            or not isinstance(checks[key], list)
            or len(checks[key]) != count
            or any(type(ok) is not bool for ok in checks[key])
        ):
            raise ValueError("scoped_validation_checks_incomplete")
    reasons = checks["orcid_reasons"]
    allowed = {
        "public_record_and_name_match",
        "public_registry_and_crossref_author_match",
        "name_not_confirmed",
        "public_name_unavailable",
        "unavailable",
        "identifier_out_of_scope_or_invalid",
    }
    if (
        not isinstance(reasons, list)
        or len(reasons) != expected["orcid"]
        or any(reason not in allowed for reason in reasons)
    ):
        raise ValueError("scoped_validation_checks_invalid")
    # False comparisons remain native findings, not a transport failure.
    return value


class ScopedValidatorExecutor:
    def __init__(self, socket_path: Path, *, scope: dict[str, str]) -> None:
        self.socket_path = socket_path
        self.scope = validate_scope(scope)
        self.evidence: dict[str, dict[str, Any]] = {}

    def __call__(self, candidate: bytes, specification: ValidatorCommand) -> ValidatorRun:
        self.evidence.pop(specification.name, None)
        expected = self.scope[
            "xml_sha256" if specification.input_suffix == ".xml" else "package_sha256"
        ]
        if not 0 < len(candidate) <= MAX_INPUT or hashlib.sha256(candidate).hexdigest() != expected:
            raise ValueError("scoped_validation_candidate_mismatch")
        request = json.dumps(
            {
                "version": "local-validator-1.1",
                "scope": self.scope,
                "name": specification.name,
                "candidate_sha256": expected,
                "size": len(candidate),
                "tool_sha256": specification.tool_sha256,
                "validator_version": specification.version,
                "profile_id": specification.profile_id,
            },
            sort_keys=True,
        ).encode()
        peer_option = getattr(socket, "SO_PEERCRED", None)
        if not hasattr(socket, "AF_UNIX") or peer_option is None:
            raise ValueError("validator transport requires Linux peer credentials")
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            # Allow the supervisor's bounded consent checks and fresh source collection.
            connection.settimeout(specification.timeout_seconds + 120)
            connection.connect(str(self.socket_path))
            credentials = connection.getsockopt(socket.SOL_SOCKET, peer_option, 12)
            if struct.unpack("3i", credentials)[1] != 0:
                raise ValueError("untrusted validator broker")
            connection.sendall(struct.pack("!I", len(request)) + request + candidate)
            length = struct.unpack("!I", receive(connection, 4))[0]
            if not 0 < length <= specification.max_output_bytes:
                raise ValueError("validator output budget")
            raw = receive(connection, length)
        envelope = json.loads(raw)
        evidence = check_evidence(envelope["result"].get("authority_evidence"), self.scope)
        run = ValidationEngine().ingest(candidate, specification, raw)
        if run.sanitized_output_sha256:
            self.evidence[specification.name] = evidence
        return run
