"""Technical admission to a working draft; warnings remain pending, never accepted.

Only fresh server-generated revalidation records may reach this policy. Neither
HTTP clients nor model output supply formal reports or compatibility decisions.
"""

import re
from typing import Any

from idml_foundation.release.xpm_compatibility import TOOL_SHA256
from idml_foundation.release.xpm_sps_compatibility import VALIDATORS
from idml_foundation.release.xpm_structural_compatibility import NATIVE_QUALIFICATION_SHA256
from idml_foundation.services.validation_followups import query_followups, wayta_followup
from idml_foundation.services.validation_scope import scope_digest

POLICY = "autocorrection-working-draft-admission-1.0"
RULES = {
    "xpm-doi-journal-exact-1.0": "errors",
    "xpm-doi-article-exact-1.0": "errors",
    "xpm-sps110-version-table-1.0": "errors",
    "xpm-sps110-date-type-1.0": "blocking_errors",
    "xpm-sps110-date-combination-1.0": "blocking_errors",
    "xpm-jats13-legacy-dtd-1.0": "fatal_errors",
    "xpm-sps110-style-unavailable-1.0": "errors",
}


def _sha(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _counts(value: Any, keys: tuple[str, ...]) -> dict[str, int]:
    if (
        not isinstance(value, dict)
        or set(value) != set(keys)
        or any(type(v) is not int or not 0 <= v <= 100_000 for v in value.values())
    ):
        raise ValueError("promotion_counts_invalid")
    return value


def draft_admission(
    *,
    offline: dict[str, Any] | None,
    formal: dict[str, Any],
    xml_sha256: str,
    package_sha256: str,
    validation_scope: dict[str, str],
) -> dict[str, Any]:
    reasons: set[str] = set()
    pending: set[str] = set()
    try:
        scope_sha = scope_digest(validation_scope)
        if (
            validation_scope["xml_sha256"] != xml_sha256
            or validation_scope["package_sha256"] != package_sha256
        ):
            raise ValueError("promotion_scope_binding_invalid")
        if (
            not _sha(xml_sha256)
            or not _sha(package_sha256)
            or not offline
            or offline.get("valid") is not True
            or offline.get("xml_sha256") != xml_sha256
            or not isinstance(offline.get("issues"), list)
            or any(i.get("severity") != "warning" for i in offline["issues"])
        ):
            raise ValueError("promotion_offline_invalid")
        if offline["issues"]:
            pending.add("offline-warnings-review")
        if (
            formal.get("version") != "package-formal-assessment-1.0"
            or formal.get("xml_sha256") != xml_sha256
            or formal.get("package_sha256") != package_sha256
            or formal.get("required_validators") != ["packtools", "spsvalidator", "xpm"]
            or formal.get("ready_for_scielo") is not False
            or formal.get("production_activation_authorized") is not False
        ):
            raise ValueError("promotion_formal_binding_invalid")
        runs = formal["external_runs"]
        if len(runs) != 2 or {r["name"] for r in runs} != {"packtools", "spsvalidator"}:
            raise ValueError("promotion_modern_validation_missing")
        for run in runs:
            expected = xml_sha256 if run["name"] == "packtools" else package_sha256
            version, tool, _ = VALIDATORS[run["name"]]
            counts = _counts(run["counts"], ("blocking", "critical", "error", "warning"))
            if (
                run["status"] != "completed"
                or run.get("failure_code") is not None
                or run["candidate_sha256"] != expected
                or not _sha(run.get("report_sha256"))
                or run.get("tool_sha256") != tool
                or run.get("version") != version
                or run.get("unavailable_external_checks") != []
                or any(counts[k] for k in ("blocking", "critical", "error"))
            ):
                raise ValueError("promotion_modern_validation_failed")
            if counts["warning"]:
                pending.add(run["name"] + "-warnings-review")
        xpm = formal["xpm"]
        counts = _counts(xpm["counts"], ("blocking_errors", "fatal_errors", "errors", "warnings"))
        if (
            xpm.get("status") != "completed"
            or xpm.get("attested") is not True
            or xpm.get("candidate_package_sha256") != package_sha256
            or xpm.get("tool_sha256") != TOOL_SHA256
            or xpm.get("xpm_version") != "4.0.096"
            or not _sha(xpm.get("report_sha256"))
            or xpm.get("failure_code") is not None
            or type(xpm.get("parser_errors")) is not int
            or xpm["parser_errors"] < 0
            or xpm.get("parser_recovered") is not bool(xpm["parser_errors"])
        ):
            raise ValueError("promotion_xpm_validation_unavailable")
        if any(counts[k] for k in ("blocking_errors", "fatal_errors", "errors")):
            compat = xpm["compatibility"]
            if (
                compat.get("status") != "assessed"
                or compat.get("structural_status") != "assessed"
                or compat.get("structural_policy_version")
                != "xpm-homologation-structural-compatibility-1.0"
                or compat.get("technical_errors_resolved") is not True
                or compat.get("homologation_ready") is not False
                or compat.get("release_approved") is not False
                or compat.get("scope_sha256") != scope_sha
            ):
                raise ValueError("promotion_xpm_errors_unresolved")
            derived = dict(counts)
            occurrences = set()
            rule_ids = []
            for exception in compat["exceptions"]:
                rule = exception["rule_id"]
                key = RULES[rule]
                fingerprint = exception["occurrence_sha256"]
                if not _sha(fingerprint) or fingerprint in occurrences:
                    raise ValueError("promotion_compatibility_occurrence_invalid")
                if rule in {"xpm-jats13-legacy-dtd-1.0", "xpm-sps110-style-unavailable-1.0"} and (
                    exception.get("native_qualification_sha256") != NATIVE_QUALIFICATION_SHA256
                ):
                    raise ValueError("promotion_compatibility_proof_invalid")
                occurrences.add(fingerprint)
                rule_ids.append(rule)
                derived[key] -= 1
            if (
                sorted(rule_ids) != sorted([*RULES, "xpm-sps110-date-type-1.0"])
                or derived != compat["unresolved_counts"]
                or any(derived[k] != 0 for k in ("blocking_errors", "fatal_errors", "errors"))
            ):
                raise ValueError("promotion_compatibility_counts_invalid")
            pending.add("delivery-doctype-editorial-review")
        if counts["warnings"]:
            pending.add("xpm-warnings-review")
        if xpm.get("required_queries_complete") is not True:
            selected = xpm.get("selected_queries")
            if (
                not isinstance(selected, dict)
                or selected.get("selected_checks_matched") is not True
            ):
                raise ValueError("promotion_queries_incomplete_or_conflicting")
            rows = query_followups(selected)
            if not rows or any(r["status"] != "observed" for r in rows):
                raise ValueError("promotion_queries_incomplete_or_conflicting")
            wayta = wayta_followup(xpm.get("compatibility"))
            if (
                wayta["code"] != "wayta-service-observation"
                or xpm["compatibility"]["wayta"]["requirement"] != "advisory_for_qualified_profile"
            ):
                raise ValueError("promotion_wayta_applicability_unqualified")
            pending.update(("affiliation-source-review", "orcid-ownership-not-authenticated"))
        elif xpm.get("selected_queries") is not None:
            # Current semantic collection deliberately never claims all queries complete.
            raise ValueError("promotion_query_contract_inconsistent")
    except (KeyError, ValueError, TypeError, AttributeError):
        reasons.add("fresh-validation-not-qualified-for-working-draft")
    return dict(
        policy_version=POLICY,
        eligible=not reasons,
        reasons=sorted(reasons),
        pending_review=sorted(pending),
        warnings_accepted=False,
        release_approved=False,
        homologation_ready=False,
    )
