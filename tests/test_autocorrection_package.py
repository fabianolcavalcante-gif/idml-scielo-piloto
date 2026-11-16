import copy
import hashlib
import json
from datetime import timedelta
from io import BytesIO
from uuid import uuid4
from zipfile import ZipFile

import pytest
from sqlalchemy import func, select, update

from idml_foundation.autocorrection_models import AutomationAttempt
from idml_foundation.domain.common import content_digest
from idml_foundation.models import Artifact, DomainSnapshot, Resource, ReviewItem
from idml_foundation.pipeline.validation import ValidationReport
from idml_foundation.release.package_builder import AssetPayload, PackageBuilder
from idml_foundation.services.artifacts import store_supporting_artifact
from idml_foundation.services.autocorrection_executor import (
    discard_candidate,
    revoke_extraction_grant,
    stage_autocorrection,
)
from idml_foundation.services.autocorrection_package import (
    _verify_packaging,
    revalidate_candidate_package,
)
from tests.autocorrection_helpers import SyntheticCleanScanner, persisted_data, stage_kwargs
from tests.test_autocorrection_evidence_pipeline import prepared as prepared
from tests.test_autocorrection_evidence_pipeline import provision
from tests.test_package_formal_validation import completed


class PassingOffline:
    """Synthetic report only; real DTD execution is separately exercised below."""

    def validate(self, xml, *, asset_names):
        return ValidationReport(xml_sha256=hashlib.sha256(xml).hexdigest(), valid=True, issues=())


@pytest.fixture
def data(db, settings):
    result = persisted_data(db, settings)
    return with_package_inputs(db, result)


def with_package_inputs(db, result):
    attempt = stage_autocorrection(db, **stage_kwargs(result))
    org = str(result["context"].scope.organization_id)
    pdf = store_supporting_artifact(
        db,
        organization_id=org,
        original_name="article.pdf",
        data=b"%PDF-1.4\nsynthetic-test-only\n%%EOF",
        settings=result["settings"],
        scanner=SyntheticCleanScanner(),
    )
    db.commit()
    result.update(attempt=attempt, pdf=pdf)
    return result


def package(db, data, **overrides):
    return revalidate_candidate_package(
        db,
        **(
            {
                "organization_id": str(data["context"].scope.organization_id),
                "attempt_id": data["attempt"].id,
                "intent": data["intent"],
                "context": data["context"],
                "pdf_artifact_id": data["pdf"].id,
                "pdf_sha256": data["pdf"].sha256,
                "profile": data["profile"],
                "settings": data["settings"],
                "validator": PassingOffline(),
                "executor": completed,
                "clock": lambda: data["now"],
            }
            | overrides
        ),
    )


def test_exact_package_fresh_reports_deterministic_bytes_and_no_promotion(db, data):
    before = copy.deepcopy(data["snapshot"].payload)
    before_count = db.scalar(select(func.count()).select_from(Artifact))
    seen = []

    def execute(payload, spec):
        seen.append((spec.name, payload))
        return completed(payload, spec)

    result = package(db, data, executor=execute)
    assert seen == [("packtools", result.xml), ("spsvalidator", result.package.archive)]
    assert result.xml != data["attempt"].xml_content.encode()  # Exact package href renaming.
    assert result.receipt["xml_sha256"] == result.offline.xml_sha256
    assert result.receipt["package_sha256"] == hashlib.sha256(result.package.archive).hexdigest()
    assert result.receipt["previous_receipt_sha256"] == data["attempt"].receipt_sha256
    assert result.receipt["formal_assessment_sha256"] == content_digest(result.formal)
    assert result.receipt["reasons"] == ["xpm-executor-not-configured"]
    assert result.receipt["state"] == "validation-unavailable"
    assert not result.receipt["promotion_authorized"]
    assert not result.receipt["release_approved"]
    assert not result.receipt["active_snapshot_changed"]
    assert not result.formal["complete"] and not result.formal["ready_for_scielo"]
    assert data["snapshot"].payload == before
    assert db.scalar(select(func.count()).select_from(DomainSnapshot)) == 1
    assert db.scalar(select(func.count()).select_from(Artifact)) == before_count
    assert package(db, data).package.archive == result.package.archive
    with ZipFile(BytesIO(result.package.archive)) as archive:
        for item in result.package.manifest.files:
            payload = archive.read(item.name)
            assert len(payload) == item.size_bytes
            assert hashlib.sha256(payload).hexdigest() == item.sha256
            if item.role == "asset":
                assert payload == data["asset"]
    assert "Example University" not in json.dumps(result.receipt)


def test_actual_offline_validator_runs_again_and_failure_stays_blocked(db, data):
    seen = []
    result = package(
        db,
        data,
        validator=data["validator"],
        executor=lambda *args: seen.append(args),
    )
    assert result.offline.xml_sha256 == hashlib.sha256(result.xml).hexdigest()
    # Minimal synthetic article lacks required publication metadata, intentionally.
    assert not result.offline.valid
    assert result.receipt["state"] == "blocked"
    assert "offline-validation-failed" in result.receipt["reasons"]
    assert not seen


@pytest.mark.parametrize("fault", ["exception", "hash", "inconsistent"])
def test_bad_offline_evidence_redacted_and_no_external_dispatch(db, data, fault):
    seen = []

    class Broken:
        def validate(self, xml, *, asset_names):
            if fault == "exception":
                raise RuntimeError("private secret")
            report = PassingOffline().validate(xml, asset_names=asset_names)
            return report.model_copy(
                update={"xml_sha256": "a" * 64} if fault == "hash" else {"valid": False}
            )

    result = package(db, data, validator=Broken(), executor=lambda *a: seen.append(a))
    assert result.offline is None and not seen
    assert "offline-validation-unavailable" in result.receipt["reasons"]
    assert "private secret" not in json.dumps(result.receipt)


@pytest.mark.parametrize("fault", ["exception", "old_hash", "unavailable"])
def test_external_errors_do_not_reuse_old_assessment(db, data, fault):
    def execute(payload, spec):
        if fault == "exception":
            raise TimeoutError("private credentials")
        return completed(payload, spec).model_copy(update={"candidate_sha256": "b" * 64})

    result = package(db, data, executor=None if fault == "unavailable" else execute)
    assert all(run["status"] == "unavailable" for run in result.formal["external_runs"])
    assert "required-validator-unavailable" in result.receipt["reasons"]
    assert "private credentials" not in json.dumps(result.receipt)


@pytest.mark.parametrize(
    "fault",
    [
        "organization",
        "attempt",
        "intent",
        "disabled",
        "profile",
        "discard",
        "resource_version",
        "grant_revoked",
        "grant_expired",
        "human_state",
        "pdf_id",
        "pdf_hash",
        "pdf_type",
        "pdf_scan",
        "pdf_bytes",
        "asset_scan",
        "idml_bytes",
    ],
)
def test_current_state_and_source_fail_closed_before_external_work(db, data, fault):
    options = {}
    if fault == "organization":
        options["organization_id"] = str(uuid4())
    elif fault == "attempt":
        options["attempt_id"] = str(uuid4())
    elif fault == "intent":
        options["intent"] = data["intent"].model_copy(update={"needs_human": True})
    elif fault == "disabled":
        options["context"] = data["context"].model_copy(update={"enabled": False})
    elif fault == "profile":
        options["profile"] = data["profile"].model_copy(update={"sps_version": "9.9"})
    elif fault == "discard":
        discard_candidate(
            db,
            organization_id=str(data["context"].scope.organization_id),
            attempt_id=data["attempt"].id,
            now=data["now"],
        )
    elif fault == "resource_version":
        db.execute(update(Resource).values(version=2))
    elif fault == "grant_revoked":
        revoke_extraction_grant(
            db,
            organization_id=str(data["context"].scope.organization_id),
            authorization_id=str(data["grants"][0].authorization_id),
            decision_sha256="d" * 64,
        )
    elif fault == "grant_expired":
        options["clock"] = lambda: data["grants"][0].expires_at
    elif fault == "human_state":
        db.add(
            ReviewItem(
                organization_id=str(data["context"].scope.organization_id),
                resource_id=str(data["context"].scope.resource_id),
                base_snapshot_id=data["snapshot"].id,
                field_path="/front/affiliations/0/country_code",
                category="metadata",
                rule_code="test",
                message="private",
            )
        )
        db.flush()
    elif fault in {"pdf_id", "pdf_hash"}:
        options["pdf_artifact_id" if fault == "pdf_id" else "pdf_sha256"] = (
            str(uuid4()) if fault == "pdf_id" else "b" * 64
        )
    elif fault in {"pdf_type", "pdf_scan", "asset_scan"}:
        target = (
            data["pdf"].id
            if fault != "asset_scan"
            else db.scalar(
                select(Artifact.id).where(
                    Artifact.sha256 == hashlib.sha256(data["asset"]).hexdigest()
                )
            )
        )
        db.execute(
            update(Artifact)
            .where(Artifact.id == target)
            .values(
                **(
                    {"media_type": "text/plain"}
                    if fault == "pdf_type"
                    else {"scanner_status": "policy_only"}
                )
            )
        )
    else:
        digest = (
            data["pdf"].sha256
            if fault == "pdf_bytes"
            else (data["context"].scope.source_idml_sha256)
        )
        org = str(data["context"].scope.organization_id)
        (data["settings"].artifact_root / org / digest[:2] / digest).write_bytes(b"tampered")
    seen = []
    with pytest.raises((ValueError, LookupError, PermissionError)):
        package(db, data, executor=lambda *a: seen.append(a), **options)
    assert not seen


@pytest.mark.parametrize(
    "fault", ["text", "doi", "doctype", "processing_instruction", "image", "pdf"]
)
def test_packaging_may_not_silently_change_xml_or_payloads(db, data, monkeypatch, fault):
    original = PackageBuilder.scielo_files

    def changed(self, **kwargs):
        files = list(original(self, **kwargs))
        if fault in {"image", "pdf"}:
            index = 2 if fault == "image" else 1
            files[index] = files[index].model_copy(update={"data": b"altered"})
        else:
            xml = files[0].data
            if fault == "text":
                xml = xml.replace(b"Example University", b"Changed University")
            elif fault == "doi":
                xml = xml.replace(
                    b"</article-meta>",
                    b'<article-id pub-id-type="doi">10.9999/forged</article-id></article-meta>',
                )
            elif fault == "doctype":
                xml = xml.replace(b"JATS", b"DIFFERENT")
            else:
                xml += b"<?private injected?>"
            assert xml != files[0].data
            files[0] = files[0].model_copy(update={"data": xml})
        return tuple(files)

    monkeypatch.setattr(PackageBuilder, "scielo_files", changed)
    with pytest.raises(
        ValueError, match=r"automation_package_(xml_invariant_failure|payload_changed)"
    ):
        package(db, data)


@pytest.mark.parametrize("fault", ["candidate", "xml", "receipt"])
def test_even_rehashed_stored_candidate_is_rederived_from_source(db, data, fault):
    attempt = data["attempt"]
    receipt = copy.deepcopy(attempt.receipt)
    values = {}
    if fault == "candidate":
        changed = copy.deepcopy(attempt.candidate)
        changed["front"]["affiliations"][0]["original_text"]["value"] = "invented university"
        values["candidate"] = changed
        receipt["candidate_sha256"] = content_digest(changed)
    elif fault == "xml":
        values["xml_content"] = attempt.xml_content.replace("Example University", "Invented")
        receipt["xml_sha256"] = hashlib.sha256(values["xml_content"].encode()).hexdigest()
    else:
        receipt["decision_sha256"] = "b" * 64
    values.update(receipt=receipt, receipt_sha256=content_digest(receipt))
    # Test DB has create_all, no migration triggers: simulate corrupted privileged storage.
    db.execute(update(AutomationAttempt).where(AutomationAttempt.id == attempt.id).values(**values))
    db.flush()
    with pytest.raises(ValueError, match=r"automation_(candidate_reconstruction|policy_recheck)"):
        package(db, data)


@pytest.mark.parametrize("fault", ["revocation", "discard", "resource", "pdf"])
def test_changes_during_external_validation_invalidate_result(db, data, fault):
    changed = False

    def execute(payload, spec):
        nonlocal changed
        if not changed:
            changed = True
            org = str(data["context"].scope.organization_id)
            if fault == "revocation":
                revoke_extraction_grant(
                    db,
                    organization_id=org,
                    authorization_id=str(data["grants"][0].authorization_id),
                    decision_sha256="d" * 64,
                )
            elif fault == "discard":
                discard_candidate(
                    db,
                    organization_id=org,
                    attempt_id=data["attempt"].id,
                    now=data["now"],
                )
            elif fault == "resource":
                db.execute(update(Resource).values(version=2))
            else:
                digest = data["pdf"].sha256
                path = data["settings"].artifact_root / org / digest[:2] / digest
                path.write_bytes(b"tampered")
        return completed(payload, spec)

    with pytest.raises(ValueError):
        package(db, data, executor=execute)


@pytest.mark.parametrize("fault", ["naive_start", "naive_end", "backwards", "timeout"])
def test_clock_boundaries_and_cycle_duration_are_enforced(db, data, fault):
    started = data["now"]
    ended = started
    if fault == "naive_start":
        started = started.replace(tzinfo=None)
    elif fault == "naive_end":
        ended = ended.replace(tzinfo=None)
    elif fault == "backwards":
        ended -= timedelta(seconds=1)
    else:
        ended += timedelta(minutes=20)
    times = iter([started, ended])
    with pytest.raises(ValueError):
        package(db, data, clock=lambda: next(times))


def test_size_limit_rejects_before_packaging(db, data):
    settings = data["settings"].model_copy(update={"upload_max_bytes": len(data["idml"])})
    with pytest.raises(ValueError, match="automation_package_too_large"):
        package(db, data, settings=settings)


@pytest.mark.parametrize("revoke_during_run", [False, True])
def test_field_catalog_batch_grants_staging_and_package_form_one_chain(
    db, prepared, revoke_during_run
):
    issued = provision(db, prepared)
    prepared["intent"] = issued.intent
    prepared["context"] = prepared["context"].model_copy(update={"findings": issued.findings})
    data = with_package_inputs(db, prepared)

    def execute(payload, spec):
        if revoke_during_run:
            auth = data["authorization"].model_copy(update={"status": "revoked"})
            data["authorization_file"].write_text(auth.model_dump_json(), encoding="utf-8")
        return completed(payload, spec)

    if revoke_during_run:
        with pytest.raises(ValueError, match="batch_authorization_unavailable_or_invalid"):
            package(db, data, executor=execute)
    else:
        result = package(db, data, executor=execute)
        assert len(data["attempt"].receipt["operations"]) == 3
        assert result.receipt["candidate_sha256"] == data["attempt"].receipt["candidate_sha256"]
        assert not result.receipt["promotion_authorized"]


@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "formula",
        "table",
        "xref",
        "reference",
        "missing_file",
        "renamed_file",
        "fuzzy_asset",
    ],
)
def test_package_invariants_preserve_scientific_structures_and_exact_assets(fault):
    xml = (
        b'<article xmlns:xlink="http://www.w3.org/1999/xlink" '
        b'xmlns:mml="http://www.w3.org/1998/Math/MathML">'
        b'<body><p><xref ref-type="bibr" rid="B1">1</xref></p>'
        b"<table-wrap><table><tr><td>42.5</td></tr></table></table-wrap>"
        b"<disp-formula><mml:math><mml:mi>x</mml:mi></mml:math></disp-formula>"
        b'<fig><graphic xlink:href="source-gf01.jpg"/></fig></body>'
        b'<back><ref-list><ref id="B1"><mixed-citation>Reference text</mixed-citation>'
        b"</ref></ref-list></back></article>"
    )
    assets = (AssetPayload(source_name="source-gf01.jpg", data=b"image", media_type="image/jpeg"),)
    files = list(
        PackageBuilder().scielo_files(
            package_stem="candidate",
            xml=xml,
            pdf=b"%PDF-bytes",
            assets=assets,
        )
    )
    replacements = {
        "formula": (b"<mml:mi>x", b"<mml:mi>y"),
        "table": (b"<td>42.5", b"<td>42.6"),
        "xref": (b'rid="B1"', b'rid="B9"'),
        "reference": (b"Reference text", b"Invented text"),
    }
    if fault in replacements:
        old, new = replacements[fault]
        files[0] = files[0].model_copy(update={"data": files[0].data.replace(old, new)})
    elif fault == "missing_file":
        files.pop()
    elif fault == "renamed_file":
        files[2] = files[2].model_copy(update={"name": "unexpected.jpg"})
    elif fault == "fuzzy_asset":
        assets = (assets[0].model_copy(update={"source_name": "different-gf01.jpg"}),)
    if fault == "none":
        assert (
            _verify_packaging(
                xml, tuple(files), assets, package_stem="candidate", pdf=b"%PDF-bytes"
            )
            == files[0].data
        )
    else:
        with pytest.raises(ValueError, match="automation_package_"):
            _verify_packaging(
                xml, tuple(files), assets, package_stem="candidate", pdf=b"%PDF-bytes"
            )


def test_unresolved_graphic_is_not_repaired_by_package_filename_heuristics(db, settings):
    data = persisted_data(db, settings)
    data["intent"] = data["intent"].model_copy(
        update={"operations": (data["intent"].operations[0],)}
    )
    data = with_package_inputs(db, data)
    with pytest.raises(ValueError, match="automation_package_requires_exact_asset_mapping"):
        package(db, data)
