#!/usr/bin/env python3
"""Validate restricted OpenClaw proposals against canonical and JATS invariants."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from idml_foundation.ai.outputs import parse_agent_output
from idml_foundation.domain.canonical import CanonicalArticle
from idml_foundation.domain.metrics import normalize_text
from idml_foundation.pipeline.jats_builder import JatsBuilder
from idml_foundation.pipeline.profile import load_profile
from idml_foundation.pipeline.service import DeterministicPipeline
from idml_foundation.pipeline.validation import OfflineJatsValidator
from idml_foundation.schemas import JsonPatchOperation
from idml_foundation.services.reviews import (
    _replace_pointer,
    validate_patch_scope_and_atomicity,
)


def _pointer_value(document: Any, path: str) -> Any:
    current = document
    for escaped in path.removeprefix("/").split("/"):
        segment = escaped.replace("~1", "/").replace("~0", "~")
        current = current[int(segment)] if isinstance(current, list) else current[segment]
    return current


def _similarity(left: Any, right: Any) -> float:
    return SequenceMatcher(
        None,
        normalize_text(str(left)),
        normalize_text(str(right)),
        autojunk=False,
    ).ratio()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-idml", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    results = json.loads(args.results.read_text(encoding="utf-8"))
    result_by_id = {item["case_id"]: item for item in results["cases"]}
    source = args.source_idml.read_bytes()
    profile = load_profile()
    pipeline_result = DeterministicPipeline(profile=profile).run(
        source, logical_name=args.source_idml.name
    )
    base_payload = pipeline_result.canonical.model_dump(mode="json")
    validator = OfflineJatsValidator(Path(__file__).parents[1] / "vendor" / "jats" / "1.3")
    builder = JatsBuilder(sps_version=profile.sps_version)
    rows: list[dict[str, Any]] = []

    for case in dataset["cases"]:
        result = result_by_id.get(case["case_id"], {})
        baseline_similarity = float(case["baseline_similarity"])
        row: dict[str, Any] = {
            "case_id": case["case_id"],
            "domain": case["domain"],
            "response_succeeded": result.get("status") == "succeeded",
            "schema_valid": False,
            "scope_valid": False,
            "canonical_valid": False,
            "jats_valid": False,
            "baseline_similarity": baseline_similarity,
            "candidate_similarity": None,
            "similarity_delta": None,
            "improved": False,
            "exact": False,
            "patch_operations": 0,
            "failure_stage": result.get("error_code"),
        }
        raw = result.get("output")
        if not row["response_succeeded"] or not isinstance(raw, dict):
            rows.append(row)
            continue
        try:
            proposal = parse_agent_output(raw)
            row["schema_valid"] = True
            row["patch_operations"] = len(proposal.patch)
            operations = tuple(
                JsonPatchOperation.model_validate(operation.model_dump(mode="json"))
                for operation in proposal.patch
            )
            validate_patch_scope_and_atomicity(base_payload, operations, case["field_path"])
            row["scope_valid"] = True
            candidate_payload = copy.deepcopy(base_payload)
            for operation in operations:
                _replace_pointer(candidate_payload, operation)
            candidate = CanonicalArticle.model_validate(candidate_payload)
            row["canonical_valid"] = True
            xml = builder.build(candidate)
            validation = validator.validate(
                xml, asset_names={asset.logical_name for asset in candidate.assets}
            )
            row["jats_valid"] = validation.valid
            candidate_value = _pointer_value(candidate_payload, case["field_path"])
            candidate_similarity = _similarity(candidate_value, case["expected_value"])
            row["candidate_similarity"] = candidate_similarity
            row["similarity_delta"] = candidate_similarity - baseline_similarity
            row["improved"] = candidate_similarity > baseline_similarity
            row["exact"] = normalize_text(str(candidate_value)) == normalize_text(
                str(case["expected_value"])
            )
            row["failure_stage"] = None if validation.valid else "jats_validation"
        except ValidationError as exc:
            row["failure_stage"] = "ValidationError"
            row["failure_codes"] = sorted(
                {
                    f"{'.'.join(str(part) for part in error['loc'])}:{error['type']}"
                    for error in exc.errors(include_input=False)
                }
            )
        except (KeyError, TypeError, ValueError) as exc:
            row["failure_stage"] = type(exc).__name__
        rows.append(row)

    total = len(rows)

    def rate(key: str) -> float:
        return sum(bool(row[key]) for row in rows) / total if total else 0.0

    comparable = [row for row in rows if row["candidate_similarity"] is not None]
    report = {
        "version": "initial-corpus-candidate-validation-1.0",
        "restricted": True,
        "source_idml_sha256": hashlib.sha256(source).hexdigest(),
        "cases": total,
        "metrics": {
            "response_success_rate": rate("response_succeeded"),
            "schema_valid_rate": rate("schema_valid"),
            "scope_valid_rate": rate("scope_valid"),
            "canonical_valid_rate": rate("canonical_valid"),
            "jats_valid_rate": rate("jats_valid"),
            "improvement_rate": rate("improved"),
            "exact_rate": rate("exact"),
            "comparable_cases": len(comparable),
            "mean_baseline_similarity": (
                sum(row["baseline_similarity"] for row in comparable) / len(comparable)
                if comparable
                else None
            ),
            "mean_candidate_similarity": (
                sum(row["candidate_similarity"] for row in comparable) / len(comparable)
                if comparable
                else None
            ),
        },
        "rows": rows,
    }
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report["metrics"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
