"""Native unmodified XPM structural methods, offline; Python 3.8 vendor runtime."""

import hashlib
import json
import os
import shutil
import sys
from pathlib import Path


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def manifest(root):
    return {
        p.relative_to(root).as_posix(): sha(p.read_bytes()) for p in root.rglob("*") if p.is_file()
    }


def main():
    os.umask(0o077)
    original = Path("/opt/original/SciELO_XPM")
    source = Path("/input")
    work = Path("/work")
    before = manifest(original)
    inputs = manifest(source)
    runtime = work / "SciELO_XPM"
    shutil.copytree(original, runtime)
    os.chdir(runtime / "xml")
    sys.path.insert(0, str(runtime / "xml"))
    from app_modules.app.pkg_processors.xml_versions import identify_dtd_files
    from app_modules.app.validations.sps_xml_validators import XMLValidator

    rows = []
    for case in json.loads((source / "plan.json").read_bytes())["cases"]:
        folder = work / case["case"]
        folder.mkdir()
        xml = (source / case["case"] / "candidate.xml").read_bytes()
        assert sha(xml) == case["xml_sha256"]
        candidate = folder / "candidate.xml"
        candidate.write_bytes(xml)
        dtd_files, _ = identify_dtd_files(xml.decode())
        validator = XMLValidator(dtd_files, "sps-1.10", ["packtools", "java"])
        _, valid, counts = validator.validate(
            str(candidate), str(folder / "dtd.txt"), str(folder / "style.html")
        )
        dtd = (folder / "dtd.txt").read_bytes()
        annotated = validator.validator.annoted or ""
        row = dict(
            case=case["case"],
            xml_sha256=sha(xml),
            dtd_report_sha256=sha(dtd),
            style_report_sha256=sha((folder / "style.html").read_bytes()),
            dtd_valid=valid,
            style_counts=list(counts),
            unknown_public_id=b"Unknown PUBLIC ID:" in dtd,
            fallback_jats11="v1.1 20151215" in dtd_files.doctype_with_local_path,
            rejects_root_version=b'Attribute "dtd-version"' in dtd,
            rejects_coi_statement=b'with value "coi-statement"' in dtd,
            rejects_invalid_fn=b'with value "invented"' in dtd,
            style_sps_unsupported='version "sps-1.10" is not currently supported' in annotated,
            vendor_xml_validator_absent=validator.validator.xml_validator is None,
        )
        assert not valid and row["unknown_public_id"] and row["fallback_jats11"]
        assert row["style_sps_unsupported"] and row["vendor_xml_validator_absent"]
        assert counts == (0, 1, 0)
        if case["case"].endswith("-invalid_fn"):
            assert row["rejects_invalid_fn"]
        elif not case["case"].endswith("-wrong_version"):
            assert row["rejects_coi_statement"] and row["rejects_root_version"]
        rows.append(row)
    unchanged = all(sha((runtime / n).read_bytes()) == digest for n, digest in before.items())
    assert unchanged and inputs == manifest(source)
    report = dict(
        version="vh1-xpm-doctype-native-1.0",
        probe_sha256=sha(Path(__file__).read_bytes()),
        vendor_sha256={
            n: before[n]
            for n in (
                "xml/app_modules/app/validations/sps_xml_validators.py",
                "xml/app_modules/app/pkg_processors/xml_versions.py",
            )
        },
        vendor_files_unchanged=True,
        input_unchanged=True,
        network="none",
        cases=rows,
        publication_approved=False,
        compatibility_exceptions_added=0,
    )
    (work / "doctype.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(dict(cases=len(rows), vendor_files_unchanged=True, native_probe_passed=True)))


if __name__ == "__main__":
    main()
