"""Synthetic native-rule probe, run only in the isolated qualification image."""

import json
import sys
from pathlib import Path

from doi_authority_runtime import authority_lookup
from lxml import etree
from packtools.sps.validation import utils
from packtools.sps.validation.article_doi import ArticleDoiValidation

candidate = Path(sys.argv[1]).read_bytes()
with authority_lookup(utils, candidate, Path("/authority")):
    rows = list(ArticleDoiValidation(etree.fromstring(candidate), {}).validate_doi_registered())
print(
    json.dumps(
        {"rows": len(rows), "native_doi_passed": len(rows) == 1 and rows[0]["response"] == "OK"}
    )
)
