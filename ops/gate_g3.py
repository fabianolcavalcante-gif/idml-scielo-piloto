"""Run the deterministic Phase 3 gate against the restricted ESA corpus."""

import argparse
import hashlib
import json
from pathlib import Path

from lxml import etree

from idml_foundation.domain.common import canonical_bytes
from idml_foundation.pipeline.crossref_evaluation import evaluate_cross_references
from idml_foundation.pipeline.service import DeterministicPipeline

EXPECTED_IDML_SHA256 = "8ce185f5dd03f5403a36ca7b60d9d708b95e2b334e731327dd0b568b0cd44d2c"
EXPECTED_GOLD_SHA256 = "739b4c3247a06d6d5253ad2805fb830d09692cb306cbb5c785ad99707e539de9"


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--idml", type=Path, required=True)
    parser.add_argument("--gold-xml", type=Path, required=True)
    args = parser.parse_args()

    idml_data = args.idml.read_bytes()
    gold_data = args.gold_xml.read_bytes()
    if _digest(idml_data) != EXPECTED_IDML_SHA256:
        raise SystemExit("restricted ESA IDML hash mismatch")
    if _digest(gold_data) != EXPECTED_GOLD_SHA256:
        raise SystemExit("restricted ESA gold XML hash mismatch")

    pipeline = DeterministicPipeline()
    first = pipeline.run(idml_data, logical_name=args.idml.name)
    second = pipeline.run(idml_data, logical_name=args.idml.name)
    deterministic = (
        canonical_bytes(first.raw) == canonical_bytes(second.raw)
        and canonical_bytes(first.canonical) == canonical_bytes(second.canonical)
        and first.xml == second.xml
        and first.validation == second.validation
    )
    if not deterministic:
        raise SystemExit("pipeline output is not deterministic")
    if not first.validation.valid:
        raise SystemExit("generated XML failed offline validation")

    blocking_thread_codes = {
        "invalid_thread_start_count",
        "non_reciprocal_thread_link",
        "thread_cycle",
        "thread_disconnected",
    }
    blocking_thread_issues = [
        issue for issue in first.raw.reading_order_issues if issue.code in blocking_thread_codes
    ]
    thread_integrity = 1.0 if not blocking_thread_issues else 0.0
    if thread_integrity < 1.0 or len(first.raw.frames) != 55:
        raise SystemExit("reading-order frame-chain threshold not reached")

    parser_xml = etree.XMLParser(
        resolve_entities=False,
        load_dtd=False,
        no_network=True,
        recover=False,
    )
    gold = etree.fromstring(gold_data, parser=parser_xml)
    generated = etree.fromstring(first.xml, parser=parser_xml)
    gold_counts = {
        "contributors": len(gold.xpath("front/article-meta//contrib[@contrib-type='author']")),
        "affiliations": len(gold.xpath("front/article-meta/aff")),
        "references": len(gold.xpath("back/ref-list/ref")),
    }
    generated_counts = {
        "contributors": len(generated.xpath("front/article-meta//contrib[@contrib-type='author']")),
        "affiliations": len(generated.xpath("front/article-meta/aff")),
        "references": len(generated.xpath("back/ref-list/ref")),
    }
    if generated_counts != gold_counts or generated_counts != {
        "contributors": 3,
        "affiliations": 3,
        "references": 52,
    }:
        raise SystemExit("deterministic core structure differs from the approved corpus facts")
    if not first.canonical.review_reasons:
        raise SystemExit("known ambiguities were not classified for review")
    cross_references = evaluate_cross_references(gold, generated)

    report = {
        "gate": "G3",
        "approved": True,
        "article_id": first.canonical.article_id,
        "deterministic": deterministic,
        "idml": {
            "stories": len(first.raw.stories),
            "frames": len(first.raw.frames),
            "spreads": len(first.raw.spreads),
            "tables": len(first.raw.tables),
            "external_assets": sum(item.external for item in first.raw.assets),
        },
        "reading_order": {
            "frame_thread_integrity": thread_integrity,
            "unframed_stories_classified": sum(
                issue.code == "story_without_frame" for issue in first.raw.reading_order_issues
            ),
            "blocking_issues": len(blocking_thread_issues),
        },
        "canonical": generated_counts,
        "cross_references": cross_references.model_dump(mode="json"),
        "validation": {
            "valid": first.validation.valid,
            "issues": len(first.validation.issues),
            "profile": first.validation.validator_profile,
            "xml_sha256": first.validation.xml_sha256,
        },
        "review_reasons": len(first.canonical.review_reasons),
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
