"""Exercise original DOI comparison methods offline, without instantiating web clients."""

import hashlib
import json
import os
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace


def main():
    os.umask(0o077)
    original = Path("/opt/original/SciELO_XPM")
    runtime = Path("/work/SciELO_XPM")
    before = {
        p.relative_to(original).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in original.rglob("*")
        if p.is_file()
    }
    shutil.copytree(original, runtime)
    sys.path.insert(0, str(runtime / "xml"))
    from app_modules.generics.doi_validations import DOIValidator

    rows = []
    for field in ("journal", "article"):
        expected = "Synthetic journal title" if field == "journal" else "Synthetic article title"
        for kind, values in (
            ("exact", [expected]),
            ("near_but_not_exact", [expected + "s"]),
            ("different", ["xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"]),
            ("absent", None),
        ):
            validator = DOIValidator.__new__(DOIValidator)
            validator.messages = []
            data = SimpleNamespace(journal_titles=values, article_titles=values)
            if field == "journal":
                validator.validate_journal_title(expected, "10.0000/synthetic", data)
            else:
                validator.validate_article_title(
                    [SimpleNamespace(title=expected)], "10.0000/synthetic", data
                )
            statuses = [message[1] for message in validator.messages]
            wanted = (
                [] if kind == "absent" else ["[FATAL ERROR]" if kind == "different" else "[ERROR]"]
            )
            if statuses != wanted:
                raise ValueError("unexpected_vendor_comparison")
            rows.append({"field": field, "case": kind, "statuses": statuses})
    if any(hashlib.sha256((runtime / n).read_bytes()).hexdigest() != s for n, s in before.items()):
        raise ValueError("vendor_changed")
    report = {
        "version": "xpm-doi-comparison-native-1.0",
        "probe_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "vendor_module_sha256": before["xml/app_modules/generics/doi_validations.py"],
        "vendor_files_unchanged": True,
        "network": "none",
        "cases": rows,
        "release_approved": False,
    }
    (Path("/work") / "doi-comparisons.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
