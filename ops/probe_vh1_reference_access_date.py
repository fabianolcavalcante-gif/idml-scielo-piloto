"""Run inside the pinned Packtools image; inspect one rule without network or writes."""

import hashlib
import inspect
import json
from pathlib import Path

from lxml import etree
from packtools.sps.models.references import XMLReferences
from packtools.sps.validation.references import ReferenceValidation


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    expected = {
        "before": "84ab07204bd7debff2fc9f4c1623926f1637a722d12cbe964f4d5f4b178e899e",
        "after": "ccc0553baa5c11d17b7ce1fd47d7e4da766a59543c2ae8e2bc41d2269ff51992",
    }
    rows = {}
    for name, digest in expected.items():
        raw = Path("/input/" + name + ".xml").read_bytes()
        if sha(raw) != digest:
            raise ValueError("candidate_changed")
        root = etree.fromstring(raw, etree.XMLParser(resolve_entities=False, no_network=True))
        ref = list(XMLReferences(root).items)[30]
        if ref["ref_id"] != "reference-ff139fbc-b398-59da-9326-587309014e6a":
            raise ValueError("reference_changed")
        results = list(
            ReferenceValidation(
                ref, {"publication_type_requires": {}, "not_marked_data_error_level": "WARNING"}
            ).validate_not_marked()
        )
        rows[name] = {
            "candidate_sha256": digest,
            "reference_ordinal": 31,
            "filtered_not_marked_sha256": [sha(v.encode()) for v in ref["filtered_not_marked"]],
            "native_rule_findings": len(results),
            "native_severities": [r["response"] for r in results],
            "access_date_present_in_literal_citation": "Accessed on: May 5, 2020."
            in ref["mixed_citation"],
            "access_date_structured": bool(ref.get("date_in_citation")),
        }
    print(
        json.dumps(
            {
                "version": "vh1-reference-access-date-diagnostic-1.0",
                "rule_sha256": sha(
                    inspect.getsource(ReferenceValidation.validate_not_marked).encode()
                ),
                "model_sha256": sha(Path(inspect.getfile(XMLReferences)).read_bytes()),
                "rows": rows,
                "content_emitted": False,
                "formal_xml_approved": False,
                "diagnosis": "previously_misassigned_access_text_now_detected_as_unstructured",
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
