"""Administrative qualification only, Python 3.10 host; never activates app/registry."""

import hashlib
import json
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import validator_broker as broker
from doi_authority_transport import trusted_read

VAULT = Path(
    "/opt/idml-platform/private/source-vault/"
    "25ca4293d4e180ad32b7751b50fd30cd0f66ace056ff7226cddf01640b69b1e8"
)
CODE = (
    "editorial_authority.py",
    "editorial_authority_runtime.py",
    "probe_vh1_editorial.py",
    "doi_validation_evidence.py",
    "doi_package_binding.py",
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    source = Path(__file__).resolve().parent
    plan_raw = (source / "qualification.json").read_bytes()
    if len(sys.argv) != 2 or digest(plan_raw) != sys.argv[1]:
        raise ValueError("qualification_manifest_mismatch")
    plan = json.loads(plan_raw)
    for name, expected in plan["code_sha256"].items():
        if Path(name).name != name or digest((source / name).read_bytes()) != expected:
            raise ValueError("qualification_code_mismatch")
    report = {
        "version": "vh1-editorial-linux-1.0",
        "qualification_sha256": digest(plan_raw),
        "executed_at": datetime.now(timezone.utc).isoformat(),  # noqa: UP017
        "code_sha256": plan["code_sha256"],
        "cases": [],
        "deployment_changed": False,
        "formal_xml_approved": False,
        "runtime": "pinned native images plus fingerprinted read-only qualification harness",
    }
    # Scratch tree is root-owned with root-owned ancestors. Never weaken trusted_read.
    # /run is a small tmpfs: use the disk volume without weakening the 5 GiB reserve.
    work = Path("/var/lib/idml-vh1-qualification")
    work.mkdir(mode=0o700, exist_ok=True)
    if work.is_symlink() or work.stat().st_uid != 0 or work.stat().st_mode & 0o077:
        raise ValueError("qualification_workdir_untrusted")
    with tempfile.TemporaryDirectory(prefix="editorial-", dir=work) as temporary:
        scratch = Path(temporary)
        broker.reserve(scratch, starting=True)
        for name in CODE:
            (scratch / name).write_bytes((source / name).read_bytes())
            (scratch / name).chmod(0o444)
        for case, item in plan["cases"].items():
            if case not in {"esa-e20240086", "esa-e20240135"}:
                raise ValueError("qualification_case_denied")
            context = scratch / case
            context.mkdir(mode=0o700)
            raw = (source / case / "manifest.json").read_bytes()
            if digest(raw) != item["editorial_manifest_sha256"]:
                raise ValueError("editorial_manifest_mismatch")
            manifest = json.loads(raw)
            (context / "manifest.json").write_bytes(raw)
            for key, entry in manifest["sources"].items():
                if key != "journal" and not __import__("re").fullmatch(
                    r"[0-9]{4}-[0-9]{4}-[0-9]{4}-[0-9]{3}[0-9X]", key
                ):
                    raise ValueError("editorial_source_name_invalid")
                if entry["status"] != "available":
                    continue
                raw = (source / case / (key + ".json")).read_bytes()
                if not 0 < len(raw) <= 1024**2 or digest(raw) != entry["sha256"]:
                    raise ValueError("editorial_snapshot_mismatch")
                (context / (key + ".json")).write_bytes(raw)
            for path in context.iterdir():
                path.chmod(0o444)
            result = {"case": case, "validators": {}}
            for spec_original in plan["validators"]:
                spec = dict(spec_original)
                run = scratch / (case + "-" + spec["name"])
                run.mkdir(mode=0o700)
                candidate = run / ("candidate" + spec["input_suffix"])
                payload = (VAULT / case / candidate.name).read_bytes()
                if digest(payload) != item[candidate.suffix[1:] + "_sha256"]:
                    raise ValueError("qualification_candidate_mismatch")
                candidate.write_bytes(payload)
                candidate.chmod(0o444)
                authority = run / "trusted-authority"
                authority.mkdir(mode=0o700)
                original_doi_raw = (VAULT / case / "authority/manifest.json").read_bytes()
                if digest(original_doi_raw) != item["doi_manifest_sha256"]:
                    raise ValueError("qualification_doi_manifest_mismatch")
                original_doi = json.loads(original_doi_raw)
                if spec["name"] == "packtools":
                    original_doi.pop("package_sha256", None)
                manifest_path = authority / "manifest.json"
                manifest_path.write_text(json.dumps(original_doi), encoding="utf-8")
                snapshot = authority / "crossref.json"
                shutil.copyfile(VAULT / case / "authority/crossref.json", snapshot)
                spec["doi_authority"] = {
                    "manifest_path": str(manifest_path),
                    "snapshot_path": str(snapshot),
                    "manifest_sha256": digest(trusted_read(manifest_path, 8192)),
                }
                create_original = broker.create_arguments

                def create_arguments(selected, target, original=create_original, data=context):
                    arguments = original(selected, target)
                    index = arguments.index("--entrypoint=python")
                    mounts = []
                    for filename in CODE:
                        mounts.extend(
                            [
                                "--mount",
                                f"type=bind,src={scratch / filename},"
                                f"dst=/validator/{filename},readonly",
                            ]
                        )
                    for file in data.iterdir():
                        mounts.extend(
                            ["--mount", f"type=bind,src={file},dst=/editorial/{file.name},readonly"]
                        )
                    arguments = arguments[:index] + mounts + arguments[index:]
                    arguments[-2] = "/validator/probe_vh1_editorial.py"
                    return arguments

                broker.create_arguments = create_arguments
                try:
                    outcome = json.loads(broker.execute(spec, candidate, scratch))
                finally:
                    broker.create_arguments = create_original
                if "probe_error_type" in outcome:
                    print(json.dumps(outcome), flush=True)
                    raise ValueError("native_probe_failed")
                result["validators"][spec["name"]] = {"image_id": spec["image_id"], **outcome}
                print(
                    json.dumps(
                        {
                            "case": case,
                            "validator": spec["name"],
                            "summary": outcome["result"]["summary"],
                            "native_context_evidence": outcome["native_context_evidence"],
                        }
                    ),
                    flush=True,
                )
            report["cases"].append(result)
    with (source / "report.json").open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
    print(json.dumps({"report_saved": True, "formal_xml_approved": False}))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        safe_codes = {
            "memory_reserve",
            "disk_reserve",
            "validator_execution_failed",
            "validator_timeout",
            "validator_output_budget",
            "image_mismatch",
        }
        print(
            json.dumps(
                {
                    "qualification_error_type": type(error).__name__,
                    "code": str(error) if str(error) in safe_codes else "qualification_failed",
                }
            )
        )
        raise SystemExit(1) from None
