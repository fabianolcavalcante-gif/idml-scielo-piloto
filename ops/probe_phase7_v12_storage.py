"""Synthetic transaction/quota probe inside the disposable PostgreSQL lab only."""

import json
import subprocess
import sys

from idml_foundation.database import SessionLocal
from idml_foundation.models import Organization
from idml_foundation.services.artifacts import store_generated_artifact


def probe(settings):
    settings = settings.model_copy(update={"artifact_tenant_quota_bytes": 4})
    with SessionLocal() as db:
        org = Organization(slug="storage-probe", name="Synthetic storage")
        db.add(org)
        db.commit()
        tenant = org.id

    def child(content):
        result = subprocess.run(  # noqa: S603 -- fixed module in isolated lab
            [sys.executable, "-m", "ops.probe_phase7_v12_storage", tenant, content],
            capture_output=True,
            text=True,
            timeout=20,
            check=True,
        )
        return json.loads(result.stdout)

    with SessionLocal() as db:
        artifact = store_generated_artifact(
            db,
            organization_id=tenant,
            original_name="synthetic.xml",
            data=b"<x/>",
            media_type="application/xml",
            settings=settings,
        )
        busy = child("<y/>")
        db.rollback()
        orphan_preserved = (settings.artifact_root / artifact.storage_key).read_bytes() == b"<x/>"
    quota = child("<y/>")
    recovered = child("<x/>")
    dedup = child("<x/>")
    checks = {
        "cross_process_busy": busy.get("code") == "artifact_storage_busy",
        "rollback_orphan_preserved": orphan_preserved,
        "orphan_charged_to_quota": quota.get("code") == "artifact_quota_exceeded",
        "orphan_recovered": recovered.get("size") == 4,
        "committed_deduplicated": bool(recovered.get("id"))
        and recovered.get("id") == dedup.get("id"),
    }
    return {"approved": all(checks.values()), "checks": checks, "provider_calls": 0}


if __name__ == "__main__":
    from idml_foundation.services.storage_budget import ArtifactStorageError
    from idml_foundation.settings import Settings

    settings = Settings(artifact_tenant_quota_bytes=4)
    if settings.database_url != "postgresql+psycopg://v12lab:v12lab@pg:5432/v12lab":
        raise RuntimeError("refusing non-laboratory database")
    try:
        with SessionLocal() as db:
            artifact = store_generated_artifact(
                db,
                organization_id=sys.argv[1],
                original_name="synthetic.xml",
                data=sys.argv[2].encode(),
                media_type="application/xml",
                settings=settings,
            )
            db.commit()
            print(json.dumps({"id": artifact.id, "size": artifact.size_bytes}))
    except ArtifactStorageError as exc:
        print(json.dumps({"code": exc.code}))
