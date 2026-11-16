"""Package the qualified metadata candidate without replacing the historical baseline."""

import hashlib
import json
from pathlib import Path

from idml_foundation.domain.corpus import load_manifest
from idml_foundation.pipeline.profile import load_profile
from idml_foundation.pipeline.validation import OfflineJatsValidator
from idml_foundation.release.package_builder import AssetPayload, PackageBuilder
from ops.build_h1_real_packages import figure_paths
from ops.gate_phase7_7c06 import _single_artifact

ROOT = Path(__file__).resolve().parents[1]


def main():
    folder = ROOT / "benchmarks/private/output/h1-publication-metadata-v1"
    evidence_path = ROOT / "benchmarks/qualification/reports/h1-publication-metadata-v1.json"
    evidence = json.loads(evidence_path.read_text())
    xml = (folder / "candidate.xml").read_bytes()
    if hashlib.sha256(xml).hexdigest() != evidence["after_xml_sha256"]:
        raise ValueError("corrected candidate differs from qualified metadata evidence")
    manifest = load_manifest(ROOT / "corpus/manifests/esa-e20240086.json")
    corpus = (ROOT / "tmp/sample").resolve()
    source = _single_artifact(corpus, manifest, "source_idml").read_bytes()
    profile = load_profile()
    builder = PackageBuilder()
    files = builder.scielo_files(
        package_stem=profile.package_stem("e20240086"),
        xml=xml,
        pdf=_single_artifact(corpus, manifest, "approved_pdf_reference").read_bytes(),
        assets=tuple(
            AssetPayload(source_name=p.name, data=p.read_bytes())
            for p in figure_paths(corpus, manifest)
        ),
    )
    kwargs = dict(
        article_id="e20240086",
        profile_id=profile.profile_id,
        source_idml_sha256=hashlib.sha256(source).hexdigest(),
        files=files,
        validator_versions={},
    )
    package = builder.build(**kwargs)
    if builder.build(**kwargs).archive != package.archive:
        raise ValueError("non-deterministic package")
    packaged_xml = files[0].data
    offline = OfflineJatsValidator(ROOT / "vendor/jats/1.3").validate(
        packaged_xml, asset_names={f.name for f in files if f.role == "asset"}
    )
    if not offline.valid:
        raise ValueError("packaged candidate failed offline validation")
    (folder / "packaged.xml").write_bytes(packaged_xml)
    (folder / "candidate.zip").write_bytes(package.archive)
    report = {
        "version": "h1-corrected-package-1.0",
        "corpus_id": "esa-e20240086",
        "metadata_report_sha256": hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
        "xml_sha256": hashlib.sha256(packaged_xml).hexdigest(),
        "package_sha256": package.package_sha256,
        "package_size_bytes": package.package_size_bytes,
        "files": len(package.manifest.files),
        "deterministic": True,
        "offline_valid": True,
        "vps_validation": "not-run-memory-reserve",
        "ready_for_scielo": False,
    }
    (ROOT / "benchmarks/qualification/reports/h1-corrected-package-v1.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report))


if __name__ == "__main__":
    main()
