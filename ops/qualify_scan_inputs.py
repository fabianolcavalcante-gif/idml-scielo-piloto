"""Isolated HTTP upload/rescan and conversion using private user-provided inputs."""

import hashlib
import json
import time
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4
from zipfile import ZipFile

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from idml_foundation.database import Base, get_db
from idml_foundation.dependencies import get_content_scanner
from idml_foundation.domain.canonical import CanonicalArticle
from idml_foundation.ingest.scanner import PolicyOnlyScanner, build_scanner
from idml_foundation.main import create_app
from idml_foundation.models import AuditEvent, Organization
from idml_foundation.rbac import Role
from idml_foundation.services.snapshots import store_snapshot
from idml_foundation.settings import Settings, get_settings
from idml_foundation.worker import process_job
from tests.test_phase7_v10_workflow import _headers, _user


def run(root, directory):
    settings = Settings(
        environment="test",
        artifact_root=directory / "artifacts",
        artifact_disk_reserve_bytes=1,
        feature_clamav=True,
        clamav_socket=Path("/run/idml-clamav-vh1/scan.sock"),
        journal_profile_path=Path("/app/profiles/esa-aop-1.1.json"),
    )
    # Official harmless EICAR control, assembled only inside the isolated test process.
    control = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}" + b"$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
    rejected = build_scanner(settings).scan(control)
    assert not rejected.clean and rejected.status == "malware_detected"
    engine = create_engine(f"sqlite+pysqlite:///{directory / 'local.sqlite'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    app = create_app()

    def database():
        with factory() as db:
            yield db
            db.commit()

    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_settings] = lambda: settings
    with factory() as db:
        org = Organization(slug="isolated", name="Qualification")
        db.add(org)
        db.flush()
        headers = _headers(db, _user(db, org, "scan@example.invalid", Role.OPERATOR), org, settings)
    cases = []
    with TestClient(app, headers=headers) as client:

        def upload(path, kind):
            response = client.post(
                "/v1/artifacts/" + kind, files={"upload": (path.name, path.read_bytes())}
            )
            assert response.status_code == 201, (kind, response.status_code)
            return response.json()

        def job(kind, payload, *, allow_failure=False):
            response = client.post(
                "/v1/jobs", json=dict(kind=kind, payload=payload, idempotency_key=uuid4().hex)
            )
            assert response.status_code == 202
            jid = response.json()["id"]
            process_job(jid, factory, settings=settings)
            body = client.get("/v1/jobs/" + jid).json()
            if allow_failure and body["state"] == "failed_permanent":
                return {"failure": body["error_code"]}
            assert body["state"] == "succeeded", (kind, body["error_code"])
            return body["result"]

        for folder in sorted(root.iterdir()):
            start = time.monotonic()
            resource = client.post("/v1/resources", json={"title": "Qualification"}).json()["id"]
            app.dependency_overrides[get_content_scanner] = PolicyOnlyScanner
            source = upload(next(folder.glob("*.idml")), "idml")
            assert source["scanner_status"] == "policy_only"
            del app.dependency_overrides[get_content_scanner]
            response = client.post("/v1/artifacts/" + source["id"] + "/rescan")
            assert (
                response.status_code == 200 and response.json()["scanner_status"] == "clamav_clean"
            )
            assert source["sha256"] == response.json()["sha256"]
            pdf = upload(next(folder.glob("*.pdf")), "assets")
            pictures = [upload(p, "assets") for p in sorted(folder.glob("*.jpg"))]
            assert all(p["scanner_status"] == "clamav_clean" for p in [pdf, *pictures])
            common = dict(resource_id=resource, idml_artifact_id=source["id"])
            conversion = job("idml.process", common)
            payload = common | dict(
                canonical_snapshot_id=conversion["canonical_snapshot_id"],
                pdf_artifact_id=pdf["id"],
                asset_artifact_ids=[p["id"] for p in pictures],
            )
            package = job("scielo.package", payload, allow_failure=True)
            raw_package = package.get("failure", "completed")
            if raw_package != "completed":
                # Exercise the previously qualified enriched snapshot separately when
                # raw IDML references additional materials not supplied with the article.
                scope = json.loads((folder / "scope.json").read_bytes())
                assert scope["source_idml_sha256"] == source["sha256"]
                article = CanonicalArticle.model_validate_json(
                    (folder / "canonical.json").read_bytes()
                )
                with factory() as db:
                    enriched, _ = store_snapshot(
                        db,
                        organization_id=org.id,
                        resource_id=resource,
                        document=article,
                        revision=2,
                        source_artifact_id=source["id"],
                        parent_snapshot_id=conversion["canonical_snapshot_id"],
                    )
                    db.commit()
                package = job("scielo.package", payload | {"canonical_snapshot_id": enriched.id})
                assert package["package_sha256"] == scope["package_sha256"]
            receipt = package["figure_bindings"]
            assert (
                receipt["source_sha256"] == source["sha256"]
                and receipt["package_sha256"] == package["package_sha256"]
            )
            result = client.get("/v1/artifacts/" + package["package_artifact_id"] + "/download")
            assert (
                result.status_code == 200
                and hashlib.sha256(result.content).hexdigest() == receipt["package_sha256"]
            )
            assets = {p["id"]: p for p in pictures}
            assert {f["artifact_id"] for f in receipt["figures"]} == set(assets)
            with ZipFile(BytesIO(result.content)) as z:
                for f in receipt["figures"]:
                    original = (folder / assets[f["artifact_id"]]["original_name"]).read_bytes()
                    assert (
                        z.read(f["package_name"]) == original
                        and hashlib.sha256(original).hexdigest() == f["sha256"]
                    )
            with factory() as db:
                audit = db.scalar(
                    select(AuditEvent).where(
                        AuditEvent.resource_id == source["id"],
                        AuditEvent.action == "artifact.rescan",
                    )
                )
                assert (
                    audit.outcome == "clamav_clean" and audit.details["previous"] == "policy_only"
                )
            cases.append(
                dict(
                    case=folder.name,
                    raw_package=raw_package,
                    scanned_inputs=2 + len(pictures),
                    figures=len(receipt["figures"]),
                    verified_from_canonical=sum(
                        f["canonical_origin_verified"] for f in receipt["figures"]
                    ),
                    layout_assets=receipt["canonical_asset_count"],
                    source_sha256=source["sha256"],
                    package_sha256=receipt["package_sha256"],
                    offline_valid=package["validation"]["valid"],
                    elapsed_seconds=round(time.monotonic() - start, 1),
                )
            )
            print("verified", folder.name, flush=True)
    engine.dispose()
    return dict(
        cases=cases,
        eicar_rejected=True,
        real_http_handlers=True,
        real_clamav=True,
        historical_rescan_audited=True,
        native_formal_validators_exercised=False,
        ai_invoked=False,
    )


if __name__ == "__main__":
    with TemporaryDirectory() as tmp:
        print(json.dumps(run(Path("/inputs"), Path(tmp))))
