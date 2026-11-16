import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

SENSITIVE_KEYS = re.compile(r"password|secret|token|authorization|cookie|content", re.IGNORECASE)
SENSITIVE_VALUES = (
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{8,}\b", re.IGNORECASE),
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)(password|secret|token|authorization|cookie)(\s*[=:]\s*)[^\s,;]+"),
    re.compile(r"(?i)([a-z][a-z0-9+.-]*://[^:/\s]+:)[^@/\s]+@"),
)


def _sanitize_text(value: str) -> str:
    sanitized = value
    for pattern in SENSITIVE_VALUES:
        if pattern.groups == 2:
            sanitized = pattern.sub(r"\1\2[REDACTED]", sanitized)
        elif pattern.groups == 1:
            sanitized = pattern.sub(r"\1[REDACTED]@", sanitized)
        else:
            sanitized = pattern.sub("[REDACTED]", sanitized)
    return sanitized


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if SENSITIVE_KEYS.search(str(key)) else _sanitize(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_sanitize(item) for item in value]
    if isinstance(value, str):
        return _sanitize_text(value)
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in ("correlation_id", "organization_id", "job_id", "event"):
            if hasattr(record, field):
                payload[field] = getattr(record, field)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(_sanitize(payload), ensure_ascii=False, separators=(",", ":"))


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
