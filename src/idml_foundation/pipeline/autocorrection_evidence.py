"""Opt-in provenance preparation before first snapshot persistence; never edits article text."""

import hashlib
import re
from collections.abc import Iterator
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Literal
from zipfile import ZipFile

from lxml import etree

from idml_foundation.ai.autocorrection_contracts import (
    PROFILE_SHA256,
    Digest,
    Identifier,
    Operation,
)
from idml_foundation.ai.autocorrection_policy import value_digest
from idml_foundation.domain.canonical import CanonicalArticle
from idml_foundation.domain.common import Evidence, StrictModel, content_digest, stable_id
from idml_foundation.ingest.safe_zip import inspect_idml
from idml_foundation.ingest.xml_security import parse_untrusted_xml
from idml_foundation.pipeline.jats_builder import JatsBuilder
from idml_foundation.pipeline.profile import JournalProfile
from idml_foundation.pipeline.service import DeterministicPipeline, PipelineResult
from idml_foundation.services.autocorrection_sources import (
    SourceResolutionError,
    _literal_text,
    source_element,
)
from idml_foundation.settings import Settings


class FieldBinding(StrictModel):
    operation: Operation
    subject_id: Identifier
    evidence_id: Identifier
    expected_value_sha256: Digest


class FieldEvidenceCatalog(StrictModel):
    version: Literal["autocorrection-field-catalog-1.0"] = "autocorrection-field-catalog-1.0"
    source_idml_sha256: Digest
    canonical_sha256: Digest
    profile_sha256: Digest
    bindings: tuple[FieldBinding, ...]


@dataclass(frozen=True)
class QualifiedFields:
    article: CanonicalArticle
    catalog: FieldEvidenceCatalog
    # Public diagnostics contain codes and identifiers only.
    refused: tuple[dict[str, str], ...]


def _missing(value: Any) -> bool:
    return value is None or (
        value.state == "missing" and value.value is None and not value.alternatives
    )


def _sections(sections: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    for section in sections:
        yield section
        yield from _sections(section["children"])


def _affiliation_lines(element: etree._Element, full: str) -> list[tuple[int, str]]:
    """Use exact text offsets even when the template uses separate superscript labels."""
    lines = [(m.start(), m.group()) for m in re.finditer(r"[^\r\n]+", full)]
    runs = list(element)
    if element.tag != "ParagraphStyleRange" or len(runs) != 2 * len(lines):
        return lines
    qualified = []
    for index, (offset, line) in enumerate(lines):
        marker, body = runs[2 * index : 2 * index + 2]
        label = str(index + 1)
        if (
            marker.tag != "CharacterStyleRange"
            or marker.get("AppliedCharacterStyle") != "CharacterStyle/sobrescrito"
            or [n.tag for n in marker] != ["Content"]
            or marker[0].text != label
            or body.tag != "CharacterStyleRange"
            or [n.tag for n in body] != ["Content", "Br"]
            or line != label + (body[0].text or "")
        ):
            return lines
        qualified.append((offset + len(label), line[len(label) :]))
    return qualified


def qualify_fields(
    article: CanonicalArticle, *, idml: bytes, profile: JournalProfile, settings: Settings
) -> QualifiedFields:
    """Add new exact evidence; preserve all prior evidence, values, ordering and IDs.

    Only already field-bound source locators may be inspected. No global search for
    convenient text. Ambiguous multiline affiliations/duplicate matches are refused.
    """
    article = CanonicalArticle.model_validate(article.model_dump(mode="python"))
    if (
        content_digest(profile) != PROFILE_SHA256
        or article.journal_profile_id != profile.profile_id
    ):
        raise ValueError("autocorrection_profile_not_qualified")
    inspect_idml(idml, settings)
    source_sha = hashlib.sha256(idml).hexdigest()
    raw = article.model_dump(mode="json")
    evidence_by_id = {e.id: e for e in article.evidence}
    bindings = []
    refused = []
    with ZipFile(BytesIO(idml)) as archive:
        roots: dict[str, etree._Element] = {}

        def prepare(
            operation: Operation, subject: dict[str, Any], value: Any, country: str | None = None
        ) -> None:
            if any(evidence_by_id[e].source_kind == "human" for e in subject["evidence_ids"]):
                refused.append({"subject_id": subject["id"], "code": "human_source_protected"})
                return
            candidates = []
            for evidence_id in subject["evidence_ids"]:
                evidence = evidence_by_id[evidence_id]
                if evidence.source_kind != "idml" or evidence.locator.artifact_sha256 != source_sha:
                    continue
                locator = evidence.locator
                # Existing precise slices must not be broadened to their parent.
                if locator.start_offset is not None or locator.end_offset is not None:
                    continue
                try:
                    if locator.logical_path not in roots:
                        roots[locator.logical_path] = parse_untrusted_xml(
                            archive.read(locator.logical_path)
                        )
                    element = source_element(roots[locator.logical_path], locator.element_id)
                    if operation == "figure-asset-exact":
                        if etree.QName(element).localname != "Link":
                            continue
                        text = element.get("LinkResourceURI", "")
                        if not text or text in {".", ".."} or any(c in text for c in "/\\:"):
                            continue
                        if (
                            len(
                                [
                                    a
                                    for a in article.assets
                                    if a.logical_name == text
                                    and a.state == "present"
                                    and a.sha256
                                    and a.media_type in {"image/jpeg", "image/png", "image/tiff"}
                                ]
                            )
                            != 1
                        ):
                            continue
                        exact = locator
                    else:
                        full = _literal_text(element)
                        institution = subject["institution"]["value"]
                        institution_pattern = re.compile(
                            r"(?<!\w)" + re.escape(institution) + r"(?!\w)"
                        )
                        # One complete source line with the exact institution, not another
                        # affiliation in the same paragraph or a partial scientific sentence.
                        lines = [
                            (offset, line)
                            for offset, line in _affiliation_lines(element, full)
                            if institution_pattern.search(line)
                        ]
                        if len(lines) != 1 or len(institution_pattern.findall(lines[0][1])) != 1:
                            continue
                        offset, line = lines[0]
                        if operation == "country-code-exact":
                            assert country is not None
                            matches = list(
                                re.finditer(r"(?<!\w)" + re.escape(country) + r"(?!\w)", line)
                            )
                            if len(matches) != 1 or line[matches[0].end() :].strip() not in {
                                "",
                                ".",
                            }:
                                continue
                            start, end = offset + matches[0].start(), offset + matches[0].end()
                        else:
                            # Recover a literal full line. Numbered/labelled lines need a
                            # separate qualified selector; never guess where a label ends.
                            text = line.strip()
                            if not text or text[0].isdigit():
                                continue
                            start = offset + len(line) - len(line.lstrip())
                            end = start + len(text)
                        text = full[start:end]
                        exact = locator.model_copy(
                            update={"start_offset": start, "end_offset": end}
                        )
                    if not 0 < len(text) <= 4096:
                        continue
                    candidates.append((exact, hashlib.sha256(text.encode()).hexdigest()))
                except (ValueError, KeyError, SourceResolutionError):
                    continue
            # A whole-story and a paragraph pointing at identical text are NOT independent
            # proofs of a unique field. Require one source selector, not a majority vote.
            unique = {
                content_digest({"locator": loc.model_dump(mode="json"), "sha": sha}): (loc, sha)
                for loc, sha in candidates
            }
            if len(unique) != 1:
                refused.append(
                    {
                        "operation": operation,
                        "subject_id": subject["id"],
                        "code": "field_source_missing_or_ambiguous",
                    }
                )
                return
            exact, sha = next(iter(unique.values()))
            key = content_digest(
                {
                    "operation": operation,
                    "subject": subject["id"],
                    "locator": exact.model_dump(mode="json"),
                    "sha": sha,
                }
            )
            evidence_id = stable_id(article.article_id, "auto-evidence", key)
            new = Evidence(
                id=evidence_id,
                source_kind="idml",
                locator=exact,
                content_sha256=sha,
                description="Exact IDML field extraction for VH-09",
            )
            if evidence_id in evidence_by_id and evidence_by_id[evidence_id] != new:
                raise ValueError("field_evidence_identity_conflict")
            if evidence_id not in evidence_by_id:
                raw["evidence"].append(new.model_dump(mode="json"))
                evidence_by_id[evidence_id] = new
            if evidence_id not in subject["evidence_ids"]:
                subject["evidence_ids"].append(evidence_id)
            if (
                operation == "country-code-exact"
                and evidence_id not in subject["country"]["evidence_ids"]
            ):
                subject["country"]["evidence_ids"].append(evidence_id)
            bindings.append(
                FieldBinding(
                    operation=operation,
                    subject_id=subject["id"],
                    evidence_id=evidence_id,
                    expected_value_sha256=value_digest(value),
                )
            )

        for index, affiliation in enumerate(article.front.affiliations):
            subject = raw["front"]["affiliations"][index]
            if affiliation.institution.state != "present" or affiliation.institution.alternatives:
                continue
            bound_ids = set(affiliation.evidence_ids + affiliation.institution.evidence_ids)
            if affiliation.country:
                bound_ids.update(affiliation.country.evidence_ids)
            if any(evidence_by_id[e].source_kind == "human" for e in bound_ids):
                refused.append({"subject_id": affiliation.id, "code": "human_source_protected"})
                continue
            if (
                _missing(affiliation.country_code)
                and affiliation.country is not None
                and affiliation.country.state == "present"
                and not affiliation.country.alternatives
                and affiliation.country.value in profile.country_codes
            ):
                prepare(
                    "country-code-exact",
                    subject,
                    affiliation.country_code,
                    affiliation.country.value,
                )
            if _missing(affiliation.original_text):
                prepare("affiliation-original-literal", subject, affiliation.original_text)
        for section in _sections(raw["body"]):
            for block in section["blocks"]:
                if block["kind"] == "figure" and block["asset_id"] is None:
                    prepare("figure-asset-exact", block, None)
    enriched = CanonicalArticle.model_validate(raw)
    if JatsBuilder(sps_version=profile.sps_version).build(enriched) != JatsBuilder(
        sps_version=profile.sps_version
    ).build(article):
        raise ValueError("provenance_changed_xml")
    return QualifiedFields(
        enriched,
        FieldEvidenceCatalog(
            source_idml_sha256=source_sha,
            canonical_sha256=content_digest(enriched),
            profile_sha256=content_digest(profile),
            bindings=tuple(bindings),
        ),
        tuple(refused),
    )


def qualify_pipeline_result(
    result: PipelineResult, *, idml: bytes, profile: JournalProfile, settings: Settings
) -> QualifiedFields:
    qualified = qualify_fields(result.canonical, idml=idml, profile=profile, settings=settings)
    if JatsBuilder(sps_version=profile.sps_version).build(qualified.article) != result.xml:
        raise ValueError("qualified_pipeline_xml_mismatch")
    return qualified


def run_evidence_ready_pipeline(
    pipeline: DeterministicPipeline,
    *,
    idml: bytes,
    logical_name: str,
    profile: JournalProfile,
    settings: Settings,
) -> tuple[PipelineResult, QualifiedFields]:
    """Opt-in ingestion entry point; result is ready for normal snapshot persistence.

    It does not reprocess/overwrite stored historical snapshots or enable the worker.
    """
    result = pipeline.run(idml, logical_name=logical_name)
    qualified = qualify_pipeline_result(result, idml=idml, profile=profile, settings=settings)
    return PipelineResult(result.raw, qualified.article, result.xml, result.validation), qualified
