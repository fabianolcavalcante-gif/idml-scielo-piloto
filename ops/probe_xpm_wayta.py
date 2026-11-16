"""Offline original-XPM contraproof: query failures cannot imply institution validity."""

import contextlib
import hashlib
import io
import json
import os
import shutil
import sys
from pathlib import Path


def statuses(value):
    if isinstance(value, (list, tuple)):
        if len(value) >= 2 and isinstance(value[1], str) and value[1].startswith("["):
            return [value[1]]
        return [status for item in value for status in statuses(item)]
    return []


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
    from app_modules.app.data.article import AffiliationXML
    from app_modules.app.validations.article_content_validations import AffValidator
    from app_modules.app.ws.ws_institutions import Wayta
    from lxml import etree

    # Fake requester only controls external I/O, never the original implementation.
    class Requester:
        def __init__(self, value):
            self.value = value

        def format_url(self, url, params):
            return url  # Synthetic data; no network request occurs.

        def request(self, url, timeout):
            if isinstance(self.value, Exception):
                raise self.value
            return self.value

    responses = {
        "match": json.dumps(
            {
                "choices": [
                    {
                        "value": "Synthetic University",
                        "score": 1,
                        "iso3166": "BR",
                        "country": "Brazil",
                    }
                ]
            }
        ),
        "empty": '{"choices": []}',
        "malformed": "not-json",
        "absent": None,
        "timeout": TimeoutError("synthetic timeout"),
    }
    queries = []
    for name, response in responses.items():
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = Wayta(Requester(response)).search("Synthetic University", "Brazil")
        queries.append({"case": name, "result_count": len(result)})

    template = (
        '<aff id="aff1"><institution content-type="original">Synthetic University, '
        'Synthetic City, Brazil</institution><institution content-type="orgname">'
        'Synthetic University</institution><country country="BR">Brazil</country></aff>'
    )
    cases = {
        "valid": template,
        "missing_orgname": template.replace(
            '<institution content-type="orgname">Synthetic University</institution>', ""
        ),
        "missing_country": template.replace('<country country="BR">Brazil</country>', ""),
        "invalid_country": template.replace('country="BR"', 'country="ZZ"'),
        "missing_original": template.replace(
            '<institution content-type="original">Synthetic University, '
            "Synthetic City, Brazil</institution>",
            "",
        ),
        "broken_xref": template,
    }
    affiliations = []
    for name, xml in cases.items():
        for state, query in (
            ("unavailable", None),
            ("empty", (None, [])),
            ("present", (object(), ["synthetic candidate"])),
        ):
            validator = AffValidator(
                AffiliationXML(etree.fromstring(xml.encode())),
                query,
                [] if name == "broken_xref" else ["aff1"],
            )
            normalized = validator.normalized
            found = statuses(validator.validations)
            errors = [s for s in found if s not in ("[INFO]", "[OK]", "[VALID]")]
            # Native validator iterates existing countries; absence is not caught here.
            # Record that gap, never turn it into permission to omit the country.
            if normalized != [] or bool(errors) != (name not in {"valid", "missing_country"}):
                raise ValueError(
                    "unexpected_native_affiliation_result: " + repr((name, state, found))
                )
            affiliations.append(
                {
                    "case": name,
                    "query_state": state,
                    "normalized_findings": len(normalized),
                    "error_statuses": errors,
                }
            )
    if any(hashlib.sha256((runtime / n).read_bytes()).hexdigest() != s for n, s in before.items()):
        raise ValueError("vendor_changed")
    files = (
        "xml/app_modules/app/ws/ws_institutions.py",
        "xml/app_modules/app/validations/article_content_validations.py",
    )
    report = {
        "version": "xpm-wayta-native-1.0",
        "network": "none",
        "probe_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "vendor_sha256": {p: before[p] for p in files},
        "vendor_files_unchanged": True,
        "requester_is_synthetic": True,
        "native_missing_country_gap": True,
        "query_cases": queries,
        "affiliation_cases": affiliations,
        "release_approved": False,
    }
    (Path("/work") / "wayta-native.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"query_cases": len(queries), "affiliation_cases": len(affiliations)}))


if __name__ == "__main__":
    main()
