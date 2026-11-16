#!/usr/bin/env python3
"""Build and attest the private SPS package for corrective stage 7C-06."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any
from zipfile import ZipFile

from lxml import etree

from idml_foundation.ai.formula_catalog import FormulaTranscriptionCatalog
from idml_foundation.domain.canonical import FigureBlock, Section
from idml_foundation.domain.corpus import CorpusManifest, load_manifest, verify_manifest
from idml_foundation.pipeline.profile import load_profile
from idml_foundation.pipeline.service import DeterministicPipeline
from idml_foundation.pipeline.validation import OfflineJatsValidator
from idml_foundation.release.crossref_authority import CrossrefMetadataAuthorityCatalog
from idml_foundation.release.formal_metadata import FormalMetadataAuthorityCatalog
from idml_foundation.release.package_builder import (
    AssetPayload,
    PackageBuilder,
    PackageRole,
)

ROOT = Path(__file__).parents[1]
DEFAULT_MANIFEST = ROOT / "corpus/manifests/esa-e20240135.json"
DEFAULT_CONTRACT = ROOT / "benchmarks/qualification/contracts/e20240135-7c06-formal-v1.json"
DEFAULT_FORMAL_REPORT = (
    ROOT / "benchmarks/qualification/reports/formal-metadata-authority-e20240135-v1.json"
)
XLINK_HREF = "{http://www.w3.org/1999/xlink}href"
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path.name}")
    return value


def _compare_expected(actual: Any, expected: Any, *, path: str = "expected") -> list[str]:
    mismatches: list[str] = []
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return [path]
        for key, expected_value in expected.items():
            child = f"{path}.{key}"
            if key not in actual:
                mismatches.append(child)
            else:
                mismatches.extend(_compare_expected(actual[key], expected_value, path=child))
        return mismatches
    if actual != expected:
        mismatches.append(path)
    return mismatches


def _private_file(path: Path, description: str) -> Path:
    resolved = path.resolve(strict=True)
    if "private" not in {part.casefold() for part in resolved.parts}:
        raise ValueError(f"{description} must remain inside a private directory")
    return resolved


def _artifact_paths(root: Path, manifest: CorpusManifest, role: str) -> list[Path]:
    resolved: list[Path] = []
    for descriptor in manifest.artifacts:
        if descriptor.role != role:
            continue
        path = (root / Path(*PurePosixPath(descriptor.logical_path).parts)).resolve()
        if not path.is_relative_to(root) or path.is_symlink() or not path.is_file():
            raise ValueError(f"restricted artifact is unavailable: {role}")
        payload = path.read_bytes()
        if len(payload) != descriptor.size_bytes or _sha256(payload) != descriptor.sha256:
            raise ValueError(f"restricted artifact integrity failed: {role}")
        resolved.append(path)
    return resolved


def _single_artifact(root: Path, manifest: CorpusManifest, role: str) -> Path:
    paths = _artifact_paths(root, manifest, role)
    if len(paths) != 1:
        raise ValueError(f"manifest must contain exactly one {role} artifact")
    return paths[0]


def _figure_blocks(sections: tuple[Section, ...]) -> list[FigureBlock]:
    figures: list[FigureBlock] = []
    for section in sections:
        figures.extend(block for block in section.blocks if isinstance(block, FigureBlock))
        figures.extend(_figure_blocks(section.children))
    return figures


def _load_contract(path: Path, manifest: CorpusManifest) -> dict[str, Any]:
    contract = _load_object(path)
    if (
        contract.get("contract_version") != "1.0.0"
        or contract.get("stage") != "7C-06"
        or contract.get("corpus_id") != manifest.corpus_id
        or not isinstance(contract.get("expected"), dict)
    ):
        raise ValueError("invalid 7C-06 corrective contract")
    return contract


def _validator_findings(report: dict[str, Any]) -> dict[str, Any]:
    if report.get("adapter_contract") != "1.1.0":
        raise ValueError("validator adapter contract mismatch")
    result = report.get("result")
    if not isinstance(result, dict) or result.get("complete") is not True:
        raise ValueError("validator report is incomplete")
    findings = result.get("findings")
    if not isinstance(findings, list):
        raise ValueError("validator findings are missing")
    blocking = Counter(
        (str(item.get("response")), str(item.get("code")))
        for item in findings
        if isinstance(item, dict) and item.get("response") in {"critical", "error"}
    )
    warnings = Counter(
        str(item.get("code"))
        for item in findings
        if isinstance(item, dict) and item.get("response") == "warning"
    )
    summary = result.get("summary")
    if not isinstance(summary, dict):
        raise ValueError("validator summary is missing")
    return {
        "adapter_contract": report["adapter_contract"],
        "validator_version": report.get("validator_version"),
        "summary": summary,
        "blocking_findings": [
            {"response": response, "code": code, "count": count}
            for (response, code), count in sorted(blocking.items())
        ],
        "warning_findings": [
            {"code": code, "count": count} for code, count in sorted(warnings.items())
        ],
    }


def _xml_evidence(
    candidate: bytes, reference: bytes, formal: FormalMetadataAuthorityCatalog
) -> dict[str, Any]:
    parser = etree.XMLParser(
        resolve_entities=False,
        load_dtd=False,
        no_network=True,
        recover=False,
        huge_tree=False,
    )
    root = etree.fromstring(candidate, parser=parser)
    reference_root = etree.fromstring(reference, parser=parser)
    ids = {str(value) for value in root.xpath("//@id")}
    xrefs = root.xpath("body//xref[@rid]")
    xref_targets = [str(item.get("rid")) for item in xrefs]
    objects = root.xpath("body//fig | body//table-wrap | body//disp-formula")
    object_ids = {str(item.get("id")) for item in objects if item.get("id")}
    graphics = root.xpath("body//fig/graphic")
    alt_texts = [graphic.findtext("alt-text") or "" for graphic in graphics]
    contributor_affiliations = root.xpath(
        "front/article-meta/contrib-group/contrib/xref[@ref-type='aff']"
    )
    affiliation_ids = {str(item.get("id")) for item in root.xpath("front/article-meta/aff")}
    roles = root.xpath("front/article-meta/contrib-group/contrib/role")
    history = sorted(
        str(item.get("date-type")) for item in root.xpath("front/article-meta/history/date")
    )
    reference_history = sorted(
        str(item.get("date-type"))
        for item in reference_root.xpath("front/article-meta/history/date")
    )
    candidate_states = len(root.xpath("front/article-meta/aff/addr-line/state"))
    reference_states = len(reference_root.xpath("front/article-meta/aff/addr-line/state"))
    orcids = root.xpath(
        "front/article-meta/contrib-group/contrib/contrib-id[@contrib-id-type='orcid']"
    )
    article_dois = [
        str(value).strip().casefold()
        for value in root.xpath("front/article-meta/article-id[@pub-id-type='doi']/text()")
    ]
    inline_formulas = root.xpath("body//inline-formula")
    display_formulas = root.xpath("body//disp-formula")
    formula_ids = [str(item.get("id")) for item in (*inline_formulas, *display_formulas)]
    mml_ids = [str(value) for value in root.xpath("//*[local-name()='math']/@id")]
    references = root.xpath("back/ref-list/ref")
    element_citations = root.xpath("back/ref-list/ref/element-citation")
    return {
        "article_doi_authorized": article_dois == [formal.doi.casefold()],
        "affiliation_xrefs": len(contributor_affiliations),
        "affiliation_xrefs_resolve": all(
            str(item.get("rid")) in affiliation_ids for item in contributor_affiliations
        ),
        "credit_roles": len(roles),
        "credit_roles_have_uri": all(
            str(item.get("content-type", "")).startswith("https://credit.niso.org/")
            for item in roles
        ),
        "affiliation_states": {
            "candidate": candidate_states,
            "approved_reference": reference_states,
            "parity": candidate_states == reference_states,
        },
        "history_date_types": history,
        "approved_reference_history_date_types": reference_history,
        "required_history_dates_present": {"received", "accepted"} <= set(history),
        "revision_date_absence_parity": not (
            {"rev-request", "rev-recd"} & set(history)
            or {"rev-request", "rev-recd"} & set(reference_history)
        ),
        "source_authenticated_orcids": len(orcids),
        "object_cross_references": len(xrefs),
        "object_cross_references_resolve": all(target in ids for target in xref_targets),
        "all_objects_have_incoming_reference": object_ids <= set(xref_targets),
        "figures": len(root.xpath("body//fig")),
        "tables": len(root.xpath("body//table-wrap")),
        "display_formulas": len(display_formulas),
        "inline_formulas": len(inline_formulas),
        "formula_ids_prefixed": all(value.startswith("e-") for value in formula_ids),
        "mathml_ids_prefixed": all(value.startswith("m-") for value in mml_ids),
        "figure_alt_texts": len(alt_texts),
        "figure_alt_texts_valid": all(0 < len(value) <= 120 for value in alt_texts),
        "references": len(references),
        "structured_references": len(element_citations),
    }


def _package_evidence(archive: bytes, package_stem: str) -> dict[str, Any]:
    from io import BytesIO

    with ZipFile(BytesIO(archive)) as package:
        names = sorted(package.namelist())
        xml_names = [name for name in names if name.endswith(".xml")]
        pdf_names = [name for name in names if name.casefold().endswith(".pdf")]
        jpg_names = [name for name in names if name.casefold().endswith(".jpg")]
        manifest = json.loads(package.read("conversion-manifest.json"))
        packaged_xml = package.read(xml_names[0]) if len(xml_names) == 1 else b""
        root = etree.fromstring(packaged_xml) if packaged_xml else None
        hrefs = (
            [
                str(value)
                for value in root.xpath(
                    "body//graphic/@xlink:href",
                    namespaces={"xlink": "http://www.w3.org/1999/xlink"},
                )
            ]
            if root is not None
            else []
        )
    return {
        "files": len(names) - 1,
        "xml_files": len(xml_names),
        "pdf_files": len(pdf_names),
        "jpeg_files": len(jpg_names),
        "conventional_pdf_name": pdf_names == [f"{package_stem}.pdf"],
        "all_graphics_resolve": sorted(hrefs) == jpg_names,
        "pdf_equation_assets": sum("eq" in name.casefold() for name in pdf_names),
        "candidate_set_sha256": manifest.get("candidate_set_sha256"),
        "validator_versions": manifest.get("validator_versions"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--formal-report", type=Path, default=DEFAULT_FORMAL_REPORT)
    parser.add_argument("--corpus-root", type=Path)
    parser.add_argument("--formula-catalog", type=Path)
    parser.add_argument("--metadata-authority-catalog", type=Path)
    parser.add_argument("--formal-metadata-catalog", type=Path)
    parser.add_argument("--packtools-json", type=Path)
    parser.add_argument("--spsvalidator-json", type=Path)
    parser.add_argument("--private-candidate-output", type=Path)
    parser.add_argument("--private-packaged-xml-output", type=Path)
    parser.add_argument("--private-package-output", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--metadata-only", action="store_true")
    parser.add_argument("--build-only", action="store_true")
    arguments = parser.parse_args()

    manifest_path = arguments.manifest.resolve(strict=True)
    manifest = load_manifest(manifest_path)
    formal_report_path = arguments.formal_report.resolve(strict=True)
    formal_report = _load_object(formal_report_path)
    contract = (
        None
        if arguments.build_only
        else _load_contract(arguments.contract.resolve(strict=True), manifest)
    )
    role_counts = {
        role: sum(item.role == role for item in manifest.artifacts)
        for role in (
            "source_idml",
            "approved_xml_reference",
            "approved_pdf_reference",
            "figure_asset",
        )
    }
    metadata_actual = {
        "role_counts": role_counts,
        "formal_metadata_authority": {
            "report_sha256": _sha256(formal_report_path.read_bytes()),
            "catalog_id": formal_report.get("catalog_id"),
            "crossref_response_sha256": formal_report.get("crossref_response_sha256"),
            "formal_reference_sha256": formal_report.get("formal_reference_sha256"),
            "publication_fields": formal_report.get("publication_fields"),
            "human_review_required": formal_report.get("human_review_required"),
            "restricted_content_emitted": formal_report.get("restricted_content_emitted"),
        },
    }
    metadata_mismatches = (
        []
        if contract is None
        else _compare_expected(
            metadata_actual,
            {
                key: contract["expected"][key]
                for key in ("role_counts", "formal_metadata_authority")
            },
        )
    )
    report: dict[str, Any] = {
        "version": "phase7-7c06-gate-1.0",
        "stage": "7C-06",
        "corpus_id": manifest.corpus_id,
        "metadata": {
            "manifest_sha256": _sha256(manifest_path.read_bytes()),
            **metadata_actual,
            "mismatches": metadata_mismatches,
            "approved": not metadata_mismatches,
        },
        "network_required_by_gate": False,
        "restricted_content_emitted": False,
        "release_ready": False,
        "xpm_sps_1_10": {"status": "pending_windows_execution"},
        "approved": not metadata_mismatches,
    }

    if not arguments.metadata_only:
        required = (
            arguments.corpus_root,
            arguments.formula_catalog,
            arguments.metadata_authority_catalog,
            arguments.formal_metadata_catalog,
        )
        if any(value is None for value in required):
            parser.error("private corpus and all three authority catalogs are required")
        corpus_root = arguments.corpus_root.resolve(strict=True)
        verification = verify_manifest(manifest, corpus_root)
        source_path = _single_artifact(corpus_root, manifest, "source_idml")
        reference_path = _single_artifact(corpus_root, manifest, "approved_xml_reference")
        pdf_path = _single_artifact(corpus_root, manifest, "approved_pdf_reference")
        figure_paths = _artifact_paths(corpus_root, manifest, "figure_asset")
        formula = FormulaTranscriptionCatalog.model_validate(
            _load_object(_private_file(arguments.formula_catalog, "formula catalog"))
        )
        metadata = CrossrefMetadataAuthorityCatalog.model_validate(
            _load_object(
                _private_file(arguments.metadata_authority_catalog, "metadata authority catalog")
            )
        )
        formal = FormalMetadataAuthorityCatalog.model_validate(
            _load_object(
                _private_file(arguments.formal_metadata_catalog, "formal metadata catalog")
            )
        )
        pipeline = DeterministicPipeline(
            formula_catalog=formula,
            crossref_metadata_catalog=metadata,
            formal_metadata_catalog=formal,
        )
        source = source_path.read_bytes()
        first = pipeline.run(source, logical_name=source_path.name)
        second = pipeline.run(source, logical_name=source_path.name)
        figure_blocks = _figure_blocks(first.canonical.body)
        if len(figure_blocks) != len(figure_paths):
            raise ValueError("candidate figure count differs from the corpus")
        if any(block.asset_id is None for block in figure_blocks):
            raise ValueError("candidate figure is not bound to a source asset")
        figure_paths.sort(key=lambda item: item.name.casefold())
        payloads = tuple(
            AssetPayload(
                source_name=path.name,
                data=path.read_bytes(),
                media_type="image/jpeg",
            )
            for block, path in zip(figure_blocks, figure_paths, strict=True)
            if block.asset_id is not None
        )
        profile = load_profile()
        package_stem = profile.package_stem(first.canonical.article_id)
        builder = PackageBuilder()
        files = builder.scielo_files(
            package_stem=package_stem,
            xml=first.xml,
            pdf=pdf_path.read_bytes(),
            assets=payloads,
        )
        packaged_xml = next(item.data for item in files if item.role == PackageRole.XML)
        offline = OfflineJatsValidator(ROOT / "vendor/jats/1.3").validate(
            packaged_xml,
            asset_names={item.name for item in files if item.role == PackageRole.ASSET},
        )
        validator_versions = {
            "offline-jats": offline.validator_profile,
            "packtools": "4.17.2+ef0e6f874ea7",
            "spsvalidator": "0.3.0+d1aa774d4e33",
        }
        package = builder.build(
            article_id=first.canonical.article_id,
            profile_id=profile.profile_id,
            source_idml_sha256=_sha256(source),
            files=files,
            validator_versions=validator_versions,
        )
        repeated = builder.build(
            article_id=first.canonical.article_id,
            profile_id=profile.profile_id,
            source_idml_sha256=_sha256(source),
            files=files,
            validator_versions=validator_versions,
        )
        validators: dict[str, Any] = {}
        if not arguments.build_only:
            if arguments.packtools_json is None or arguments.spsvalidator_json is None:
                parser.error("both validator reports are required for the full gate")
            for name, path, expected_hash in (
                ("packtools", arguments.packtools_json, _sha256(packaged_xml)),
                ("spsvalidator", arguments.spsvalidator_json, package.package_sha256),
            ):
                validator = _load_object(path.resolve(strict=True))
                if validator.get("validator_name") != name:
                    raise ValueError(f"wrong validator report supplied for {name}")
                if validator.get("candidate_sha256") != expected_hash:
                    raise ValueError(f"{name} report belongs to another candidate")
                validators[name] = _validator_findings(validator)

        actual = {
            **metadata_actual,
            "source_idml_sha256": _sha256(source),
            "formula_catalog_id": formula.catalog_id,
            "metadata_authority_catalog_id": metadata.catalog_id,
            "formal_metadata_catalog_id": formal.catalog_id,
            "candidate_xml_sha256": _sha256(first.xml),
            "packaged_xml_sha256": _sha256(packaged_xml),
            "package_sha256": package.package_sha256,
            "package_size_bytes": package.package_size_bytes,
            "deterministic": first.xml == second.xml and package.archive == repeated.archive,
            "offline_validation": {"valid": offline.valid, "issues": len(offline.issues)},
            "xml_evidence": _xml_evidence(first.xml, reference_path.read_bytes(), formal),
            "package_evidence": _package_evidence(package.archive, package_stem),
            "validators": validators,
        }
        mismatches = [] if contract is None else _compare_expected(actual, contract["expected"])
        approved = bool(
            verification.valid
            and actual["deterministic"]
            and actual["offline_validation"]["valid"]
            and not metadata_mismatches
            and not mismatches
            and not arguments.build_only
        )
        report.update(
            {
                "physical_verification": {
                    "valid": verification.valid,
                    "artifacts": len(verification.artifacts),
                    "verified": sum(item.valid for item in verification.artifacts),
                },
                "actual": actual,
                "contract_mismatches": mismatches,
                "accepted_validator_findings": sum(
                    int(item["count"])
                    for validator in validators.values()
                    for item in validator["blocking_findings"]
                ),
                "real_critical_errors": 0 if approved else None,
                "formal_package_approved": approved,
                "approved": approved,
            }
        )
        outputs = (
            (arguments.private_candidate_output, first.xml),
            (arguments.private_packaged_xml_output, packaged_xml),
            (arguments.private_package_output, package.archive),
        )
        for path, payload in outputs:
            if path is None:
                continue
            resolved = path.resolve()
            if "private" not in {part.casefold() for part in resolved.parts}:
                raise ValueError("private outputs must remain inside a private directory")
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_bytes(payload)

    serialized = json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    if arguments.output is not None:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(serialized, encoding="utf-8")
    else:
        print(serialized, end="")
    return 0 if report["approved"] or arguments.build_only else 2


if __name__ == "__main__":
    raise SystemExit(main())
