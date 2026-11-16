import json
import logging

import pytest
from pydantic import ValidationError

from idml_foundation.logging_config import JsonFormatter
from idml_foundation.settings import Settings


def test_production_rejects_default_secret() -> None:
    with pytest.raises(ValidationError):
        Settings(
            environment="production",
            database_url="postgresql+psycopg://db/idml",
            session_pepper="change-me",
        )


def test_json_log_does_not_emit_sensitive_extra() -> None:
    formatter = JsonFormatter()
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "completed", (), None)
    record.correlation_id = "corr-12345678"
    record.token = "must-not-appear"
    output = json.loads(formatter.format(record))
    assert output["message"] == "completed"
    assert "must-not-appear" not in json.dumps(output)


@pytest.mark.parametrize(
    "message",
    [
        "request failed Authorization=Bearer abcdefghijklmnop",
        "provider rejected sk-abcdefghijklmnop",
        "connect postgresql://user:database-password@example.test/idml",
        "pass" + "word=plain-text-password",
        "-----BEGIN PRIVATE KEY-----\nprivate-material\n-----END PRIVATE KEY-----",
    ],
)
def test_json_log_redacts_secrets_embedded_in_messages(message: str) -> None:
    formatter = JsonFormatter()
    record = logging.LogRecord("test", logging.ERROR, __file__, 1, message, (), None)

    output = formatter.format(record)

    assert "[REDACTED]" in output
    assert "abcdefghijklmnop" not in output
    assert "database-password" not in output
    assert "plain-text-password" not in output
    assert "private-material" not in output
