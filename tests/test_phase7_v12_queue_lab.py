import pytest

from ops.gate_phase7_v12_queue import evaluate
from ops.observe_phase7_v12_queue import preflight


def host_sample():
    return {
        "memory_available_bytes": 848 * 1024**2,
        "disk_used_percent": 85,
        "disk_free_bytes": 15 * 1024**3,
        "ready": True,
        "ready_ms": 10,
    }


def evidence():
    return {
        "version": "phase7-v12-real-queue-observation-1.0",
        "approved": True,
        "failures": [],
        "cleanup_errors": [],
        "existing_services_unchanged": True,
        "existing_service_count": 25,
        "samples": [host_sample()] * 5,
        "container_states": {n: {"oom_killed": False} for n in ("pg", "redis", "app")},
        "limits": {
            "total_memory_mib": 336,
            "application_memory_mib": 224,
            "internal_network": True,
            "published_ports": 0,
        },
        "restricted_content_emitted": False,
        "probe": {
            "version": "phase7-v12-real-queue-1.0",
            "approved": True,
            "provider_calls": 0,
            "restricted_content_emitted": False,
            "scenarios": [
                {
                    "mode": mode,
                    "approved": True,
                    "jobs": 6,
                    "effects": 6,
                    "events": 18,
                    "delayed_job_respected": True,
                    "delayed_observed_waiting": True,
                    "samples": [{}] * 6,
                    "xml_sha256": ["a" * 64],
                }
                for mode in ("normal", "duplicate", "lost", "outage")
            ],
        },
    }


def test_lab_requires_full_memory_headroom_before_creation():
    sample = host_sample()
    assert preflight(sample) == []
    sample["memory_available_bytes"] -= 1
    assert "insufficient_lab_headroom" in preflight(sample)


def test_real_queue_gate_is_not_a_full_capacity_approval():
    report = evaluate(evidence())
    assert report["approved"] is True
    assert report["v12_2_complete"] is report["v12_complete"] is report["release_ready"] is False


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_mode",
        "oom",
        "memory",
        "cleanup",
        "effects",
        "due_time",
        "waiting_not_observed",
        "ports",
        "digest",
        "privacy",
        "restart",
    ],
)
def test_real_queue_gate_rejects_failed_evidence(mutation):
    report = evidence()
    if mutation == "missing_mode":
        report["probe"]["scenarios"].pop()
    elif mutation == "oom":
        report["container_states"]["app"]["oom_killed"] = True
    elif mutation == "memory":
        report["samples"][0]["memory_available_bytes"] = 511 * 1024**2
    elif mutation == "cleanup":
        report["cleanup_errors"] = ["app"]
    elif mutation == "effects":
        report["probe"]["scenarios"][0]["effects"] = 7
    elif mutation == "due_time":
        report["probe"]["scenarios"][0]["delayed_job_respected"] = False
    elif mutation == "waiting_not_observed":
        report["probe"]["scenarios"][0]["delayed_observed_waiting"] = False
    elif mutation == "ports":
        report["limits"]["published_ports"] = 1
    elif mutation == "digest":
        report["probe"]["scenarios"][0]["xml_sha256"] = ["b" * 64]
    elif mutation == "privacy":
        report["restricted_content_emitted"] = True
    else:
        report["existing_services_unchanged"] = False
    assert evaluate(report)["approved"] is False
