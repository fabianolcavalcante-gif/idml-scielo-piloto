import asyncio
from contextlib import aclosing

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from idml_foundation.ingest.http_upload import bounded_upload


def multipart(content=b"synthetic", *, name="upload", ending=True):
    value = (
        f'--testboundary\r\nContent-Disposition: form-data; name="{name}"; '
        'filename="article.idml"\r\nContent-Type: application/octet-stream\r\n\r\n'
    ).encode()
    return value + content + (b"\r\n--testboundary--\r\n" if ending else b"")


@pytest.fixture
def temporary_files(monkeypatch):
    from starlette import formparsers

    original = formparsers.SpooledTemporaryFile
    opened = []

    def tracked(*args, **kwargs):
        file = original(*args, **kwargs)
        opened.append(file)
        return file

    monkeypatch.setattr(formparsers, "SpooledTemporaryFile", tracked)
    yield opened
    assert all(file.closed for file in opened)


def consume(settings, data, *, headers=(), chunk=17, interrupt=None):
    position = 0
    reads = 0

    async def receive():
        nonlocal position, reads
        reads += 1
        if interrupt and position >= len(data):
            if interrupt == "cancel":
                raise asyncio.CancelledError()
            return {"type": "http.disconnect"}
        body = data[position : position + chunk]
        position += len(body)
        return {
            "type": "http.request",
            "body": body,
            "more_body": bool(interrupt) or position < len(data),
        }

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/artifacts/idml",
            "headers": [(b"content-type", b"multipart/form-data; boundary=testboundary"), *headers],
        },
        receive,
    )

    async def run():
        async with aclosing(bounded_upload(request, settings)) as upload:
            file = await anext(upload)
            result = await file.read()
            return result, reads

    return asyncio.run(run())


@pytest.mark.parametrize("chunk", [1, 17, 65536])
@pytest.mark.parametrize("declared", [True, False])
def test_valid_stream_at_exact_file_limit(settings, temporary_files, chunk, declared):
    content = b"x" * 256
    settings.upload_max_bytes = len(content)
    data = multipart(content)
    headers = [(b"content-length", str(len(data)).encode())] if declared else []
    result, _ = consume(settings, data, headers=headers, chunk=chunk)
    assert result == content


@pytest.mark.parametrize(
    "headers",
    [
        [(b"content-length", b"-1")],
        [(b"content-length", b"abc")],
        [(b"content-length", b"1, 2")],
        [(b"content-length", b"1"), (b"content-length", b"1")],
        [(b"content-length", b"1"), (b"transfer-encoding", b"chunked")],
    ],
)
def test_invalid_framing_is_rejected_before_spooling(settings, temporary_files, headers):
    with pytest.raises(HTTPException) as error:
        consume(settings, multipart(), headers=headers)
    assert error.value.status_code == 400
    assert temporary_files == []


@pytest.mark.parametrize("kind", ["file", "body", "declared", "headers"])
def test_limit_violations_are_413_and_close_files(settings, temporary_files, kind):
    settings.upload_max_bytes = 256
    data = multipart(b"x" * 257)
    headers = []
    if kind == "body":
        data = b"x" * (65536 + 257)
    elif kind == "declared":
        headers = [(b"content-length", b"1000000")]
    elif kind == "headers":
        data = multipart(name="x" * 4100)
    with pytest.raises(HTTPException) as error:
        consume(settings, data, headers=headers, chunk=len(data))
    assert error.value.status_code == 413


@pytest.mark.parametrize("offset", [-1, 1])
def test_actual_length_must_match_header(settings, temporary_files, offset):
    data = multipart()
    with pytest.raises(HTTPException) as error:
        consume(settings, data, headers=[(b"content-length", str(len(data) + offset).encode())])
    assert error.value.status_code == 400


@pytest.mark.parametrize(
    "kind", ["wrong_name", "multiple_files", "field", "incomplete", "malformed"]
)
def test_multipart_contract_and_completion(settings, temporary_files, kind):
    data = multipart(name="unexpected")
    if kind == "multiple_files":
        data = multipart().replace(b"--testboundary--\r\n", multipart())
    elif kind == "field":
        data = multipart().replace(b'; filename="article.idml"', b"")
    elif kind == "incomplete":
        data = multipart(ending=False)
    elif kind == "malformed":
        data = b"not-a-multipart-request"
    with pytest.raises(HTTPException) as error:
        consume(settings, data)
    assert error.value.status_code == 400


@pytest.mark.parametrize("interrupt", ["disconnect", "cancel"])
def test_interrupted_disk_spooling_is_closed(settings, temporary_files, interrupt):
    data = multipart(b"x" * (2 * 1024**2), ending=False)
    expected = asyncio.CancelledError if interrupt == "cancel" else HTTPException
    with pytest.raises(expected):
        consume(settings, data, chunk=65536, interrupt=interrupt)
    assert len(temporary_files) == 1
    assert temporary_files[0]._rolled is True


def test_real_file_spooling_success_is_closed(settings, temporary_files):
    content = b"x" * (2 * 1024**2)
    assert consume(settings, multipart(content), chunk=65536)[0] == content
    assert temporary_files[0]._rolled is True


def test_authentication_precedes_multipart_processing(client, temporary_files):
    response = client.post(
        "/v1/artifacts/idml",
        content=b"not a multipart body",
        headers={"Content-Type": "multipart/form-data; boundary=testboundary"},
    )
    assert response.status_code == 401
    assert temporary_files == []


def test_openapi_preserves_file_upload_contract(client):
    schema = client.get("/openapi.json").json()
    for path in ("/v1/artifacts/idml", "/v1/artifacts/assets"):
        body = schema["paths"][path]["post"]["requestBody"]
        assert body["required"] is True
        assert (
            body["content"]["multipart/form-data"]["schema"]["properties"]["upload"]["format"]
            == "binary"
        )
