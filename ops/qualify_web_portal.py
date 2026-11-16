"""Isolated HTTP RC fixture. Inputs and accounts live only in the qualification database."""

import json
import os
import sys
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from idml_foundation.models import Artifact, Job, Membership, Resource, User
from idml_foundation.pipeline.profile import load_profile
from idml_foundation.pipeline.validation import OfflineJatsValidator
from idml_foundation.security import hash_password
from idml_foundation.services.canonical_heads import current_canonical_snapshot
from idml_foundation.services.restored_package_validation import restore_and_revalidate_package
from idml_foundation.services.web_edit_cycle import WebEditDecision
from idml_foundation.worker import process_job
from ops.qualify_edit_cycle import config, recover_reference, save

ROOT = Path("/case")


def run(action):
    case = json.loads((ROOT / "case.json").read_bytes())
    s = config(ROOT)
    engine = create_engine(s.database_url)
    factory = sessionmaker(engine, expire_on_commit=False)
    try:
        with factory() as db:
            initial = db.get(Job, case["job_id"])
            resource = db.get(Resource, initial.payload["resource_id"])
            if action == "accounts":
                password = sys.stdin.readline().strip()
                assert len(password) >= 32
                for role in ("operator", "reviewer"):
                    user = User(
                        email=role + "@web-rc.example.org", password_hash=hash_password(password)
                    )
                    db.add(user)
                    db.flush()
                    db.add(
                        Membership(
                            user_id=user.id, organization_id=resource.organization_id, role=role
                        )
                    )
                request = {k: v for k, v in initial.payload.items() if k != "authorization_id"}
                permit = WebEditDecision.model_validate(
                    dict(
                        purpose="review-and-promote-affiliation-v1",
                        model="openai/gpt-5.4-mini",
                        scope=request,
                        organization_id=resource.organization_id,
                        authorization_id=initial.payload["authorization_id"],
                        allowed_literal_sha256=case["published_reference"][
                            "authorized_literal_sha256"
                        ],
                        pdf_artifact_id=case["pdf_id"],
                        pdf_sha256=db.get(Artifact, case["pdf_id"]).sha256,
                    )
                )
                folder = (
                    ROOT
                    / "decisions"
                    / "web-edit-decisions"
                    / resource.organization_id
                    / resource.id
                    / request["canonical_snapshot_id"]
                )
                folder.mkdir(parents=True)
                (folder / f"{resource.version}.json").write_text(permit.model_dump_json())
                db.commit()
                return
            (job,) = db.scalars(select(Job).where(Job.kind == "autocorrection.evaluate")).all()
            if action == "queued":
                assert job.state == "queued"
                return
            s.validator_scoped_authorities = True
            s.validator_socket = Path("/socket/modern.sock")
            s.xpm_socket = Path("/socket/xpm.sock")
            if action == "process":
                from pydantic import SecretStr

                s.feature_web_edit_provider = True
                s.openclaw_gateway_url = "http://openclaw-idml:47716"
                s.openclaw_gateway_token = SecretStr(os.environ["IDML_OPENCLAW_GATEWAY_TOKEN"])
                assert job.state == "queued"
                process_job(job.id, factory, settings=s)
                db.refresh(job)
                assert job.state == "succeeded" and job.result["state"] == "applied", (
                    job.state,
                    job.error_code,
                    (job.result or {}).get("reason"),
                )
                save(
                    ROOT / "web-cycle.json",
                    dict(
                        state=job.result["state"],
                        review=job.result["review"],
                        provider_calls=job.result["provider_calls"],
                    ),
                )
            elif action == "restore":
                assert job.result["active_snapshot_changed"]
                pdf = db.get(Artifact, case["pdf_id"])
                head = current_canonical_snapshot(
                    db, organization_id=resource.organization_id, resource_id=resource.id
                )
                restore = restore_and_revalidate_package(
                    db,
                    organization_id=resource.organization_id,
                    resource_id=resource.id,
                    expected_snapshot_id=head.id,
                    expected_resource_version=resource.version,
                    target_snapshot_id=initial.payload["canonical_snapshot_id"],
                    request_id=uuid4(),
                    pdf_artifact_id=pdf.id,
                    pdf_sha256=pdf.sha256,
                    profile=load_profile(s.journal_profile_path),
                    settings=s,
                    validator=OfflineJatsValidator(Path("vendor/jats/1.3")),
                )
                assert restore.receipt["state"] == "blocked"
                db.commit()
            else:
                raise ValueError("unknown_action")
        if action == "restore":
            save(ROOT / "web-recovery.json", recover_reference(ROOT))
    finally:
        engine.dispose()


if __name__ == "__main__":
    run(sys.argv[1])
