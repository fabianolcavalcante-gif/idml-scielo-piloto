"""Rebuild only the two authorized development candidates; emit hashes, not content."""

import hashlib
import json
from pathlib import Path

from idml_foundation.domain.corpus import load_manifest
from idml_foundation.pipeline.profile import load_profile
from idml_foundation.pipeline.service import DeterministicPipeline
from idml_foundation.pipeline.validation import OfflineJatsValidator
from idml_foundation.release.package_builder import AssetPayload, PackageBuilder
from idml_foundation.services.enrichment import KINDS
from ops.gate_phase7_7c06 import _single_artifact
from ops.qualify_h1_enrichment import CASES

ROOT = Path(__file__).resolve().parents[1]


def figure_paths(root, manifest):
    paths = []
    pdf_parent = _single_artifact(root, manifest, "approved_pdf_reference").parent
    for item in manifest.artifacts:
        if item.role != "figure_asset":
            continue
        candidates = (root / item.logical_path, pdf_parent / Path(item.logical_path).name)
        matches = []
        for path in candidates:
            if path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(root):
                data = path.read_bytes()
                if len(data) == item.size_bytes and hashlib.sha256(data).hexdigest() == item.sha256:
                    matches.append(path.resolve())
        if len(set(matches)) != 1:
            raise ValueError("figure provenance unavailable or ambiguous")
        paths.append(matches[0])
    return paths


def main():
    rows = []
    for case, source_name, catalogs, expected in CASES:
        manifest = load_manifest(ROOT / f"corpus/manifests/{case}.json")
        corpus_root = (ROOT / source_name).parent.resolve()
        source = _single_artifact(corpus_root, manifest, "source_idml")
        options = {
            kind: KINDS[kind].model_validate_json(
                (ROOT / "benchmarks/private/output" / filename).read_bytes()
            )
            for kind, filename in catalogs.items()
        }
        result = DeterministicPipeline(**options).run(source.read_bytes(), logical_name=source.name)
        if hashlib.sha256(result.xml).hexdigest() != expected:
            raise ValueError("candidate parity failed")
        profile = load_profile()
        builder = PackageBuilder()
        files = builder.scielo_files(
            package_stem=profile.package_stem(result.canonical.article_id),
            xml=result.xml,
            pdf=_single_artifact(corpus_root, manifest, "approved_pdf_reference").read_bytes(),
            assets=tuple(
                AssetPayload(source_name=p.name, data=p.read_bytes())
                for p in figure_paths(corpus_root, manifest)
            ),
        )
        xml = files[0].data
        offline = OfflineJatsValidator(ROOT / "vendor/jats/1.3").validate(
            xml, asset_names={f.name for f in files if f.role == "asset"}
        )
        package = builder.build(
            article_id=result.canonical.article_id,
            profile_id=profile.profile_id,
            source_idml_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            files=files,
            validator_versions={},
        )
        output = ROOT / "benchmarks/private/output/h1-real" / case
        output.mkdir(parents=True, exist_ok=True)
        (output / "candidate.xml").write_bytes(xml)
        (output / "candidate.zip").write_bytes(package.archive)
        rows.append(
            {
                "case": case,
                "xml_sha256": hashlib.sha256(xml).hexdigest(),
                "package_sha256": package.package_sha256,
                "package_size": len(package.archive),
                "offline_valid": offline.valid,
                "source_parity": True,
            }
        )
    print(json.dumps(rows))


if __name__ == "__main__":
    main()
