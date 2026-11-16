"""Replay the two journal regression articles using only their frozen input catalogs."""

import json
from hashlib import sha256
from zipfile import ZipFile

from idml_foundation.domain.corpus import load_manifest
from idml_foundation.pipeline.profile import load_profile
from idml_foundation.pipeline.service import DeterministicPipeline
from idml_foundation.release.package_builder import AssetPayload, PackageBuilder
from idml_foundation.services.enrichment import KINDS
from ops.build_h1_real_packages import figure_paths
from ops.gate_phase7_7c06 import _single_artifact
from ops.qualify_vh1_doctype import JATS_PUBLIC_ID, OLD
from ops.qualify_vh1_journal_metadata import CASES, METADATA, ROOT, TYPE_BASELINE

CATALOG_SOURCES = (
    "src/idml_foundation/pipeline/affiliation_hierarchy.py",
    "src/idml_foundation/release/institution_locations.py",
    "src/idml_foundation/release/reference_types.py",
)
BASELINE_REPORT = "benchmarks/qualification/reports/vh1-journal-metadata-linux-v1.json"


def replay():
    root = ROOT / "benchmarks/private/output"
    old = root / "vh1-journal-metadata-20261016T165250Z"
    report_bytes = (ROOT / BASELINE_REPORT).read_bytes()
    plan = json.loads(report_bytes)["qualification"]
    ref = plan["cases"]
    out = {}
    for case, name in CASES.items():
        path = ROOT / name
        manifest = load_manifest(ROOT / f"corpus/manifests/{case}.json")
        source = path.read_bytes()
        pdf = _single_artifact(path.parent, manifest, "approved_pdf_reference").read_bytes()
        catalogs = {}
        pinned = {}
        for base in [
            root / "h1-country-codes-v1" / case,
            METADATA / case,
            TYPE_BASELINE / case,
            old / case,
        ]:
            for kind, cls in KINDS.items():
                p = base / (kind + ".json")
                if p.exists():
                    data = p.read_bytes()
                    catalogs[kind] = cls.model_validate_json(data)
                    pinned[kind] = sha256(data).hexdigest()
        profile = load_profile(ROOT / "profiles/esa-aop-1.1.json")
        result = DeterministicPipeline(profile=profile, **catalogs).run(
            source, logical_name=path.name
        )
        builder = PackageBuilder()
        files = builder.scielo_files(
            package_stem=profile.package_stem(result.canonical.article_id),
            xml=result.xml,
            pdf=pdf,
            assets=tuple(
                AssetPayload(source_name=p.name, data=p.read_bytes())
                for p in figure_paths(path.parent, manifest)
            ),
        )
        xml = files[0].data
        original = (old / case / "candidate.xml").read_bytes()
        assert (
            sha256(original).hexdigest() == ref[case]["xml_sha256"]
            and sha256(source).hexdigest() == ref[case]["source_idml_sha256"]
        )
        assert sha256(pdf).hexdigest() == ref[case]["source_pdf_sha256"] and result.validation.valid
        expected = original.replace(OLD, JATS_PUBLIC_ID.encode(), 1)
        assert original.count(OLD) == 1 and expected == xml, case
        package = old / case / "candidate.zip"
        assert sha256(package.read_bytes()).hexdigest() == ref[case]["package_sha256"]
        with ZipFile(package) as baseline:
            assert set(baseline.namelist()) == {f.name for f in files} | {
                "conversion-manifest.json"
            }
            assert all(baseline.read(f.name) == f.data for f in files[1:])
        out[case] = dict(
            catalogs=pinned,
            prior_xml_sha256=sha256(original).hexdigest(),
            xml_sha256=sha256(xml).hexdigest(),
            source_sha256=sha256(source).hexdigest(),
            unchanged_members=len(files) - 1,
        )
    return dict(
        cases=out,
        baseline_sha256=sha256(report_bytes).hexdigest(),
        before={p: plan["source_sha256"][p] for p in CATALOG_SOURCES},
        after={p: sha256((ROOT / p).read_bytes()).hexdigest() for p in CATALOG_SOURCES},
        audit_sha256=sha256((ROOT / "ops/qualify_vh17_catalog_replay.py").read_bytes()).hexdigest(),
        replay_only=True,
        new_provider_calls=0,
        release_approved=False,
    )


if __name__ == "__main__":
    print(json.dumps(replay(), indent=2, sort_keys=True))
