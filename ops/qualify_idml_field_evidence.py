"""Exercise idml.process on private originals in a disposable DB. Emit hashes and counts."""

import argparse
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from idml_foundation.database import Base
from idml_foundation.ingest.scanner import PolicyOnlyScanner
from idml_foundation.models import Organization, Resource
from idml_foundation.pipeline.profile import load_profile
from idml_foundation.pipeline.service import DeterministicPipeline
from idml_foundation.services.artifacts import store_idml_artifact
from idml_foundation.services.jobs import create_job
from idml_foundation.settings import Settings
from idml_foundation.worker import process_job


def qualify(path: Path) -> dict:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        settings = Settings(
            environment="test",
            artifact_root=root / "artifacts",
            journal_profile_path=Path(__file__).resolve().parents[1] / "profiles/esa-aop-1.1.json",
            artifact_disk_reserve_bytes=1,
            feature_openclaw=False,
            feature_ai_swarm=False,
        )
        engine = create_engine(f"sqlite+pysqlite:///{root / 'isolated.sqlite'}")
        try:
            Base.metadata.create_all(engine)
            factory = sessionmaker(engine, expire_on_commit=False)
            raw = path.read_bytes()
            baseline = DeterministicPipeline(
                settings=settings, profile=load_profile(settings.journal_profile_path)
            ).run(raw, logical_name=path.name)
            with factory() as db:
                org = Organization(slug="isolated", name="Laboratory")
                db.add(org)
                db.flush()
                resource = Resource(organization_id=org.id, title="Qualification")
                db.add(resource)
                db.flush()
                source, _ = store_idml_artifact(
                    db,
                    organization_id=org.id,
                    original_name=path.name,
                    data=raw,
                    settings=settings,
                    scanner=PolicyOnlyScanner(),
                )
                job, _ = create_job(
                    db,
                    organization_id=org.id,
                    kind="idml.process",
                    idempotency_key=uuid4().hex,
                    payload={"resource_id": resource.id, "idml_artifact_id": source.id},
                    correlation_id=uuid4().hex,
                    actor_id="qualification",
                )
                db.commit()
                process_job(job.id, factory, settings=settings)
                db.refresh(job)
                assert job.state == "succeeded", job.error_code
                proof = job.result["field_evidence"]
                assert proof["status"] == "prepared"
                assert job.result["xml_sha256"] == hashlib.sha256(baseline.xml).hexdigest()
                assert job.result["validation"] == baseline.validation.model_dump(mode="json")
                return dict(
                    article=baseline.canonical.article_id,
                    **proof,
                    offline_valid=baseline.validation.valid,
                    scanner="policy_only",
                )
        finally:
            engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", type=Path, nargs="+")
    print(json.dumps([qualify(path) for path in parser.parse_args().inputs], indent=2))
