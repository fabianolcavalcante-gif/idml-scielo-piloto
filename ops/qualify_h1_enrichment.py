"""Local-only parity proof: private qualified catalogs through the actual job processor."""

import hashlib
import json
import tempfile
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from idml_foundation.database import Base
from idml_foundation.ingest.scanner import PolicyOnlyScanner
from idml_foundation.models import Job, Organization, Resource
from idml_foundation.services.artifacts import store_idml_artifact
from idml_foundation.services.enrichment import bundle_path
from idml_foundation.settings import Settings
from idml_foundation.worker import process_job

ROOT = Path(__file__).resolve().parents[1]
CASES = (
    (
        "esa-e20240086",
        "tmp/sample/ESA_2024086_AOP.idml",
        {
            "formula_catalog": "formula-transcription-catalog-v1.json",
            "editorial_enrichment_catalog": "editorial-enrichment-catalog-v1.json",
        },
        "15287f774bed60a62f0c5734aa7082234cbc7b69b86effeecc7a1e9ea991bc20",
    ),
    (
        "esa-e20240135",
        "tmp/ARQUIVOS TESTE/ESA_2024135_AOP.idml",
        {
            "formula_catalog": "formula-transcription-catalog-e20240135-v1.json",
            "crossref_metadata_catalog": "crossref-metadata-authority-e20240135-v1.json",
            "formal_metadata_catalog": "formal-metadata-authority-e20240135-v1.json",
        },
        "20a03a91496ac0b447bd2abe589c2be6c231547793dcf5289bd3e66cc1990880",
    ),
)


def main():
    rows = []
    with tempfile.TemporaryDirectory(prefix="h1-", dir=ROOT / "tmp") as temp:
        root = Path(temp)
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        factory = sessionmaker(engine, expire_on_commit=False)
        settings = Settings(
            environment="test", artifact_root=root / "artifacts", enrichment_root=root / "catalogs"
        )
        try:
            for case, filename, catalogs, expected in CASES:
                source = ROOT / filename
                data = source.read_bytes()
                digest = hashlib.sha256(data).hexdigest()
                with Session(engine) as db:
                    org = Organization(slug=case, name="Local qualification")
                    db.add(org)
                    db.flush()
                    resource = Resource(organization_id=org.id, title="Local qualification")
                    db.add(resource)
                    db.flush()
                    artifact, _ = store_idml_artifact(
                        db,
                        organization_id=org.id,
                        original_name=source.name,
                        data=data,
                        settings=settings,
                        scanner=PolicyOnlyScanner(),
                    )
                    directory = root / "catalogs" / bundle_path(org.id, resource.id, digest)
                    directory.mkdir(parents=True)
                    hashes = {}
                    for kind, name in catalogs.items():
                        content = (ROOT / "benchmarks/private/output" / name).read_bytes()
                        (directory / f"{kind}.json").write_bytes(content)
                        hashes[kind] = hashlib.sha256(content).hexdigest()
                    manifest = {
                        "version": "enrichment-bundle-1.0",
                        "organization_id": org.id,
                        "resource_id": resource.id,
                        "source_idml_sha256": digest,
                        "profile_id": "esa-aop-1.0.0",
                        "catalogs": hashes,
                    }
                    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
                    job = Job(
                        organization_id=org.id,
                        kind="idml.process",
                        idempotency_key=case,
                        payload={"resource_id": resource.id, "idml_artifact_id": artifact.id},
                    )
                    db.add(job)
                    db.commit()
                    job_id = job.id
                process_job(job_id, factory, settings=settings)
                with Session(engine) as db:
                    job = db.get(Job, job_id)
                    actual = job.result.get("xml_sha256") if job.result else None
                    provenance = job.result.get("enrichment", {}) if job.result else {}
                    rows.append(
                        {
                            "corpus_id": case,
                            "job_state": job.state,
                            "xml_sha256": actual,
                            "matches_qualified_xml": actual == expected,
                            "catalog_count": len(provenance.get("catalog_sha256", {})),
                            "provenance_recorded": provenance.get("status") == "selected",
                        }
                    )
        finally:
            engine.dispose()
    report = {
        "version": "h1-job-parity-1.0",
        "cases": rows,
        "approved": all(
            r["matches_qualified_xml"]
            and r["provenance_recorded"]
            and r["job_state"] == "succeeded"
            for r in rows
        ),
        "scope": "local SQLite actual process_job; no Redis/HTTP/provider/external validators",
        "temporary_copies_removed": True,
        "release_ready": False,
    }
    (ROOT / "benchmarks/qualification/reports/h1-job-parity-v1.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report))
    return 0 if report["approved"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
