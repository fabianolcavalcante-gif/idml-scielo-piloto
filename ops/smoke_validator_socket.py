"""Synthetic client run only inside an isolated existing app image on Linux."""

import hashlib
import io
import json
import sys
from pathlib import Path
from zipfile import ZipFile

from idml_foundation.release.validator_registry import ValidatorChannel, load_validator_registry

sys.path.insert(0, "/qualification")
from validator_transport import LocalValidatorExecutor

registry = load_validator_registry(Path("/qualification/validator-registry-v1.json"))
name = sys.argv[1]
case = sys.argv[2] if len(sys.argv) > 2 else "incomplete"
xml = b'<?xml version="1.0"?><article article-type="research-article"><front/></article>'
candidate = xml
if name == "spsvalidator":
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("synthetic.xml", xml)
    candidate = buffer.getvalue()
if case in {"complete", "real"}:
    candidate = Path(
        "/qualification/candidate" + (".xml" if name == "packtools" else ".zip")
    ).read_bytes()
spec = registry.select(name, ValidatorChannel.ACTIVE).command_specification()
run = LocalValidatorExecutor(Path("/qualification/broker.sock"))(candidate, spec)
print(
    json.dumps(
        {
            "name": name,
            "case": case,
            "status": run.status.value,
            "counts": run.counts,
            "candidate_sha256": run.candidate_sha256,
            "tool_sha256": run.tool_sha256,
            "report_sha256": run.sanitized_output_sha256,
            "failure_code": run.failure_code,
            "passed": run.passed,
            "issue_codes": sorted({issue.code for issue in run.issues}),
            "transport_completed": bool(run.sanitized_output_sha256)
            and run.candidate_sha256 == hashlib.sha256(candidate).hexdigest(),
        }
    )
)
raise SystemExit(0 if run.sanitized_output_sha256 else 1)
