import asyncio

import pytest

from idml_foundation.ai.orchestration import ProviderResponse
from ops.edit_cycle_lab import review_candidate
from ops.qualify_edit_cycle import prepare, review, validate
from tests.autocorrection_helpers import SyntheticCleanScanner


class Votes:
    def __init__(self, decisions=(), *, alter_hash=False):
        self.decisions = iter(decisions)
        self.alter_hash = alter_hash
        self.calls = []

    async def run_agent(self, **kw):
        assert not kw["tool_allowlist"]
        self.calls.append(kw["session_key"])
        digest = kw["input_envelope"]["evidence"]["xml_sha256"]
        return ProviderResponse(
            payload=dict(
                candidate_sha256="b" * 64 if self.alter_hash else digest,
                decision=next(self.decisions, "support"),
            ),
            provider="openai",
            model="gpt-5.4-mini",
            input_tokens=100,
            output_tokens=50,
        )


def run(client, **overrides):
    preflight = dict(state="staged", offline_valid=True, xml_sha256="a" * 64)
    args = dict(still_authorized=lambda: True, interrupted=lambda: False)
    args.update(overrides)
    return asyncio.run(review_candidate(preflight, dict(xml_sha256="a" * 64), client, **args))


@pytest.mark.parametrize(
    "decisions,state,count",
    [
        (["support", "abstain"], "abstained", 2),
        (["recheck", "recheck"], "round_limit", 2),
        (["recheck"], "supported_for_revalidation", 5),
        (["support"] * 4, "supported_for_revalidation", 4),
    ],
)
def test_bounded_roles(decisions, state, count):
    client = Votes(decisions)
    r = run(client)
    assert (
        r["state"] == state
        and len(set(client.calls)) == count
        and 0 < r["cost_microusd"] <= r["budget_microusd"]
    )
    assert max(c["round"] for c in r["calls"]) <= 2


def test_stops_after_interrupt_or_revocation():
    for key, state in [
        ("interrupted", "interrupted"),
        ("still_authorized", "authorization_refused"),
    ]:
        client = Votes()

        def switch(client=client, key=key):
            return bool(client.calls) if key == "interrupted" else not client.calls

        assert run(client, **{key: switch})["state"] == state
        assert len(client.calls) == 1


def test_no_calls_without_budget_or_eligible_preflight():
    client = Votes()
    assert run(client, budget_microusd=1)["state"] == "budget_exhausted"
    for state in ("abstained", "refused", "unknown"):
        result = asyncio.run(
            review_candidate(
                dict(state=state),
                {},
                client,
                still_authorized=lambda: False,
                interrupted=lambda: False,
            )
        )
        assert result["state"] == "no_eligible_candidate"
    assert not client.calls


def test_wrong_candidate_stops_before_critics():
    client = Votes(alter_hash=True)
    assert run(client)["state"] == "candidate_mismatch" and len(client.calls) == 1


def test_affiliation_cycle_revalidates_both_versions(tmp_path):
    prepare(tmp_path, SyntheticCleanScanner())
    assert review(tmp_path, Votes())["state"] == "supported_for_revalidation"
    result = validate(tmp_path, controlled=True)
    assert result["applied"] and result["restore_state"] == "revalidated-working-draft"
    assert (
        result["xml_sha256"] != result["restored_xml_sha256"]
        and result["package_sha256"] != result["restored_package_sha256"]
    )
    with pytest.raises(FileExistsError):
        review(tmp_path, Votes())
