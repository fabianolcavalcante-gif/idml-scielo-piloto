"""Root-only bounded probe and pinned qualification sources; Python 3.10 host."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

NORM = Path(
    "/opt/idml-platform/private/qualification/vh1-history-20261007T115427Z/sps-specification.txt"
)
NORM_SHA = "09ade688acbf1aa6c48324b660bf4baeb9293c92ff315a2d68c371251909bbef"
PROOF_SHA = "144d937523f966751d2ce73300131c1fbde1e6e380cbd1ad5de022e411459802"
VENDOR = {
    "xml/app_modules/app/ws/ws_institutions.py": (
        "fde363c6461aa3a2f7e52f8de1e0300934b8d1cfc5d321beed6583f583f9807c"
    ),
    "xml/app_modules/app/validations/article_content_validations.py": (
        "e0882113d47ee4fd64e2e4290e1e63d933c6324d6cf542f2f9323aedfc78c3b8"
    ),
}


def collect(scope, report_sha256, case):
    from ops.xpm_validator_broker import read_regular

    root = Path(__file__).resolve().parents[1]
    proof_path = root / "benchmarks/qualification/reports/vh1-wayta-native-v3.json"
    proof_raw = read_regular(proof_path, root, 1024**2)
    norm_raw = read_regular(NORM, NORM.parent, 4 * 1024**2)
    proof = json.loads(proof_raw)
    if (
        hashlib.sha256(proof_raw).hexdigest() != PROOF_SHA
        or hashlib.sha256(norm_raw).hexdigest() != NORM_SHA
        or proof["vendor_sha256"] != VENDOR
        or not proof["vendor_files_unchanged"]
    ):
        raise ValueError("wayta_qualification_source_mismatch")
    output = case / "wayta-service.json"
    # Child deadline also bounds DNS and slow-body reads. No article data in arguments.
    result = subprocess.run(  # noqa: S603 - fixed local probe, no shell
        [sys.executable, "-m", "ops.probe_wayta_https", str(output)],
        capture_output=True,
        timeout=30,
        check=False,
    )
    if result.returncode:
        raise ValueError("wayta_probe_failed")
    os.chmod(output, 0o600)
    raw = read_regular(output, case, 16384)
    service = json.loads(raw)
    if (
        service["probe_sha256"]
        != hashlib.sha256((root / "ops/probe_wayta_https.py").read_bytes()).hexdigest()
    ):
        raise ValueError("wayta_probe_source_mismatch")
    return dict(
        xpm_report_sha256=report_sha256,
        service_report=raw.decode(),
        requirement=dict(
            contract_version="wayta-requirement-evidence-1.0",
            scope=scope,
            normative_sha256=NORM_SHA,
            native_proof_sha256=PROOF_SHA,
            vendor_sha256=VENDOR,
            service_report_sha256=hashlib.sha256(raw).hexdigest(),
            observation=service["service_observation"],
        ),
    )
