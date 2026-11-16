from __future__ import annotations

import hashlib
from typing import Any, Literal, Self

from pydantic import Field, model_validator

from idml_foundation.ai.security import payload_digest
from idml_foundation.domain.common import SHA256_PATTERN, StrictModel
from idml_foundation.domain.metrics import normalize_text
from idml_foundation.pipeline.crossref_evaluation import TargetDelta
from idml_foundation.release.semantic_fidelity import (
    SemanticChangeKind,
    SemanticFidelityReport,
)

CATALOG_VERSION = "source-authority-qualification-1.0"
REPORT_VERSION = "source-authority-qualification-report-1.0"


class QualifiedMetadataDifference(StrictModel):
    expected_position: int = Field(ge=1)
    actual_position: int = Field(ge=1)
    expected_sha256: str = Field(pattern=SHA256_PATTERN)
    actual_sha256: str = Field(pattern=SHA256_PATTERN)
    authority: Literal["journal-profile", "source-idml"]


class SourceAuthorityQualification(StrictModel):
    version: Literal["source-authority-qualification-1.0"]
    qualification_id: str = Field(pattern=SHA256_PATTERN)
    corpus_id: str = Field(min_length=3, max_length=100)
    journal_profile_id: str = Field(min_length=3, max_length=100)
    source_idml_sha256: str = Field(pattern=SHA256_PATTERN)
    approved_xml_sha256: str = Field(pattern=SHA256_PATTERN)
    crossref_evidence_sha256: str = Field(pattern=SHA256_PATTERN)
    metadata_differences: tuple[QualifiedMetadataDifference, ...]
    expected_target_deficits: tuple[TargetDelta, ...]
    actual_target_surpluses: tuple[TargetDelta, ...]
    human_review_required: Literal[True]

    @model_validator(mode="after")
    def qualification_is_narrow_and_content_addressed(self) -> Self:
        if len(self.metadata_differences) != 2:
            raise ValueError("source authority requires exactly two metadata differences")
        authorities = {item.authority for item in self.metadata_differences}
        if authorities != {"journal-profile", "source-idml"}:
            raise ValueError("source authority metadata evidence is incomplete")
        if not self.expected_target_deficits or not self.actual_target_surpluses:
            raise ValueError("source authority cross-reference evidence is incomplete")
        payload = self.model_dump(mode="json", exclude={"qualification_id"})
        if payload_digest(payload) != self.qualification_id:
            raise ValueError("source authority qualification ID mismatch")
        return self

    def apply(
        self,
        report: SemanticFidelityReport,
        *,
        source_idml_sha256: str,
    ) -> tuple[SemanticFidelityReport, dict[str, int]]:
        if source_idml_sha256 != self.source_idml_sha256:
            raise ValueError("source authority IDML hash mismatch")
        if report.reference_xml_sha256 != self.approved_xml_sha256:
            raise ValueError("source authority approved XML hash mismatch")
        expected = {
            (
                item.expected_position,
                item.actual_position,
                item.expected_sha256,
                item.actual_sha256,
            )
            for item in self.metadata_differences
        }
        observed = {
            (
                item.expected_position,
                item.actual_position,
                item.expected_sha256,
                item.actual_sha256,
            )
            for item in report.findings
            if item.domain == "metadata" and item.blocking
        }
        if observed != expected:
            raise ValueError("source authority metadata differences changed")
        if (
            report.cross_references.expected_target_deficits != self.expected_target_deficits
            or report.cross_references.actual_target_surpluses != self.actual_target_surpluses
        ):
            raise ValueError("source authority cross-reference differences changed")
        findings = tuple(
            finding.model_copy(update={"blocking": False})
            if finding.domain == "metadata" and finding.blocking
            else finding
            for finding in report.findings
        )
        domains = tuple(
            score.model_copy(update={"passed": True}) if score.domain == "metadata" else score
            for score in report.domains
        )
        cross_references = report.cross_references.model_copy(
            update={"decision": "source_qualified"}
        )
        blocking = sum(finding.blocking for finding in findings)
        reconciled = report.model_copy(
            update={
                "domains": domains,
                "findings": findings,
                "cross_references": cross_references,
                "blocking_findings": blocking,
                "passed": blocking == 0,
            }
        )
        return reconciled, {
            "metadata_differences": len(self.metadata_differences),
            "bibliographic_occurrences": max(
                sum(item.occurrences for item in self.expected_target_deficits),
                sum(item.occurrences for item in self.actual_target_surpluses),
            ),
        }


def _normalized_sha256(value: str) -> str:
    return hashlib.sha256(normalize_text(value).encode("utf-8")).hexdigest()


def build_source_authority_qualification(
    *,
    report: SemanticFidelityReport,
    corpus_id: str,
    journal_profile_id: str,
    source_idml_sha256: str,
    journal_title: str,
    primary_article_title: str,
    crossref_evidence: dict[str, Any],
    crossref_evidence_sha256: str,
) -> tuple[SourceAuthorityQualification, dict[str, Any]]:
    if (
        crossref_evidence.get("version") != "esa-crossrefs-1.0"
        or crossref_evidence.get("corpus_id") != corpus_id
        or crossref_evidence.get("source_idml_sha256") != source_idml_sha256
        or crossref_evidence.get("approved_xml_sha256") != report.reference_xml_sha256
        or crossref_evidence.get("runtime_uses_approved_xml") is not False
        or crossref_evidence.get("generated_xml_valid") is not True
    ):
        raise ValueError("source authority cross-reference evidence provenance mismatch")
    target_deltas = crossref_evidence.get("target_deltas", {})
    expected_deficits = tuple(
        TargetDelta.model_validate(item) for item in target_deltas.get("expected_deficits", [])
    )
    actual_surpluses = tuple(
        TargetDelta.model_validate(item) for item in target_deltas.get("actual_surpluses", [])
    )
    if (
        expected_deficits != report.cross_references.expected_target_deficits
        or actual_surpluses != report.cross_references.actual_target_surpluses
        or len(crossref_evidence.get("technical_adjudication_candidates", [])) != 2
    ):
        raise ValueError("source authority cross-reference evidence no longer matches")
    blocking_metadata = [
        finding for finding in report.findings if finding.domain == "metadata" and finding.blocking
    ]
    authoritative_values = {
        1: (journal_title, "journal-profile"),
        2: (primary_article_title, "source-idml"),
    }
    if len(blocking_metadata) != len(authoritative_values):
        raise ValueError("source authority metadata difference count changed")
    metadata: list[QualifiedMetadataDifference] = []
    for finding in blocking_metadata:
        position = finding.actual_position
        if (
            position not in authoritative_values
            or finding.expected_position != position
            or finding.kind != SemanticChangeKind.ALTERATION
            or finding.actual_sha256 is None
            or finding.expected_sha256 is None
        ):
            raise ValueError("source authority metadata difference is not eligible")
        value, authority = authoritative_values[position]
        if finding.actual_sha256 != _normalized_sha256(value):
            raise ValueError("source authority metadata value does not match its source")
        metadata.append(
            QualifiedMetadataDifference(
                expected_position=position,
                actual_position=position,
                expected_sha256=finding.expected_sha256,
                actual_sha256=finding.actual_sha256,
                authority=authority,
            )
        )
    base = {
        "version": CATALOG_VERSION,
        "corpus_id": corpus_id,
        "journal_profile_id": journal_profile_id,
        "source_idml_sha256": source_idml_sha256,
        "approved_xml_sha256": report.reference_xml_sha256,
        "crossref_evidence_sha256": crossref_evidence_sha256,
        "metadata_differences": [
            item.model_dump(mode="json")
            for item in sorted(metadata, key=lambda item: item.actual_position)
        ],
        "expected_target_deficits": [item.model_dump(mode="json") for item in expected_deficits],
        "actual_target_surpluses": [item.model_dump(mode="json") for item in actual_surpluses],
        "human_review_required": True,
    }
    qualification = SourceAuthorityQualification.model_validate(
        {"qualification_id": payload_digest(base), **base}
    )
    public_report = {
        "version": REPORT_VERSION,
        "qualification_id": qualification.qualification_id,
        "corpus_id": corpus_id,
        "source_idml_sha256": source_idml_sha256,
        "approved_xml_sha256": report.reference_xml_sha256,
        "crossref_evidence_sha256": crossref_evidence_sha256,
        "metadata_differences": len(metadata),
        "bibliographic_occurrences": max(
            sum(item.occurrences for item in expected_deficits),
            sum(item.occurrences for item in actual_surpluses),
        ),
        "human_review_required": True,
        "restricted_content_emitted": False,
    }
    return qualification, public_report
