import struct
import subprocess
import sys
from types import SimpleNamespace

import pytest

from ops import clamav_stream as broker


class Stream:
    def __init__(self):
        self.data = bytearray(b"zINSTREAM\0\0\0\0\x01x\0\0\0\0")

    def getsockopt(self, *_args):
        return struct.pack("3i", 1, 10001, 10001)

    def settimeout(self, value):
        assert value > 0

    def recv(self, size):
        value = self.data[:size]
        del self.data[:size]
        return value


@pytest.fixture
def lock(monkeypatch, tmp_path):
    state = dict(held=False, busy=False, releases=0)

    def flock(_file, mode):
        if mode == 4:
            state.update(held=False, releases=state["releases"] + 1)
        elif state["busy"]:
            raise BlockingIOError()
        else:
            assert not state["held"]
            state["held"] = True

    monkeypatch.setitem(
        sys.modules, "fcntl", SimpleNamespace(flock=flock, LOCK_EX=1, LOCK_NB=2, LOCK_UN=4)
    )
    # Linux peer credential constant is not available on Windows.
    monkeypatch.setattr(broker.socket, "SO_PEERCRED", 17, raising=False)
    original = broker.scan_slot
    monkeypatch.setattr(broker, "scan_slot", lambda: original(tmp_path / "scan.lock", wait=0.2))
    return state


@pytest.mark.parametrize(
    ("code", "out", "err", "expected"),
    [
        (0, b"stdin: OK", b"", b"stream: OK\0"),
        (1, b"stdin: Eicar FOUND", b"", b"stream: rejected FOUND\0"),
        (2, b"", b"unavailable", b"stream: ERROR\0"),
        (0, b"stdin: OK", b"warning", b"stream: ERROR\0"),
    ],
)
def test_sequential_scans_release_engine_before_reply(monkeypatch, lock, code, out, err, expected):
    def engine(*_args, **kwargs):
        assert lock["held"] and kwargs["stdin"].read() == b"x"
        return SimpleNamespace(returncode=code, stdout=out, stderr=err)

    monkeypatch.setattr(broker.subprocess, "run", engine)
    for _ in range(2):
        assert broker.scan(Stream()) == expected
        assert not lock["held"]
    assert lock["releases"] == 2


def test_queue_deadline_never_starts_engine(monkeypatch, lock):
    lock["busy"] = True
    now = [0.0]
    monkeypatch.setattr(broker.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(broker.time, "sleep", lambda seconds: now.__setitem__(0, now[0] + seconds))

    def forbidden(*_args, **_kwargs):
        pytest.fail("engine started while another scan or signature update held the lock")

    monkeypatch.setattr(broker.subprocess, "run", forbidden)
    with pytest.raises(TimeoutError, match="queue deadline"):
        broker.scan(Stream())
    assert now[0] == pytest.approx(0.2)
    assert lock["releases"] == 0


def test_engine_failure_releases_slot(monkeypatch, lock):
    def engine(*_args, **_kwargs):
        raise subprocess.TimeoutExpired("scanner", 125)

    monkeypatch.setattr(broker.subprocess, "run", engine)
    with pytest.raises(subprocess.TimeoutExpired):
        broker.scan(Stream())
    assert not lock["held"] and lock["releases"] == 1
