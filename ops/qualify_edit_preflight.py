"""Run the edit preflight with a disposable database, real worker and isolated decisions."""

import argparse
import hashlib
import json
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from lxml import etree
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from idml_foundation.autocorrection_models import AutomationAttempt, AutomationGrantRecord
from idml_foundation.database import Base
from idml_foundation.domain.common import content_digest
from idml_foundation.ingest.scanner import ContentScanner, build_scanner
from idml_foundation.models import AgentRun, Organization, Resource, utcnow
from idml_foundation.schemas import JobCreate
from idml_foundation.services.artifacts import store_idml_artifact
from idml_foundation.services.autocorrection_authorization import RevisionEditAuthorization
from idml_foundation.services.canonical_heads import current_canonical_snapshot
from idml_foundation.services.jobs import create_job
from idml_foundation.settings import Settings
from idml_foundation.worker import process_job
from tests.test_autocorrection_evidence_pipeline import pipeline_idml


def qualify(
    root: Path,
    inputs: list[Path],
    settings: Settings,
    scanner: ContentScanner,
    *,
    positive_idml: bytes | None = None,
) -> dict:
    assert settings.automation_authorization_root == root / "decisions"
    decisions = root / "decisions" / "autocorrection-authorizations"
    decisions.mkdir(parents=True)
    engine = create_engine(f"sqlite+pysqlite:///{root / 'qualification.sqlite'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    cases = []
    try:
        with factory() as db:
            org = Organization(slug="preflight", name="Laboratory")
            db.add(org)
            db.flush()

            def job(kind, payload):
                request = JobCreate(kind=kind, idempotency_key=uuid4().hex, payload=payload)
                row, _ = create_job(
                    db,
                    organization_id=org.id,
                    kind=kind,
                    idempotency_key=request.idempotency_key,
                    payload=request.payload,
                    correlation_id=uuid4().hex,
                    actor_id="qualification",
                )
                db.commit()
                process_job(row.id, factory, settings=settings)
                db.refresh(row)
                assert row.state == "succeeded", (row.kind, row.error_code)
                return row.result

            def count(model):
                return db.scalar(select(func.count()).select_from(model))

            for path in [*inputs, None]:
                resource = Resource(organization_id=org.id, title="Qualification")
                db.add(resource)
                db.flush()
                name = path.name if path else "ESA_2024001_AOP.idml"
                raw = (
                    path.read_bytes()
                    if path
                    else (positive_idml if positive_idml is not None else pipeline_idml())
                )
                source, _ = store_idml_artifact(
                    db,
                    organization_id=org.id,
                    original_name=name,
                    data=raw,
                    settings=settings,
                    scanner=scanner,
                )
                assert source.scanner_status == "clamav_clean"
                conversion = job(
                    "idml.process", dict(resource_id=resource.id, idml_artifact_id=source.id)
                )
                snapshot_id = conversion["canonical_snapshot_id"]
                db.refresh(resource)
                payload = dict(
                    resource_id=resource.id,
                    canonical_snapshot_id=snapshot_id,
                    review_version=resource.version,
                )
                evidence = conversion["field_evidence"]
                result = job("autocorrection.preflight", payload)
                assert result["provider_calls"] == 0 and not result["active_snapshot_changed"]
                if path:
                    assert (
                        result["state"] == "abstained" and result["reason"] == "no_eligible_field"
                    )
                    assert (
                        not evidence["bindings"]
                        and count(AutomationGrantRecord) == count(AutomationAttempt) == 0
                    )
                else:
                    assert (
                        evidence["bindings"] == 1
                        and result["reason"] == "batch_authorization_required"
                    )
                    now = utcnow()
                    decision = RevisionEditAuthorization(
                        authorization_id=uuid4(),
                        organization_id=org.id,
                        resource_id=resource.id,
                        snapshot_id=snapshot_id,
                        review_version=resource.version,
                        source_idml_sha256=source.sha256,
                        canonical_sha256=evidence["snapshot_sha256"],
                        catalog_sha256=evidence["catalog_sha256"],
                        decision_sha256=content_digest(
                            {"decision": "isolated synthetic XML test", "scope": payload}
                        ),
                        destination=settings.enrichment_location,
                        status="active",
                        collected_at=now,
                        issued_at=now,
                        expires_at=now + timedelta(hours=1),
                    )
                    file = decisions / f"{decision.authorization_id}.json"
                    payload["authorization_id"] = str(decision.authorization_id)
                    for change in (
                        {"review_version": resource.version + 1},
                        {"snapshot_id": uuid4()},
                        {"organization_id": uuid4()},
                        {"resource_id": uuid4()},
                        {"status": "revoked"},
                        {"catalog_sha256": "f" * 64},
                        {"canonical_sha256": "e" * 64},
                        {"source_idml_sha256": "d" * 64},
                        {
                            "collected_at": now - timedelta(days=2),
                            "issued_at": now - timedelta(days=2),
                            "expires_at": now - timedelta(days=1),
                        },
                    ):
                        file.write_text(decision.model_copy(update=change).model_dump_json())
                        assert job("autocorrection.preflight", payload)["state"] == "refused"
                    legacy = decision.model_dump(
                        mode="json", exclude={"snapshot_id", "review_version"}
                    )
                    legacy["version"] = "autocorrection-batch-authorization-1.0"
                    file.write_text(json.dumps(legacy))
                    assert (
                        job("autocorrection.preflight", payload)["reason"]
                        == "revision_authorization_required"
                    )
                    assert count(AutomationGrantRecord) == count(AutomationAttempt) == 0
                    file.write_text(decision.model_dump_json())
                    result = job("autocorrection.preflight", payload)
                    assert result["state"] == "staged" and result["offline_valid"], result.get(
                        "reason"
                    )
                    attempt = db.get(AutomationAttempt, result["attempt_id"])
                    assert (
                        attempt.candidate["front"]["affiliations"][0]["original_text"]["value"]
                        == "Example University"
                    )
                    assert (
                        hashlib.sha256(attempt.xml_content.encode()).hexdigest()
                        == result["xml_sha256"]
                    )
                    xml = etree.fromstring(
                        attempt.xml_content.encode(),
                        etree.XMLParser(resolve_entities=False, no_network=True),
                    )
                    assert xml.xpath(
                        "//article-meta/aff/institution[@content-type='original']/text()"
                    ) == ["Example University"]
                    assert (
                        result["xml_sha256"] != conversion["xml_sha256"]
                        and result["operation_count"] == 1
                    )
                    assert job("autocorrection.preflight", payload)["attempt_id"] == attempt.id
                    file.write_text(
                        decision.model_copy(update={"status": "revoked"}).model_dump_json()
                    )
                    assert job("autocorrection.preflight", payload)["state"] == "refused"
                    assert count(AutomationGrantRecord) == count(AutomationAttempt) == 1
                    # Same XML head, next editorial revision. Old authority cannot follow it.
                    resource.version += 1
                    payload["review_version"] = resource.version
                    file.write_text(decision.model_dump_json())
                    assert job("autocorrection.preflight", payload)["state"] == "refused"
                    renewed = decision.model_copy(
                        update={
                            "authorization_id": uuid4(),
                            "review_version": resource.version,
                            "decision_sha256": content_digest(payload),
                        }
                    )
                    payload["authorization_id"] = str(renewed.authorization_id)
                    (decisions / f"{renewed.authorization_id}.json").write_text(
                        renewed.model_dump_json()
                    )
                    fresh = job("autocorrection.preflight", payload)
                    assert fresh["state"] == "staged" and fresh["offline_valid"]
                    assert (
                        fresh["attempt_id"] != attempt.id
                        and fresh["xml_sha256"] == result["xml_sha256"]
                    )
                    assert count(AutomationGrantRecord) == count(AutomationAttempt) == 2
                assert (
                    current_canonical_snapshot(
                        db, organization_id=org.id, resource_id=resource.id
                    ).id
                    == snapshot_id
                )
                assert count(AgentRun) == 0
                cases.append(
                    dict(
                        source_sha256=source.sha256,
                        positive_fixture=path is None,
                        state=result["state"],
                        catalog_sha256=evidence["catalog_sha256"],
                        bindings=evidence["bindings"],
                        xml_input_sha256=conversion["xml_sha256"],
                        candidate_xml_sha256=result.get("xml_sha256"),
                        offline_valid=result.get("offline_valid"),
                        provider_calls=0,
                    )
                )
        return {
            "cases": cases,
            "active_head_preserved": True,
            "replay_idempotent": True,
            "revocation_enforced": True,
            "new_review_requires_new_decision": True,
        }
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", type=Path, nargs=2)
    args = parser.parse_args()
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        settings = Settings(
            environment="test",
            artifact_root=root / "artifacts",
            artifact_disk_reserve_bytes=1,
            automation_authorization_root=root / "decisions",
            enrichment_location="vps",
            feature_clamav=True,
            clamav_socket=Path("/run/idml-clamav-vh1/scan.sock"),
            journal_profile_path=Path("profiles/esa-aop-1.1.json"),
        )
        print(json.dumps(qualify(root, args.inputs, settings, build_scanner(settings))))
