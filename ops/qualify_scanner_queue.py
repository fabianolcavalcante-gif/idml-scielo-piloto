"""Exercise real consecutive and concurrent requests against an isolated systemd socket."""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

from idml_foundation.ingest.scanner import ClamAVScanner


def run():
    scanner = ClamAVScanner("unused", 0, 300, Path("/run/idml-clamav-vh1/scan.sock"))
    # Two real IDMLs back-to-back, without a teardown sleep or a transport retry.
    originals = sorted(Path("/inputs").glob("*/*.idml"))
    assert len(originals) == 2
    start = time.monotonic()
    consecutive = [scanner.scan(p.read_bytes()).status for p in originals]
    assert consecutive == ["clamav_clean", "clamav_clean"]
    control = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}" + b"$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
    ready = Barrier(3)

    def check(data):
        ready.wait(timeout=10)
        return scanner.scan(data).status

    with ThreadPoolExecutor(max_workers=3) as pool:
        concurrent = list(pool.map(check, (b"clean one", control, b"clean two")))
    assert concurrent == ["clamav_clean", "malware_detected", "clamav_clean"]
    print(
        json.dumps(
            dict(
                consecutive=consecutive,
                concurrent=concurrent,
                explicit_delay=False,
                transport_retries=0,
                elapsed_seconds=round(time.monotonic() - start, 2),
            )
        )
    )


if __name__ == "__main__":
    run()
