"""Run original XPM SPS/date methods on synthetic controls; no network/vendor edits."""

import hashlib
import json
import os
import shutil
import sys
from pathlib import Path


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
    from app_modules.app.data.article import Article
    from app_modules.app.validations.article_content_validations import ArticleContentValidation
    from lxml import etree

    template = (
        '<article specific-use="sps-1.10" dtd-version="1.3"><front><journal-meta/>'
        '<article-meta><pub-date publication-format="electronic" date-type="pub" '
        'iso-8601-date="2025-07-07"><day>07</day><month>07</month><year>2025</year>'
        '</pub-date><pub-date publication-format="electronic" date-type="collection">'
        "<year>2025</year></pub-date><volume>30</volume></article-meta></front></article>"
    )
    cases = {
        "sps110_valid": template,
        "sps19_valid": template.replace("sps-1.10", "sps-1.9"),
        "sps20_unknown": template.replace("sps-1.10", "sps-2.0"),
        "missing_day": template.replace("<day>07</day>", ""),
        "invalid_calendar": template.replace("<month>07</month>", "<month>13</month>"),
        "legacy_pub_type": template.replace('date-type="pub"', 'date-type="pub" pub-type="epub"'),
        "wrong_format": template.replace(
            'publication-format="electronic"', 'publication-format="print"'
        ),
        "unknown_date_type": template.replace('date-type="pub"', 'date-type="other"'),
        "collection_day": template.replace(
            "<year>2025</year></pub-date><volume>",
            "<day>01</day><year>2025</year></pub-date><volume>",
        ),
        "duplicate_pub": template.replace(
            "<volume>",
            template[template.index("<pub-date") : template.index("</pub-date>") + 11] + "<volume>",
        ),
    }
    rows = []
    for name, xml in cases.items():
        article = Article(etree.ElementTree(etree.fromstring(xml.encode())), "synthetic.xml")
        validator = ArticleContentValidation.__new__(ArticleContentValidation)
        validator.article = article
        findings = {}
        for kind in ("sps", "article_date_types"):
            try:
                findings[kind] = [list(item[:3]) for item in getattr(validator, kind)]
            except (TypeError, ValueError, AttributeError) as exc:
                findings[kind] = {"failed": type(exc).__name__}
        rows.append(
            {
                "case": name,
                "xml": xml,
                "legacy_version_number": article.sps_version_number,
                "findings": findings,
            }
        )
    if rows[0]["legacy_version_number"] != 1.1 or rows[1]["legacy_version_number"] != 1.9:
        raise ValueError("version_contraproof_failed")
    if any(hashlib.sha256((runtime / n).read_bytes()).hexdigest() != s for n, s in before.items()):
        raise ValueError("vendor_changed")
    files = (
        "xml/app_modules/app/data/article.py",
        "xml/app_modules/app/data/attributes.py",
        "xml/app_modules/app/validations/article_content_validations.py",
    )
    report = {
        "version": "xpm-sps-date-native-1.0",
        "probe_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "vendor_sha256": {name: before[name] for name in files},
        "vendor_files_unchanged": True,
        "network": "none",
        "cases": rows,
        "release_approved": False,
    }
    (Path("/work") / "sps-dates.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"cases": len(rows), "vendor_files_unchanged": True}))


if __name__ == "__main__":
    main()
