"""Execute the Phase 4 gate without publishing restricted corpus artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from lxml import etree

from idml_foundation.domain.canonical import FigureBlock
from idml_foundation.domain.common import canonical_bytes
from idml_foundation.pipeline.profile import load_profile
from idml_foundation.pipeline.service import DeterministicPipeline
from idml_foundation.pipeline.validation import OfflineJatsValidator
from idml_foundation.release.fidelity import FidelityEngine
from idml_foundation.release.package_builder import AssetPayload, PackageBuilder, PackageRole
from idml_foundation.release.policy import ReleasePolicy
from idml_foundation.release.validation_engine import ValidationEngine
from idml_foundation.release.xpm import XpmReportParser


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def resolve_artifact(source_root: Path, artifact: dict[str, object]) -> Path:
    """Resolve a manifest artifact relocated inside one restricted bundle by exact hash."""
    resolved_root = source_root.resolve(strict=True)
    logical_path = str(artifact["logical_path"])
    expected_digest = str(artifact["sha256"])
    expected_size = int(artifact["size_bytes"])
    direct = (resolved_root / logical_path).resolve()
    candidates = [direct] if direct.is_relative_to(resolved_root) and direct.is_file() else []
    if not candidates:
        candidates = [
            path.resolve()
            for path in resolved_root.rglob(Path(logical_path).name)
            if path.is_file() and not path.is_symlink()
        ]
    matches = [
        path
        for path in candidates
        if path.stat().st_size == expected_size and digest(path.read_bytes()) == expected_digest
    ]
    if len(matches) != 1:
        raise ValueError(f"artifact must resolve uniquely by manifest hash: {logical_path}")
    return matches[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--spsvalidator-json", type=Path)
    parser.add_argument(
        "--spsvalidator-tool-sha256",
        default="d743a2c07ca757495d32fc9617a5acd0b49bb0ae0d46bfac6f85198c11e409de",
    )
    parser.add_argument("--output-package", type=Path)
    parser.add_argument("--output-xml", type=Path)
    arguments = parser.parse_args()

    manifest = json.loads(arguments.manifest.read_text(encoding="utf-8"))
    artifact_by_role = {item["role"]: item for item in manifest["artifacts"]}
    source_path = resolve_artifact(arguments.source_root, artifact_by_role["source_idml"])
    pdf_path = resolve_artifact(arguments.source_root, artifact_by_role["approved_pdf_reference"])
    source = source_path.read_bytes()
    pdf = pdf_path.read_bytes()
    if digest(source) != artifact_by_role["source_idml"]["sha256"]:
        raise ValueError("source IDML hash does not match the restricted manifest")
    if digest(pdf) != artifact_by_role["approved_pdf_reference"]["sha256"]:
        raise ValueError("PDF hash does not match the restricted manifest")

    profile = load_profile()
    pipeline = DeterministicPipeline(profile=profile)
    result = pipeline.run(source, logical_name=source_path.name)
    figure_blocks = [
        block
        for section in result.canonical.body
        for block in section.blocks
        if isinstance(block, FigureBlock)
    ]
    asset_by_id = {item.id: item for item in result.canonical.assets}
    payloads: list[AssetPayload] = []
    figure_artifacts = sorted(
        (item for item in manifest["artifacts"] if item["role"] == "figure_asset"),
        key=lambda item: item["logical_path"],
    )
    if len(figure_blocks) != len(figure_artifacts):
        raise ValueError("figure count differs from the approved corpus manifest")
    for block, artifact in zip(figure_blocks, figure_artifacts, strict=True):
        if block.asset_id is None:
            raise ValueError("canonical figure has no source asset binding")
        asset_data = resolve_artifact(arguments.source_root, artifact).read_bytes()
        if digest(asset_data) != artifact["sha256"]:
            raise ValueError("figure asset hash differs from manifest")
        payloads.append(
            AssetPayload(
                source_name=asset_by_id[block.asset_id].logical_name,
                media_type=artifact["media_type"],
                data=asset_data,
            )
        )

    package_builder = PackageBuilder()
    package_stem = profile.package_stem(result.canonical.article_id)
    files = package_builder.scielo_files(
        package_stem=package_stem,
        xml=result.xml,
        pdf=pdf,
        assets=tuple(payloads),
    )
    resolved_xml = next(item.data for item in files if item.role == PackageRole.XML)
    resolved_assets = {item.name for item in files if item.role == PackageRole.ASSET}
    offline = OfflineJatsValidator(Path(__file__).parents[1] / "vendor" / "jats" / "1.3")
    offline_report = offline.validate(resolved_xml, asset_names=resolved_assets)
    validator_versions = {
        "offline-jats": offline_report.validator_profile,
        "packtools": "4.16.11-tag/internal-4.16.10",
        "spsvalidator": "0.3.0+d1aa774d4e33",
    }
    first = package_builder.build(
        article_id=result.canonical.article_id,
        profile_id=profile.profile_id,
        source_idml_sha256=digest(source),
        files=files,
        validator_versions=validator_versions,
    )
    second = package_builder.build(
        article_id=result.canonical.article_id,
        profile_id=profile.profile_id,
        source_idml_sha256=digest(source),
        files=files,
        validator_versions=validator_versions,
    )
    if first.archive != second.archive:
        raise ValueError("package builder is not byte deterministic")
    validation_engine = ValidationEngine()
    runs = [validation_engine.offline_run(offline_report, candidate_sha256=first.package_sha256)]
    if arguments.spsvalidator_json:
        spsvalidator = json.loads(arguments.spsvalidator_json.read_text(encoding="utf-8"))
        if spsvalidator["candidate_sha256"] != first.package_sha256:
            raise ValueError("SPSValidator output belongs to another package candidate")
        version = str(spsvalidator.get("spsvalidator_version", "0.3.0"))
        runs.append(
            validation_engine.external_run(
                first.archive,
                spsvalidator["result"],
                name="spsvalidator",
                version=version,
                tool_sha256=arguments.spsvalidator_tool_sha256,
            )
        )
    else:
        runs.append(
            validation_engine.unavailable(
                "spsvalidator",
                "0.3.0+d1aa774d4e33",
                first.archive,
                "spsvalidator-result-not-supplied",
            )
        )
    runs.append(
        validation_engine.unavailable(
            "packtools",
            "4.16.11-tag/internal-4.16.10",
            first.archive,
            "classic-stylechecker-does-not-accept-sps-1.10-jats-1.3",
        )
    )
    validation = validation_engine.aggregate(
        first.archive, tuple(runs), ("offline-jats", "spsvalidator")
    )
    fidelity = FidelityEngine().compare(result.canonical, resolved_xml, pdf)
    xpm = XpmReportParser().unavailable(first.package_sha256, "xpm-worker-not-configured")
    release = ReleasePolicy().assess(
        package_sha256=first.package_sha256,
        validation=validation,
        fidelity=fidelity,
        xpm=xpm,
        review_reasons=result.canonical.review_reasons,
    )
    if arguments.output_package:
        arguments.output_package.parent.mkdir(parents=True, exist_ok=True)
        arguments.output_package.write_bytes(first.archive)
    if arguments.output_xml:
        arguments.output_xml.parent.mkdir(parents=True, exist_ok=True)
        arguments.output_xml.write_bytes(resolved_xml)

    root = etree.fromstring(resolved_xml)
    report = {
        "gate": "G4",
        "gate_status": (
            "APPROVED" if release.decision == "ready-for-scielo" else "BLOCKED_EXTERNAL_GATE"
        ),
        "article_id": result.canonical.article_id,
        "source_idml_sha256": digest(source),
        "xml_sha256": digest(resolved_xml),
        "package_sha256": first.package_sha256,
        "package_size_bytes": first.package_size_bytes,
        "package_deterministic": first.archive == second.archive,
        "structure": {
            "figures": len(root.xpath("//fig")),
            "tables": len(root.xpath("//table-wrap")),
            "references": len(root.xpath("//ref")),
        },
        "validation": validation.model_dump(mode="json"),
        "validation_complete": validation.complete,
        "validation_valid": validation.valid,
        "fidelity": fidelity.model_dump(mode="json"),
        "release": release.model_dump(mode="json"),
        "manifest_sha256": digest(canonical_bytes(first.manifest)),
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if release.decision == "ready-for-scielo" else 2


if __name__ == "__main__":
    raise SystemExit(main())
