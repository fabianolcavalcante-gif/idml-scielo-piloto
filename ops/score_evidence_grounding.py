#!/usr/bin/env python3
"""Create a content-free grounding report from a restricted agent dataset."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from idml_foundation.ai.evidence import reassemble_evidence
from idml_foundation.ai.grounding import DEFAULT_GROUNDING_POLICY, assess_evidence_grounding


def score_dataset(dataset: dict[str, Any]) -> dict[str, Any]:
    if dataset.get("restricted") is not True or not isinstance(dataset.get("cases"), list):
        raise ValueError("a restricted dataset with cases is required")
    domains: dict[str, dict[str, int]] = {}
    supported = 0
    segment_count = 0
    multi_segment_cases = 0
    max_evidence_characters = 0
    for case in dataset["cases"]:
        evidence_text = reassemble_evidence(case["evidence"])
        assessment = assess_evidence_grounding(
            case["expected_value"],
            evidence_text,
            policy=case.get("grounding_policy", DEFAULT_GROUNDING_POLICY),
        )
        domain = str(case["domain"])
        row = domains.setdefault(domain, {"cases": 0, "supported": 0})
        row["cases"] += 1
        row["supported"] += int(assessment.supported)
        supported += int(assessment.supported)
        segments = case["evidence"].get("segments")
        if isinstance(segments, list):
            segment_count += len(segments)
            multi_segment_cases += int(len(segments) > 1)
        else:
            segment_count += 1
        max_evidence_characters = max(max_evidence_characters, len(evidence_text))
    cases = len(dataset["cases"])
    return {
        "version": "idml-evidence-grounding-corpus-report-1.1",
        "dataset_version": dataset.get("version"),
        "corpus_id": dataset.get("corpus_id"),
        "policy": DEFAULT_GROUNDING_POLICY,
        "cases": cases,
        "supported": supported,
        "unsupported": cases - supported,
        "support_rate": supported / cases if cases else 0.0,
        "evidence_transport": {
            "representation": "lossless_segmented",
            "segments": segment_count,
            "multi_segment_cases": multi_segment_cases,
            "max_evidence_characters": max_evidence_characters,
            "individual_hashes_valid": True,
            "aggregate_hashes_valid": True,
            "truncation_used": False,
        },
        "domains": domains,
        "automatic_target_used_only_for_offline_evaluation": True,
        "target_exposed_to_agents": False,
        "human_baseline_complete": False,
        "gate_g6_t_approved": False,
        "privacy": {
            "contains_article_text": False,
            "contains_expected_values": False,
            "contains_evidence_excerpts": False,
            "contains_credentials": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--report-output", type=Path, required=True)
    args = parser.parse_args()
    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    report = score_dataset(dataset)
    args.report_output.parent.mkdir(parents=True, exist_ok=True)
    args.report_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "cases": report["cases"],
                "supported": report["supported"],
                "segments": report["evidence_transport"]["segments"],
            },
            sort_keys=True,
        )
    )
    return 0 if report["support_rate"] == 1.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
