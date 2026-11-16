"""Queue-to-diagnostic integration; external executor results here are synthetic."""

import hashlib
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from idml_foundation.models import Organization, Resource
from idml_foundation.services.artifacts import store_idml_artifact, store_supporting_artifact
from idml_foundation.services.jobs import create_job
from idml_foundation.services.validation_diagnosis import describe_validation
from idml_foundation.settings import Settings
from idml_foundation.worker import process_job
from tests.autocorrection_helpers import SyntheticCleanScanner
from tests.phase3_helpers import synthetic_idml
from tests.test_package_formal_validation import completed
from tests.test_xpm_execution import execution

ROOT = Path(__file__).parents[1]


def configured(settings):
    return settings.model_copy(
        update=dict(
            validator_socket=Path("/socket/modern.sock"),
            xpm_socket=Path("/socket/xpm.sock"),
            validator_scoped_authorities=True,
            validator_registry_path=ROOT / "config/validator-registry-vh1-composed.json",
            journal_profile_path=ROOT / "profiles/esa-aop-1.1.json",
        )
    )


def queued(db, factory, settings):
    org = Organization(slug="worker-xpm-" + uuid4().hex, name="Synthetic")
    db.add(org)
    db.flush()
    resource = Resource(organization_id=org.id, title="Synthetic")
    db.add(resource)
    db.flush()
    source, _ = store_idml_artifact(
        db,
        organization_id=org.id,
        settings=settings,
        original_name="ESA_2024001_AOP.idml",
        data=synthetic_idml(),
        scanner=SyntheticCleanScanner(),
    )
    pdf = store_supporting_artifact(
        db,
        organization_id=org.id,
        settings=settings,
        original_name="article.pdf",
        data=b"%PDF-1.4\nsynthetic-only",
        scanner=SyntheticCleanScanner(),
    )
    image = store_supporting_artifact(
        db,
        organization_id=org.id,
        settings=settings,
        original_name="Figure 1.jpg",
        data=b"\xff\xd8\xffsynthetic-only",
        scanner=SyntheticCleanScanner(),
    )
    job, _ = create_job(
        db,
        organization_id=org.id,
        kind="idml.process",
        idempotency_key=uuid4().hex,
        payload=dict(resource_id=resource.id, idml_artifact_id=source.id),
        correlation_id=uuid4().hex,
        actor_id="synthetic",
    )
    db.commit()
    process_job(job.id, factory, settings=settings)
    db.refresh(job)
    assert job.state == "succeeded"
    package, _ = create_job(
        db,
        organization_id=org.id,
        kind="scielo.package",
        idempotency_key=uuid4().hex,
        payload=dict(
            resource_id=resource.id,
            canonical_snapshot_id=job.result["canonical_snapshot_id"],
            idml_artifact_id=source.id,
            pdf_artifact_id=pdf.id,
            asset_artifact_ids=[image.id],
        ),
        correlation_id=uuid4().hex,
        actor_id="synthetic",
    )
    db.commit()
    return package, source


@pytest.mark.parametrize(
    "mode",
    [
        "completed",
        "error",
        "warning",
        "queries",
        "failure",
        "wrong_scope",
        "wrong_package",
        "disabled",
    ],
)
def test_worker_persists_bound_xpm_result_and_diagnosis(
    db, session_factory, settings, monkeypatch, mode
):
    settings = configured(settings)
    modern_calls, xpm_calls, scopes = [], [], []

    class Modern:
        def __init__(self, path, *, scope):
            assert path == settings.validator_socket
            self.scope = scope.copy()
            self.evidence = {}
            scopes.append(self.scope)

        def __call__(self, payload, spec):
            key = "xml_sha256" if spec.name == "packtools" else "package_sha256"
            assert hashlib.sha256(payload).hexdigest() == self.scope[key]
            modern_calls.append(spec.name)
            return completed(payload, spec)

    class Xpm:
        def __init__(self, path):
            assert path == settings.xpm_socket

        def __call__(self, package, scope):
            assert scope == scopes[0]
            xpm_calls.append(scope.copy())
            if mode == "failure":
                raise RuntimeError("private-synthetic-executor-message")
            selected = scope.copy()
            if mode == "wrong_scope":
                selected["resource_id"] = str(uuid4())
            return execution(
                b"other" if mode == "wrong_package" else package,
                selected,
                errors=int(mode == "error"),
                warnings=int(mode == "warning"),
                queries=mode != "queries",
            )

    monkeypatch.setattr("idml_foundation.worker.ScopedValidatorExecutor", Modern)
    monkeypatch.setattr("idml_foundation.worker.XpmSocketExecutor", Xpm)
    if mode == "disabled":
        settings.xpm_socket = None
    job, source = queued(db, session_factory, settings)
    process_job(job.id, session_factory, settings=settings)
    db.refresh(job)
    assert job.state == "succeeded"
    assert modern_calls == ["packtools", "spsvalidator"]
    formal = job.result["formal_validation"]
    assert formal["xpm"]["status"] == (
        "completed" if mode in {"completed", "error", "warning", "queries"} else "unavailable"
    )
    assert not formal["ready_for_scielo"] and not formal["production_activation_authorized"]
    assert "private-synthetic" not in str(job.result)
    if mode != "disabled":
        assert xpm_calls[0]["organization_id"] == job.organization_id
        assert xpm_calls[0]["source_idml_sha256"] == source.sha256
        assert xpm_calls[0]["package_sha256"] == job.result["package_sha256"]
    else:
        assert not xpm_calls
    assert describe_validation(job.result)
    process_job(job.id, session_factory, settings=settings)
    assert modern_calls == ["packtools", "spsvalidator"]  # Successful job replay is inert.


@pytest.mark.parametrize(
    "missing",
    [
        "validator_socket",
        "validator_registry_path",
        "journal_profile_path",
        "validator_scoped_authorities",
    ],
)
def test_xpm_configuration_requires_scoped_modern_validation(settings, missing):
    values = configured(settings).model_dump()
    values[missing] = False if missing == "validator_scoped_authorities" else None
    with pytest.raises(ValidationError):
        Settings.model_validate(values)


def test_payload_cannot_enable_or_redirect_xpm(db, session_factory, settings, monkeypatch):
    calls = []
    monkeypatch.setattr("idml_foundation.worker.XpmSocketExecutor", lambda p: calls.append(p))
    job, _ = queued(db, session_factory, settings)
    job.payload = job.payload | dict(
        xpm_socket="/untrusted.sock", expected_scope={"organization_id": str(uuid4())}
    )
    db.commit()
    process_job(job.id, session_factory, settings=settings)
    db.refresh(job)
    assert job.state == "succeeded" and not calls
    assert job.result["formal_validation"]["xpm"]["status"] == "unavailable"


def test_human_review_uses_same_configured_profile_as_worker(db, settings, monkeypatch):
    from types import SimpleNamespace

    from fastapi import HTTPException

    from idml_foundation.routers.reviews import decide_review
    from idml_foundation.schemas import ReviewDecisionCreate

    settings = configured(settings)
    seen = []

    def check(_db, **kwargs):
        seen.append(kwargs["profile"].profile_id)
        raise LookupError("synthetic missing review")

    monkeypatch.setattr("idml_foundation.routers.reviews.apply_review_decision", check)
    with pytest.raises(HTTPException) as error:
        decide_review(
            "synthetic",
            ReviewDecisionCreate(
                expected_version=1, action="reject", justification="synthetic review"
            ),
            db,
            settings,
            "synthetic",
            SimpleNamespace(organization_id=str(uuid4()), user=SimpleNamespace(id=str(uuid4()))),
        )
    assert error.value.status_code == 404
    assert seen == ["esa-aop-1.1.0"]


@pytest.mark.parametrize("kind", ["modern", "xpm"])
def test_supervised_service_limits_and_private_socket(kind):
    from ops.install_worker_validators import unit

    text = unit(kind, Path("/opt/idml-platform/releases/worker-v1"))
    assert "Restart=on-failure" in text and "RuntimeDirectoryPreserve=yes" in text
    assert f"--clean-socket {kind}" in text
    assert "MemoryMax=512M" in text and "NoNewPrivileges=true" in text
    assert "--uid 10001" in text and f"/run/idml-{kind}-vh1/validator.sock" in text


@pytest.mark.parametrize(
    "path", ["/tmp/untrusted", "/opt/idml-platform/releases/bad\nExecStart=bad"]
)
def test_service_source_path_cannot_inject_directives(path):
    from ops.install_worker_validators import unit

    with pytest.raises(ValueError):
        unit("xpm", Path(path))


@pytest.mark.parametrize(
    "case", ["socket", "absent", "file", "symlink", "owner", "group", "parent"]
)
def test_service_cleanup_refuses_untrusted_paths(monkeypatch, case):
    import stat
    from types import SimpleNamespace

    from ops import install_worker_validators as installer

    removed = []

    class Entry:
        def __init__(self, parent=False):
            self.parent = parent

        def __truediv__(self, name):
            assert name == "validator.sock"
            return Entry()

        def lstat(self):
            if self.parent:
                return SimpleNamespace(
                    st_mode=stat.S_IFDIR | (0o777 if case == "parent" else 0o755), st_uid=0
                )
            if case == "absent":
                raise FileNotFoundError
            kind = {"file": stat.S_IFREG, "symlink": stat.S_IFLNK}.get(case, stat.S_IFSOCK)
            return SimpleNamespace(
                st_mode=kind | 0o660,
                st_uid=int(case == "owner"),
                st_gid=0 if case == "group" else 10001,
            )

        def unlink(self):
            removed.append(True)

    monkeypatch.setattr(installer.os, "geteuid", lambda: 0, raising=False)
    monkeypatch.setattr(installer, "Path", lambda value: Entry(parent=True))
    if case in {"socket", "absent"}:
        installer.clean_socket("xpm")
        assert bool(removed) == (case == "socket")
    else:
        with pytest.raises(ValueError):
            installer.clean_socket("xpm")
        assert not removed
