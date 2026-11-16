"""Fixed synthetic-only one-shot authors regression; safe boolean output."""

import hashlib
import json
import sys
from pathlib import Path

from lxml import etree
from packtools.sps.validation import utils
from packtools.sps.validation.article_doi import ArticleDoiValidation
from packtools.sps.validation.xml_validator import get_validation_results

sys.path.insert(0, "/validator")
from doi_model_compat import install

payload = Path("/synthetic.xml").read_bytes()
if (
    hashlib.sha256(payload).hexdigest()
    != "02a405e124fa6ec2fbed6a5df5b78bd764427047a8c665fa2ec12bd8213a6769"
):
    raise ValueError("fixed_synthetic_fixture_required")
tree = etree.fromstring(payload)
meta = tree.find("front/article-meta")
response = {
    "message": {
        "title": ["".join(meta.find("title-group/article-title").itertext())],
        "author": [
            {"given": e.findtext("given-names"), "family": e.findtext("surname")}
            for e in meta.findall("contrib-group/contrib/name")
        ],
    }
}
original = utils.get_doi_information
try:
    utils.get_doi_information = lambda _: response
    direct = list(ArticleDoiValidation(tree, {}).validate_doi_registered())
    before = [r for r in get_validation_results(tree, {}) if r.get("title") == "registered DOI"]
    install()
    install()
    after = [r for r in get_validation_results(tree, {}) if r.get("title") == "registered DOI"]
    response["message"].update(title=["Unrelated"], author=[{"given": "Other", "family": "Person"}])
    negative = [r for r in get_validation_results(tree, {}) if r.get("title") == "registered DOI"]
    assert all(len(rows) == 1 for rows in (direct, before, after, negative))
    assert direct[0]["response"] == after[0]["response"] == "OK"
    assert before[0]["response"] != "OK" and negative[0]["response"] != "OK"
    print(
        json.dumps(
            {
                "synthetic_only": True,
                "direct_passed": True,
                "native_full_sequence_bug_reproduced": True,
                "compat_full_sequence_passed": True,
                "metadata_mismatch_rejected": True,
            }
        )
    )
finally:
    utils.get_doi_information = original
