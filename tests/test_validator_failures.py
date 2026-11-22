from pathlib import Path

from idml_foundation.services.validation_diagnosis import describe_validation
from idml_foundation.services.validator_failures import validator_failure_reason
from idml_foundation.services.validator_status import probe_socket


def test_validator_failures_map_to_fixed_codes_only() -> None:
    assert validator_failure_reason(FileNotFoundError("/run/x.sock")) == "broker-socket-missing"
    assert validator_failure_reason(ConnectionRefusedError()) == "broker-not-listening"
    assert validator_failure_reason(KeyError("result")) == "broker-error-envelope"
    assert (
        validator_failure_reason(ValueError("scoped_validation_evidence_missing"))
        == "scoped-validation-evidence-missing"
    )
    assert validator_failure_reason(ValueError("Traceback with article text")) == "unclassified"


def test_probe_reports_missing_socket_without_contacting_anything(tmp_path: Path) -> None:
    assert probe_socket(None) == {"configured": False}
    assert probe_socket(tmp_path / "absent.sock")["status"] == "socket-missing"


def test_diagnosis_shows_failure_reason() -> None:
    package = "a" * 64
    xml = "b" * 64
    result = {
        "package_sha256": package,
        "formal_validation": {
            "version": "package-formal-assessment-1.0",
            "package_sha256": package,
            "xml_sha256": xml,
            "external_runs": [
                {
                    "name": "packtools",
                    "status": "unavailable",
                    "failure_reason": "broker-not-listening",
                }
            ],
        },
    }
    items = describe_validation(result)["items"]
    details = " ".join(i["detail"] for i in items if i["code"] == "packtools-unavailable")
    assert "broker-not-listening" in details
