"""Inspect native DOI failure type only; never print DOI, metadata or exception text."""

import hashlib
import inspect
import json
import logging
import sys

from lxml import etree
from packtools.sps.libs import requester
from packtools.sps.validation.article_doi import ArticleDoiValidation


def main():
    logging.disable(logging.CRITICAL)
    payload = open(sys.argv[1], "rb").read()
    tree = etree.fromstring(payload, etree.XMLParser(resolve_entities=False, no_network=True))
    rows = []
    for rule in ArticleDoiValidation(tree, {}).validate_doi_registered():
        data = rule.get("data") or {}
        classes = {
            "<class 'tenacity.RetryError'>": "tenacity.RetryError",
            "<class 'packtools.sps.libs.requester.NonRetryableError'>": "NonRetryableError",
            "<class 'requests.exceptions.ConnectionError'>": "ConnectionError",
        }
        rows.append(
            {
                "failure_class": classes.get(data.get("exception_type"), "unrecognized"),
                "registered_metadata_present": bool(data.get("registered")),
                "valid": data.get("valid") is True,
                "upstream_severity": rule.get("response"),
            }
        )
    print(
        json.dumps(
            {
                "candidate_sha256": hashlib.sha256(payload).hexdigest(),
                "requester_source_sha256": hashlib.sha256(
                    inspect.getsource(requester).encode()
                ).hexdigest(),
                "checks": rows,
            }
        )
    )


if __name__ == "__main__":
    main()
