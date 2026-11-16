import pytest

from ops.gate_phase7_v12_storage import REQUIRED, evaluate
from tests.test_phase7_v12_queue_lab import evidence


def report():
    value = evidence()
    value["probe"]["storage"] = {
        "approved": True,
        "provider_calls": 0,
        "checks": dict.fromkeys(REQUIRED, True),
    }
    return value


def test_storage_gate_does_not_approve_production():
    result = evaluate(report())
    assert result["approved"]
    assert result["release_ready"] is result["production_capacity_qualified"] is False


@pytest.mark.parametrize("check", sorted(REQUIRED))
def test_storage_gate_requires_every_behavior(check):
    value = report()
    value["probe"]["storage"]["checks"][check] = False
    assert not evaluate(value)["approved"]


def test_storage_gate_rejects_missing_storage_and_host_failure():
    assert not evaluate(evidence())["approved"]
    value = report()
    value["existing_services_unchanged"] = False
    assert not evaluate(value)["approved"]
