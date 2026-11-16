"""Negative control in pinned runtime: hide PDFs from the package inventory only."""

import json
import sys

from packtools.sps.pid_provider.xml_sps_lib import XMLWithPre
from sps_rendition_compat import PackageRenditionView
from spsvalidator.domain.validation import validate_sps_xml_with_pre


class MissingPdfView(PackageRenditionView):
    @property
    def filenames(self):
        return [name for name in self._article.filenames if not name.lower().endswith(".pdf")]


def main():
    articles = missing = exceptions = 0
    for article in XMLWithPre.create(path=sys.argv[1]):
        articles += 1
        result = validate_sps_xml_with_pre(MissingPdfView(article))
        missing += sum(
            row.get("subject") == "Renditions" and row.get("status") == "ERROR"
            for row in result["rows"]
        )
        exceptions += len(result["exceptions"])
    result = {
        "scope": "full native validation with PDF-hidden inventory; ZIP unchanged",
        "articles": articles,
        "missing_pdf_errors": missing,
        "exceptions": exceptions,
        "negative_control_passed": articles > 0 and missing >= articles,
    }
    print(json.dumps(result))
    return 0 if result["negative_control_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
