"""Bound multipart input before spooling; close every owned file on all exits."""

import asyncio
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from python_multipart.exceptions import MultipartParseError
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser
from starlette.requests import ClientDisconnect

from idml_foundation.ingest.upload_admission import upload_admission
from idml_foundation.settings import Settings, get_settings

MULTIPART_OVERHEAD_BYTES = 64 * 1024
MAX_PART_HEADER_BYTES = 4 * 1024
UPLOAD_OPENAPI = {
    "requestBody": {
        "required": True,
        "content": {
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "required": ["upload"],
                    "additionalProperties": False,
                    "properties": {"upload": {"type": "string", "format": "binary"}},
                }
            }
        },
    }
}


def declared_length(request: Request, limit: int) -> int | None:
    values = request.headers.getlist("content-length")
    if not values:
        return None
    value = values[0]
    if (
        len(values) != 1
        or not value.isascii()
        or not value.isdecimal()
        or len(value) > 20
        or "transfer-encoding" in request.headers
    ):
        raise HTTPException(400, "invalid upload Content-Length")
    length = int(value)
    if length > limit:
        raise HTTPException(413, "upload body exceeds size limit")
    return length


class BoundedMultipartParser(MultiPartParser):
    def __init__(
        self, request: Request, stream: AsyncGenerator[bytes, None], file_limit: int
    ) -> None:
        super().__init__(request.headers, stream, max_files=1, max_fields=0)
        self.file_limit = file_limit
        self.file_bytes = 0
        self.header_bytes = 0
        self.completed = False
        self.owned: list[UploadFile] = []

    def _header(self, size: int) -> None:
        self.header_bytes += size
        if self.header_bytes > MAX_PART_HEADER_BYTES:
            raise HTTPException(413, "multipart headers exceed size limit")

    def on_header_field(self, data: bytes, start: int, end: int) -> None:
        self._header(end - start)
        super().on_header_field(data, start, end)

    def on_header_value(self, data: bytes, start: int, end: int) -> None:
        self._header(end - start)
        super().on_header_value(data, start, end)

    def on_headers_finished(self) -> None:
        super().on_headers_finished()
        if self._current_part.file is not None:
            self.owned.append(self._current_part.file)
        if self._current_part.field_name != "upload":
            raise HTTPException(400, "expected one upload file")

    def on_part_data(self, data: bytes, start: int, end: int) -> None:
        self.file_bytes += end - start
        if self.file_bytes > self.file_limit:
            raise HTTPException(413, "upload file exceeds size limit")
        super().on_part_data(data, start, end)

    def on_end(self) -> None:
        self.completed = True

    def close_files(self) -> None:
        # Synchronous close also works during cancellation, where awaiting can fail.
        for upload in self.owned:
            upload.file.close()


async def bounded_upload(
    request: Request, settings: Annotated[Settings, Depends(get_settings)]
) -> AsyncIterator[UploadFile]:
    limit = settings.upload_max_bytes + MULTIPART_OVERHEAD_BYTES
    declared = declared_length(request, limit)
    content_type = request.headers.get("content-type", "")
    if (
        len(content_type) > 512
        or content_type.split(";", 1)[0].strip().lower() != "multipart/form-data"
    ):
        raise HTTPException(400, "expected bounded multipart/form-data")

    async def chunks() -> AsyncGenerator[bytes, None]:
        total = 0
        stream = request.stream()
        while True:
            try:
                chunk = await asyncio.wait_for(anext(stream), settings.upload_idle_timeout_seconds)
            except StopAsyncIteration:
                break
            total += len(chunk)
            if total > limit:
                raise HTTPException(413, "upload body exceeds size limit")
            if declared is not None and total > declared:
                raise HTTPException(400, "upload length does not match Content-Length")
            # Keep parser callbacks and temporary write queues bounded even if the
            # ASGI server provides a single large receive message.
            for offset in range(0, len(chunk), 64 * 1024):
                yield chunk[offset : offset + 64 * 1024]
        if declared is not None and total != declared:
            raise HTTPException(400, "upload length does not match Content-Length")

    parser = BoundedMultipartParser(request, chunks(), settings.upload_max_bytes)
    with upload_admission(settings):
        try:
            try:
                async with asyncio.timeout(settings.upload_total_timeout_seconds):
                    form = await parser.parse()
            except TimeoutError as exc:
                raise HTTPException(408, "upload reception timed out") from exc
            if not parser.completed:
                raise HTTPException(400, "incomplete multipart upload")
            files = form.getlist("upload")
            if len(files) != 1 or not isinstance(files[0], UploadFile):
                raise HTTPException(400, "expected one upload file")
            yield files[0]
        except (MultiPartException, MultipartParseError, ClientDisconnect) as exc:
            raise HTTPException(400, "invalid or interrupted multipart upload") from exc
        finally:
            # Close temporary data before allowing another process into the slot.
            parser.close_files()
