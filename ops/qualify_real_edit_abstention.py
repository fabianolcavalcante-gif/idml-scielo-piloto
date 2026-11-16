"""Check the real IDML preflights at the cycle boundary with no provider connectivity."""

import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from idml_foundation.ingest.scanner import build_scanner
from idml_foundation.models import Job
from ops.edit_cycle_lab import review_candidate
from ops.qualify_edit_cycle import config
from ops.qualify_edit_preflight import qualify


class ForbiddenClient:
    async def run_agent(self, **kwargs):
        raise AssertionError("provider dispatch is forbidden for these inputs")


def check(root, inputs):
    settings = config(root)
    cases = qualify(root, inputs, settings, build_scanner(settings))["cases"]
    engine = create_engine(settings.database_url)
    try:
        with Session(engine) as db:
            rows = db.scalars(select(Job).where(Job.kind == "autocorrection.preflight")).all()
            out = []
            for case in cases:
                if case["positive_fixture"]:
                    continue
                (job,) = [
                    j
                    for j in rows
                    if j.result["scope"]["source_idml_sha256"] == case["source_sha256"]
                ]
                assert job.result["state"] == "abstained"
                receipt = asyncio.run(
                    review_candidate(
                        job.result,
                        {},
                        ForbiddenClient(),
                        still_authorized=lambda: False,
                        interrupted=lambda: False,
                    )
                )
                assert (
                    receipt["state"] == "no_eligible_candidate"
                    and receipt["calls"] == []
                    and not receipt["cost_microusd"]
                )
                out.append(
                    dict(
                        source_sha256=case["source_sha256"],
                        state=job.result["state"],
                        bindings=case["bindings"],
                        provider_calls=0,
                    )
                )
            assert len(out) == 2
            return out
    finally:
        engine.dispose()


if __name__ == "__main__":
    import sys

    with TemporaryDirectory() as tmp:
        print(json.dumps(check(Path(tmp), [Path(s) for s in sys.argv[1:]])))
