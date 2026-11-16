"""Nonwaiting, cross-process admission on the shared local artifact filesystem.

Lock files are permanent: unlinking one could split ownership between two inodes.
The OS releases the lock on close or process exit; no expiring lease can admit a
replacement while the original request is still holding a temporary file.
"""

import errno
import shutil
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from typing import BinaryIO

from fastapi import HTTPException

from idml_foundation.settings import Settings

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl


def _lock(file: BinaryIO) -> bool:
    try:
        if sys.platform == "win32":
            file.seek(0)
            msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        if exc.errno in {errno.EACCES, errno.EAGAIN}:
            return False
        raise
    return True


@contextmanager
def upload_admission(settings: Settings) -> Iterator[None]:
    owned: BinaryIO | None = None
    try:
        directory = settings.artifact_root / ".upload-admission"
        directory.mkdir(parents=True, exist_ok=True, mode=0o750)
        for index in range(settings.upload_max_concurrency):
            candidate = (directory / f"slot-{index}.lock").open("a+b")
            try:
                acquired = _lock(candidate)
            except BaseException:
                candidate.close()
                raise
            if acquired:
                owned = candidate
                break
            candidate.close()
        if owned is None:
            raise HTTPException(503, "upload capacity busy", headers={"Retry-After": "5"})
        # Conservative: reserve the full configured capacity, even if other slots
        # already occupy disk. This is an admission check, not an OS disk quota.
        required = (
            settings.upload_temp_reserve_bytes
            + settings.upload_max_concurrency * settings.upload_max_bytes
        )
        if shutil.disk_usage(tempfile.gettempdir()).free < required:
            raise HTTPException(503, "insufficient upload temporary space")
    except OSError as exc:
        if owned is not None:
            owned.close()
        raise HTTPException(503, "upload admission unavailable") from exc
    except BaseException:
        if owned is not None:
            owned.close()
        raise
    try:
        yield
    finally:
        if owned is not None:
            owned.close()
