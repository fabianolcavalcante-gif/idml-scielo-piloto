import asyncio
import subprocess
import sys
from contextlib import aclosing
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from idml_foundation.ingest import upload_admission as admission
from idml_foundation.ingest.http_upload import bounded_upload
from tests.test_phase7_v12_http_upload import consume, multipart, temporary_files  # noqa: F401


def test_slots_shared_with_another_process_and_reusable(settings):
    script = """
import sys
from fastapi import HTTPException
from idml_foundation.ingest.upload_admission import upload_admission
from idml_foundation.settings import Settings
try:
    with upload_admission(Settings(artifact_root=sys.argv[1])):
        print('admitted')
except HTTPException as exc:
    print(exc.status_code)
"""

    def child():
        return subprocess.run(  # noqa: S603 -- fixed interpreter/script, isolated test directory
            [sys.executable, "-c", script, str(settings.artifact_root)],
            capture_output=True,
            text=True,
            check=True,
            timeout=15,
        ).stdout.strip()

    with admission.upload_admission(settings):
        assert child() == "503"
    assert child() == "admitted"
    assert (settings.artifact_root / ".upload-admission/slot-0.lock").exists()


def test_configured_slots_and_release_on_error(settings):
    settings.upload_max_concurrency = 2
    with admission.upload_admission(settings), admission.upload_admission(settings):
        with pytest.raises(HTTPException) as error:
            with admission.upload_admission(settings):
                pytest.fail("third upload admitted")
        assert error.value.status_code == 503
        assert error.value.headers == {"Retry-After": "5"}
    with pytest.raises(RuntimeError), admission.upload_admission(settings):
        raise RuntimeError("downstream failure")
    with admission.upload_admission(settings):
        pass


def test_disk_probe_failure_releases_lock(settings, monkeypatch):
    original = admission.shutil.disk_usage

    def failed(_):
        raise OSError("unavailable filesystem")

    monkeypatch.setattr(admission.shutil, "disk_usage", failed)
    with pytest.raises(HTTPException) as error, admission.upload_admission(settings):
        pytest.fail("disk probe failure admitted")
    assert error.value.status_code == 503
    monkeypatch.setattr(admission.shutil, "disk_usage", original)
    with admission.upload_admission(settings):
        pass


@pytest.mark.parametrize("reason", ["busy", "disk"])
def test_admission_rejects_before_spooling(settings, temporary_files, monkeypatch, reason):  # noqa: F811
    def attempt():
        with pytest.raises(HTTPException) as error:
            consume(settings, multipart(b"x" * (2 * 1024**2)))
        assert error.value.status_code == 503
        assert temporary_files == []

    if reason == "busy":
        with admission.upload_admission(settings):
            attempt()
    else:
        monkeypatch.setattr(admission.shutil, "disk_usage", lambda _: SimpleNamespace(free=0))
        attempt()


@pytest.mark.parametrize("free_offset", [-1, 0])
def test_disk_headroom_boundary(settings, monkeypatch, free_offset):
    required = settings.upload_temp_reserve_bytes + settings.upload_max_bytes
    monkeypatch.setattr(
        admission.shutil, "disk_usage", lambda _: SimpleNamespace(free=required + free_offset)
    )
    if free_offset < 0:
        with pytest.raises(HTTPException) as error:
            with admission.upload_admission(settings):
                pytest.fail("low disk admitted")
        assert error.value.status_code == 503
    else:
        with admission.upload_admission(settings):
            pass
    monkeypatch.setattr(admission.shutil, "disk_usage", lambda _: SimpleNamespace(free=required))
    with admission.upload_admission(settings):
        pass


def test_unavailable_filesystem_fails_closed(settings):
    settings.artifact_root.write_text("occupied", encoding="utf-8")
    with pytest.raises(HTTPException) as error:
        with admission.upload_admission(settings):
            pytest.fail("unavailable filesystem admitted")
    assert error.value.status_code == 503


@pytest.mark.parametrize("kind", ["idle", "total", "cancel"])
def test_slow_or_cancelled_stream_closes_spool_and_releases_slot(
    settings,
    temporary_files,  # noqa: F811
    kind,
):
    settings.upload_idle_timeout_seconds = 0.1 if kind == "idle" else 1
    settings.upload_total_timeout_seconds = 0.1 if kind == "total" else 3
    first = True

    async def receive():
        nonlocal first
        if first:
            first = False
            return {
                "type": "http.request",
                "body": multipart(b"x" * (2 * 1024**2), ending=False),
                "more_body": True,
            }
        if kind == "cancel":
            raise asyncio.CancelledError()
        await asyncio.sleep(0.02 if kind == "total" else 2)
        return {"type": "http.request", "body": b"x", "more_body": True}

    request = Request(
        {
            "type": "http",
            "headers": [(b"content-type", b"multipart/form-data; boundary=testboundary")],
        },
        receive,
    )

    async def run():
        async with aclosing(bounded_upload(request, settings)) as stream:
            await anext(stream)

    if kind == "cancel":
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(run())
    else:
        with pytest.raises(HTTPException) as error:
            asyncio.run(run())
        assert error.value.status_code == 408
    assert temporary_files[0]._rolled
    assert temporary_files[0].closed
    with admission.upload_admission(settings):
        pass


def test_timeout_does_not_cancel_downstream_work(settings, temporary_files):  # noqa: F811
    settings.upload_total_timeout_seconds = 0.05

    async def receive():
        return {"type": "http.request", "body": multipart(), "more_body": False}

    request = Request(
        {
            "type": "http",
            "headers": [(b"content-type", b"multipart/form-data; boundary=testboundary")],
        },
        receive,
    )

    async def run():
        async with aclosing(bounded_upload(request, settings)) as stream:
            file = await anext(stream)
            await asyncio.sleep(0.1)
            assert await file.read() == b"synthetic"
            with pytest.raises(HTTPException), admission.upload_admission(settings):
                pytest.fail("slot released before consumer finished")

    asyncio.run(run())
