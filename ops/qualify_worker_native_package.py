"""Isolated real package job from previously qualified canonical data, not IDML E2E."""

import argparse
import hashlib
import json
from io import BytesIO
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from idml_foundation.database import Base
from idml_foundation.domain.canonical import CanonicalArticle
from idml_foundation.models import Artifact, Job, Organization, Resource
from idml_foundation.services.artifacts import read_artifact_bytes
from idml_foundation.services.jobs import create_job
from idml_foundation.services.snapshots import store_snapshot
from idml_foundation.services.validation_diagnosis import describe_validation
from idml_foundation.settings import Settings
from idml_foundation.worker import process_job


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--authorize-public-sources", action="store_true")
    args = parser.parse_args()
    if args.authorize_public_sources and args.prepare_only:
        raise ValueError("separate_qualification_modes")
    if args.authorize_public_sources:
        from idml_foundation import source_access_models  # noqa: F401
    root = Path(__file__).resolve().parents[1]
    scope = json.loads((args.case / "scope.json").read_bytes())
    article = CanonicalArticle.model_validate_json((args.case / "canonical.json").read_bytes())
    args.output.mkdir(parents=True, exist_ok=False)
    settings = Settings(
        environment="test",
        database_url="sqlite+pysqlite:///:memory:",
        artifact_root=args.output / "artifacts",
        artifact_disk_reserve_bytes=1,
        validator_socket=Path("/socket/modern.sock"),
        xpm_socket=Path("/socket/xpm.sock"),
        validator_scoped_authorities=True,
        validator_registry_path=root / "config/validator-registry-vh1-composed.json",
        journal_profile_path=root / "profiles/esa-aop-1.1.json",
    )
    engine = create_engine(f"sqlite+pysqlite:///{args.output / 'qualification.sqlite'}")
    if args.prepare_only:
        settings.xpm_socket = None
        settings.validator_socket = None
        settings.validator_scoped_authorities = False
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, autoflush=False, expire_on_commit=False)
    with factory() as db:
        org = Organization(
            id=scope["organization_id"], slug="isolated-worker", name="Qualification"
        )
        db.add(org)
        db.flush()
        resource = Resource(id=scope["resource_id"], organization_id=org.id, title="Qualification")
        db.add(resource)
        db.flush()
        # Package building binds the prequalified IDML hash, but does not parse it.
        # No live article, user account, scan result or ingestion success is invented.
        source = Artifact(
            organization_id=org.id,
            original_name="qualified.idml",
            media_type="application/vnd.adobe.indesign-idml-package",
            size_bytes=1,
            sha256=scope["source_idml_sha256"],
            storage_key="qualification-metadata-only",
            scanner_status="qualification_fixture",
        )
        db.add(source)
        db.flush()
        snapshot, _ = store_snapshot(
            db,
            organization_id=org.id,
            resource_id=resource.id,
            document=article,
            revision=1,
            source_artifact_id=source.id,
        )
        assets = []
        pdf = None
        with ZipFile(args.case / "candidate.zip") as archive:
            for name in archive.namelist():
                if name.endswith(".xml") or name == "conversion-manifest.json":
                    continue
                raw = archive.read(name)
                digest = hashlib.sha256(raw).hexdigest()
                key = f"{org.id}/{digest[:2]}/{digest}"
                path = settings.artifact_root / key
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
                media = "application/pdf" if name.endswith(".pdf") else "image/jpeg"
                item = Artifact(
                    organization_id=org.id,
                    original_name=name,
                    media_type=media,
                    size_bytes=len(raw),
                    sha256=digest,
                    storage_key=key,
                    scanner_status="qualification_fixture",
                )
                db.add(item)
                db.flush()
                if media == "application/pdf":
                    pdf = item.id
                else:
                    assets.append(item.id)
        assert pdf
        job, _ = create_job(
            db,
            organization_id=org.id,
            kind="scielo.package",
            idempotency_key=uuid4().hex,
            payload=dict(
                resource_id=resource.id,
                canonical_snapshot_id=snapshot.id,
                idml_artifact_id=source.id,
                pdf_artifact_id=pdf,
                asset_artifact_ids=assets,
            ),
            correlation_id=uuid4().hex,
            actor_id="isolated-qualification",
        )
        db.commit()
        identity = job.id
    if args.authorize_public_sources:
        from ops.qualify_source_access_http import authorize

        authorize(factory, settings, scope)
    process_job(identity, factory, settings=settings)
    with factory() as db:
        job = db.get(Job, identity)
        assert job is not None and job.state == "succeeded", job.error_code if job else "missing"
        formal = job.result["formal_validation"]
        assert formal["xml_sha256"] == scope["xml_sha256"]
        if args.prepare_only:
            artifact = db.get(Artifact, job.result["package_artifact_id"])
            assert artifact is not None
            package = read_artifact_bytes(artifact, settings)
            with ZipFile(args.case / "candidate.zip") as old, ZipFile(BytesIO(package)) as new:
                assert set(old.namelist()) == set(new.namelist())
                for name in old.namelist():
                    if name == "conversion-manifest.json":
                        a, b = (json.loads(z.read(name)) for z in (old, new))
                        a.pop("validator_versions")
                        b.pop("validator_versions")
                        assert a == b
                    else:
                        assert old.read(name) == new.read(name)
                xml = next(new.read(n) for n in new.namelist() if n.endswith(".xml"))
            (args.output / "candidate.zip").write_bytes(package)
            (args.output / "candidate.xml").write_bytes(xml)
            (args.output / "scope.json").write_text(
                json.dumps(
                    scope
                    | {
                        "xml_sha256": formal["xml_sha256"],
                        "package_sha256": formal["package_sha256"],
                    }
                )
            )
            (args.output / "canonical.json").write_bytes(
                (args.case / "canonical.json").read_bytes()
            )
            print(
                json.dumps(
                    dict(
                        prepared=True,
                        xml_and_assets_unchanged=True,
                        manifest_validator_versions_only=True,
                        package_sha256=formal["package_sha256"],
                    )
                )
            )
            engine.dispose()
            return
        assert formal["package_sha256"] == scope["package_sha256"]
        assert all(r["status"] == "completed" for r in formal["external_runs"])
        assert formal["xpm"]["status"] == "completed"
        assert not formal["ready_for_scielo"]
        (args.output / "result.json").write_text(
            json.dumps(
                dict(
                    version="worker-native-package-1.0",
                    job_state=job.state,
                    formal_validation=formal,
                    diagnosis=describe_validation(job.result),
                    offline=job.result["validation"],
                    source_xml_sha256=scope["xml_sha256"],
                    source_package_sha256=scope["package_sha256"],
                    isolated_database=True,
                    actual_worker_job=True,
                    idml_ingestion_exercised=False,
                    ai_invoked=False,
                    public_sources_authorized=args.authorize_public_sources,
                    release_approved=False,
                ),
                indent=2,
            )
        )
        print(
            json.dumps(
                dict(
                    job_state=job.state,
                    modern_completed=2,
                    xpm_completed=True,
                    package_sha256=formal["package_sha256"],
                    release_approved=False,
                )
            )
        )
    engine.dispose()


if __name__ == "__main__":
    main()
