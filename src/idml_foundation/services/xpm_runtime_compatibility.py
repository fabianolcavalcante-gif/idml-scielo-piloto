"""Compose qualified DOI, SPS/date and Wayta rules on current trusted evidence."""

import hashlib
import json
from datetime import datetime
from typing import Any

from pydantic import Field

from idml_foundation.domain.common import SHA256_PATTERN, StrictModel
from idml_foundation.release.validation_engine import ValidatorRun
from idml_foundation.release.xpm import XpmAttestation
from idml_foundation.release.xpm_compatibility import (
    VENDOR_COMPARISON_SHA256,
    XpmCompatibilityEvidence,
    assess_xpm_compatibility,
)
from idml_foundation.release.xpm_query_requirements import (
    WaytaRequirementEvidence,
    WaytaServiceObservation,
    assess_wayta_requirement,
)
from idml_foundation.release.xpm_query_semantics import QueryEvidence
from idml_foundation.release.xpm_sps_compatibility import (
    assess_xpm_sps_compatibility,
    bind_runtime_runs,
)
from idml_foundation.release.xpm_structural_compatibility import assess_xpm_structural_compatibility


class WaytaExecutionEvidence(StrictModel):
    xpm_report_sha256: str = Field(pattern=SHA256_PATTERN)
    service_report: str = Field(max_length=16384)
    requirement: WaytaRequirementEvidence


def assess_runtime_compatibility(
    *,
    xml: bytes,
    package: bytes,
    report: bytes,
    scope: dict[str, str],
    image: str,
    attestation: XpmAttestation,
    queries: QueryEvidence,
    selected: dict[str, Any],
    now: datetime,
    independent_runs: tuple[ValidatorRun, ...] = (),
    wayta: WaytaExecutionEvidence | None = None,
) -> dict[str, Any]:
    """Caller has verified pinned image, attestation and all receipt bindings.

    The vendor-comparison hash identifies the code in that immutable qualified
    image, not a claim supplied by the user. No raw HTML/environment is returned.
    SPS/date rules require independent current validation evidence. This result
    never changes raw counts or release policy.
    """
    unavailable = dict(status="unavailable", reason="compatibility-evidence-unqualified")
    try:
        if scope["journal_profile_id"] != "esa-aop-1.1.0":
            return unavailable
        checks = [c for c in selected.get("checks", []) if c["kind"] == "crossref"]
        if len(checks) != 1 or checks[0]["status"] != "matched":
            return unavailable
        receipt = next(r for r in queries.receipts if r.kind == "crossref")
        if receipt.payload is None or receipt.response_sha256 is None:
            return unavailable
        arguments: dict[str, Any] = dict(
            xml=xml,
            package=package,
            report=report,
            crossref=receipt.payload.encode(),
            trusted=XpmCompatibilityEvidence(
                contract_version="xpm-compatibility-evidence-1.0",
                scope=scope,
                attestation=attestation,
                image=image,
                vendor_comparison_sha256=VENDOR_COMPARISON_SHA256,
                crossref_sha256=receipt.response_sha256,
                crossref_retrieved_at=receipt.retrieved_at,
                required_queries_complete=False,
            ),
            expected_scope=scope,
            now=now,
        )
        result = assess_xpm_compatibility(**arguments)
        output: dict[str, Any] = dict(
            status="assessed",
            policy_version=result.policy_version,
            scope_sha256=result.scope_sha256,
            exceptions=[e.model_dump(mode="json") for e in result.exceptions],
            unresolved_counts=result.unresolved_counts,
            reasons=list(result.reasons),
            integrated_rule_families=["doi"],
            pending_rule_families=["sps-date", "doctype-jats", "wayta"],
            homologation_ready=False,
            release_approved=False,
        )
        try:
            sps = bind_runtime_runs(scope, attestation.report_sha256, independent_runs, now)
            composed = assess_xpm_sps_compatibility(**arguments, sps_evidence=sps)
            output.update(
                policy_version=composed.policy_version,
                exceptions=[
                    e.model_dump(mode="json") for e in (*result.exceptions, *composed.exceptions)
                ],
                unresolved_counts=composed.unresolved_counts,
                reasons=list(composed.reasons),
                integrated_rule_families=["doi", "sps-date"],
                pending_rule_families=["doctype-jats", "wayta"],
                independent_evidence_sha256=sps.independent_report_sha256,
                independent_assembled_at=sps.assembled_at.isoformat(),
                independent_contract=sps.contract_version,
                independent_runs=[
                    dict(
                        name=r.name,
                        report_sha256=r.sanitized_output_sha256,
                        candidate_sha256=r.candidate_sha256,
                        tool_sha256=r.tool_sha256,
                    )
                    for r in independent_runs
                ],
                sps_status="assessed",
            )
        except Exception:
            output["sps_status"] = "unavailable"
            return output
        try:
            if wayta is None:
                raise ValueError("wayta_observation_missing")
            wayta = WaytaExecutionEvidence.model_validate(
                wayta.model_dump(mode="python", warnings=False)
            )
            service = json.loads(wayta.service_report)
            if (
                wayta.xpm_report_sha256 != attestation.report_sha256
                or hashlib.sha256(wayta.service_report.encode()).hexdigest()
                != wayta.requirement.service_report_sha256
                or WaytaServiceObservation.model_validate(service["service_observation"])
                != wayta.requirement.observation
            ):
                raise ValueError("wayta_observation_binding_invalid")
            assessed = assess_wayta_requirement(
                **arguments, sps_evidence=sps, wayta_evidence=wayta.requirement
            )
            output["wayta"] = assessed.model_dump(mode="json", exclude={"base"})
            output["integrated_rule_families"] = ["doi", "sps-date", "wayta-applicability"]
            output["pending_rule_families"] = ["doctype-jats"]
        except Exception:
            output["wayta"] = {
                "requirement": "undetermined",
                "reason": "wayta-evidence-unavailable-or-unqualified",
            }
        try:
            structural = assess_xpm_structural_compatibility(**arguments, sps_evidence=sps)
            output.update(
                exceptions=[
                    *output["exceptions"],
                    *(e.model_dump(mode="json") for e in structural.exceptions),
                ],
                unresolved_counts=structural.unresolved_counts,
                reasons=list(structural.reasons),
                structural_status="assessed",
                structural_policy_version=structural.policy_version,
                technical_errors_resolved=structural.technical_errors_resolved,
                homologation_disposition=(
                    "review-pending"
                    if structural.technical_errors_resolved
                    else "technical-validation-pending"
                ),
            )
            output["integrated_rule_families"].append("doctype-jats")
            output["pending_rule_families"].remove("doctype-jats")
        except Exception:
            output["structural_status"] = "unavailable"
            output["technical_errors_resolved"] = False
            output["homologation_disposition"] = "technical-validation-pending"
        return output
    except Exception:
        return unavailable
