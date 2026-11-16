"""Content-safe normalization shared by isolated formal-validator adapters."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import Counter
from typing import Any

from external_verification import PREFIX, unavailable_dependency

_CODE = re.compile(r"[^a-z0-9]+")
_NON_FINDINGS = {"", "info", "not-applicable", "ok", "pass", "passed", "success", "valid"}
_SEVERITY_KEYS = ("response", "status", "severity", "level")


def sanitize_validator_result(raw: object) -> dict[str, object]:
    """Keep rule identity and counts while excluding source-derived values and advice."""
    findings: list[dict[str, str]] = []
    counts: Counter[str] = Counter()
    unavailable: set[str] = set()
    for position, item in enumerate(_result_items(raw), start=1):
        response = _text(
            next((item[key] for key in _SEVERITY_KEYS if key in item), "error")
        ).casefold()
        counts[response or "unknown"] += 1
        if response in _NON_FINDINGS:
            continue
        # Only SPS wrapper rows contain nested rule metadata. Native rule data
        # can contain article titles/subjects and must not enter public codes.
        nested = (
            item["data"]
            if "status" in item
            and "validation_type" not in item
            and isinstance(item.get("data"), dict)
            else {}
        )
        components = []
        for source in (item, nested):
            components.extend(
                _text(source.get(key))
                for key in (
                    "subject",
                    "group",
                    "title",
                    "item",
                    "sub_item",
                    "validation_type",
                    "code",
                )
                if source.get(key) is not None
            )
        identity = "|".join(components) or f"rule-{position}"
        slug = _CODE.sub("-", identity.casefold()).strip("-")[:120] or f"rule-{position}"
        fingerprint = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
        code = f"{slug}-{fingerprint}"
        finding = {
            "code": code,
            "message": f"{response or 'unknown'} reported by rule {code}",
            "response": response or "unknown",
        }
        dependency = unavailable_dependency(item)
        if dependency:
            unavailable.add(dependency)
            finding["message"] = (
                f"External verification unavailable ({dependency}); original {response} retained"
            )
        location = next(
            (
                item[key]
                for key in ("xpath", "path", "line", "parent_id", "parent")
                if item.get(key) is not None
            ),
            None,
        )
        if location is not None:
            location_hash = hashlib.sha256(_text(location).encode("utf-8")).hexdigest()
            finding["path"] = f"locator-sha256:{location_hash}"
        findings.append(finding)
    for dependency in sorted(unavailable):
        findings.append(
            {
                "code": PREFIX + dependency,
                "message": f"External verification not completed: {dependency}",
                "response": "blocking",
            }
        )
        counts["blocking"] += 1
    findings.sort(key=lambda item: (item["response"], item["code"], item.get("path", "")))
    return {
        "complete": True,
        "findings": findings,
        "summary": dict(sorted(counts.items())),
    }


def _result_items(value: object, *, depth: int = 0) -> list[dict[str, Any]]:
    if depth > 30:
        return [{"response": "exception", "code": "adapter-result-too-deep"}]
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        keys = {str(key) for key in value}
        if keys & set(_SEVERITY_KEYS):
            found.append({str(key): item for key, item in value.items()})
        else:
            for item in value.values():
                found.extend(_result_items(item, depth=depth + 1))
    elif isinstance(value, (list, tuple)):
        for item in value:
            found.extend(_result_items(item, depth=depth + 1))
    return found


def _text(value: object) -> str:
    text = str(value) if value is not None else ""
    return "".join(
        character
        for character in text
        if character in "\t\n\r" or unicodedata.category(character) not in {"Cc", "Cf"}
    )
