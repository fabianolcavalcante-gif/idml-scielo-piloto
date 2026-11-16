import hashlib
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from idml_foundation.autocorrection_models import AutomationGrantRecord
from idml_foundation.domain.common import content_digest
from idml_foundation.models import DomainSnapshot, Organization, Resource
from idml_foundation.pipeline.profile import load_profile
from idml_foundation.pipeline.service import DeterministicPipeline
from idml_foundation.services.artifacts import store_idml_artifact
from idml_foundation.services.jobs import create_job
from idml_foundation.services.scoped_validator_transport import ScopedValidatorExecutor
from idml_foundation.services.snapshots import load_snapshot, store_snapshot
from idml_foundation.services.validation_diagnosis import describe_validation
from idml_foundation.services.xpm_socket import XpmSocketExecutor
from idml_foundation.worker import process_job
from tests.autocorrection_helpers import SyntheticCleanScanner, persisted_data
from tests.test_autocorrection_evidence_pipeline import pipeline_idml
from tests.test_autocorrection_package import package, with_package_inputs
from tests.test_package_formal_validation import completed
from tests.test_restored_package_validation import prepare, restore
from tests.test_worker_xpm_integration import configured
from tests.test_xpm_execution import execution


@pytest.mark.parametrize("historical", [False, True])
def test_job_preserves_xml_and_replays_the_same_revision(db, session_factory, settings, historical):
    settings = configured(settings)
    org = Organization(slug="evidence", name="Evidence")
    db.add(org)
    db.flush()
    resource = Resource(organization_id=org.id, title="Example")
    db.add(resource)
    db.flush()
    raw = pipeline_idml()
    source, _ = store_idml_artifact(
        db,
        organization_id=org.id,
        settings=settings,
        original_name="ESA_2024001_AOP.idml",
        data=raw,
        scanner=SyntheticCleanScanner(),
    )
    profile = load_profile(settings.journal_profile_path)
    baseline = DeterministicPipeline(settings=settings, profile=profile).run(
        raw, logical_name=source.original_name
    )
    if historical:
        store_snapshot(
            db,
            organization_id=org.id,
            resource_id=resource.id,
            revision=1,
            document=baseline.canonical,
            source_artifact_id=source.id,
        )
    results = []
    for _ in range(2):
        job, _ = create_job(
            db,
            organization_id=org.id,
            kind="idml.process",
            idempotency_key=uuid4().hex,
            payload={"resource_id": resource.id, "idml_artifact_id": source.id},
            correlation_id=uuid4().hex,
            actor_id="test",
        )
        db.commit()
        process_job(job.id, session_factory, settings=settings)
        db.refresh(job)
        assert job.state == "succeeded"
        results.append(job.result)
    first, repeat = results
    assert first["field_evidence"] == repeat["field_evidence"]
    assert first["canonical_snapshot_id"] == repeat["canonical_snapshot_id"]
    assert repeat["deduplication"]["canonical_snapshot_reused"]
    assert first["xml_sha256"] == hashlib.sha256(baseline.xml).hexdigest()
    snapshot = db.get(DomainSnapshot, first["canonical_snapshot_id"])
    assert snapshot.revision == 1

    def diagnosis(result):
        return [
            r
            for r in describe_validation(result)["items"]
            if r["code"].startswith("field-evidence-")
        ]

    if historical:
        assert first["field_evidence"] == {"status": "historical_snapshot_unprepared"}
        assert load_snapshot(snapshot) == baseline.canonical
        assert diagnosis(first)[0]["code"] == "field-evidence-historical"
    else:
        receipt = first["field_evidence"]
        assert receipt["status"] == "prepared" and receipt["bindings"] >= 1
        assert receipt["snapshot_sha256"] == content_digest(load_snapshot(snapshot))
        assert receipt["source_sha256"] == source.sha256
        assert diagnosis(first)[0]["report_sha256"] == receipt["catalog_sha256"]
        assert diagnosis(first | {"xml_sha256": "0" * 64})[0]["status"] == "unavailable"
    assert db.scalar(select(func.count()).select_from(AutomationGrantRecord)) == 0


@pytest.fixture
def observed_calls(monkeypatch):
    calls = []

    def modern(self, payload, spec):
        calls.append((spec.name, self.scope, hashlib.sha256(payload).hexdigest()))
        return completed(payload, spec)

    def xpm(self, payload, scope):
        calls.append(("xpm", scope, hashlib.sha256(payload).hexdigest()))
        return execution(payload, scope)

    monkeypatch.setattr(ScopedValidatorExecutor, "__call__", modern)
    monkeypatch.setattr(XpmSocketExecutor, "__call__", xpm)
    return calls


def check_observations(calls, xml_sha, package_sha):
    assert [(name, digest) for name, _, digest in calls] == [
        ("packtools", xml_sha),
        ("spsvalidator", package_sha),
        ("xpm", package_sha),
    ]
    assert all(scope == calls[0][1] for _, scope, _ in calls)
    assert calls[0][1]["xml_sha256"] == xml_sha
    assert calls[0][1]["package_sha256"] == package_sha


def test_candidate_validators_receive_rebuilt_bytes(db, settings, observed_calls):
    candidate = with_package_inputs(db, persisted_data(db, settings))
    result = package(db, candidate, settings=configured(candidate["settings"]), executor=None)
    check_observations(observed_calls, result.receipt["xml_sha256"], result.package.package_sha256)


def test_restore_validators_receive_restored_bytes(db, settings, observed_calls):
    restoration = prepare(db, settings)
    row = restore(
        db,
        restoration,
        settings=configured(restoration["settings"]),
        executor=None,
        xpm_executor=None,
    )
    scope = row.receipt["scope"]
    check_observations(observed_calls, scope["xml_sha256"], scope["package_sha256"])
