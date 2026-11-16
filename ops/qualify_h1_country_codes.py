"""Explicit laboratory profile migration; preserve catalogs and historical candidates."""

import hashlib
import json
from pathlib import Path

from lxml import etree

from idml_foundation.ai.security import payload_digest
from idml_foundation.domain.corpus import load_manifest
from idml_foundation.pipeline.profile import load_profile
from idml_foundation.pipeline.service import DeterministicPipeline
from idml_foundation.release.package_builder import AssetPayload, PackageBuilder
from idml_foundation.services.enrichment import KINDS
from ops.build_h1_real_packages import figure_paths
from ops.gate_phase7_7c06 import _single_artifact
from ops.qualify_h1_enrichment import CASES

ROOT = Path(__file__).resolve().parents[1]
ADDITIONS = {"Brazil": "BR", "Brasil": "BR", "Japan": "JP"}


def validate_profile_migration(old, new):
    expected = old.model_dump(mode="json")
    expected.update(profile_id="esa-aop-1.1.0", profile_version="1.1.0")
    expected["country_codes"] = {**old.country_codes, **ADDITIONS}
    if old.profile_id != "esa-aop-1.0.0" or new.model_dump(mode="json") != expected:
        raise ValueError("migration must change only the approved country mapping and version")
    if any(key in old.country_codes for key in ADDITIONS):
        raise ValueError("migration cannot overwrite existing mappings")


def verify_country_only_delta(before, after):
    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    old, new = etree.fromstring(before, parser), etree.fromstring(after, parser)
    left, right = (
        old.xpath("front/article-meta/aff/country"),
        new.xpath("front/article-meta/aff/country"),
    )
    if len(left) != len(right):
        raise ValueError("affiliation count changed")
    changed = 0
    for a, b in zip(left, right, strict=True):
        if a.get("country") != b.get("country"):
            if a.get("country") is not None or ADDITIONS.get(a.text) != b.get("country"):
                raise ValueError("unexpected country code change")
            b.attrib.pop("country")
            changed += 1
    if etree.tostring(old, method="c14n") != etree.tostring(new, method="c14n"):
        raise ValueError("non-country XML change")
    return changed


def main():
    old, new = load_profile(), load_profile(ROOT / "profiles/esa-aop-1.1.json")
    validate_profile_migration(old, new)
    output = ROOT / "benchmarks/private/output/h1-country-codes-v1"
    rows = []
    for index, (case, source_name, catalogs, expected) in enumerate(CASES):
        selected = dict(catalogs)
        if index == 0:
            selected["formal_metadata_catalog"] = (
                "h1-publication-metadata-v1/formal-metadata-catalog.json"
            )
            expected = "183dd2595a3b7d115075b426b7542acaac75dbfae2c785a3a64c41d8a291f61a"
        manifest = load_manifest(ROOT / f"corpus/manifests/{case}.json")
        corpus = (ROOT / source_name).parent.resolve()
        source = _single_artifact(corpus, manifest, "source_idml")
        data = source.read_bytes()
        options, migrated, provenance = {}, {}, {}
        for kind, filename in selected.items():
            catalog = KINDS[kind].model_validate_json(
                (ROOT / "benchmarks/private/output" / filename).read_bytes()
            )
            if catalog.journal_profile_id != old.profile_id:
                raise ValueError("unexpected catalog profile")
            options[kind] = catalog
            payload = catalog.model_dump(mode="json", exclude={"catalog_id"})
            payload["journal_profile_id"] = new.profile_id
            migrated[kind] = KINDS[kind].model_validate(
                {**payload, "catalog_id": payload_digest(payload)}
            )
            provenance[kind] = {"before": catalog.catalog_id, "after": migrated[kind].catalog_id}
        before = DeterministicPipeline(profile=old, **options).run(data, logical_name=source.name)
        if hashlib.sha256(before.xml).hexdigest() != expected:
            raise ValueError("historical candidate mismatch")
        after = DeterministicPipeline(profile=new, **migrated).run(data, logical_name=source.name)
        changed = verify_country_only_delta(before.xml, after.xml)
        if changed != (3 if index == 0 else 0) or not after.validation.valid:
            raise ValueError("unexpected country correction or invalid offline XML")
        builder = PackageBuilder()
        files = builder.scielo_files(
            package_stem=new.package_stem(after.canonical.article_id),
            xml=after.xml,
            pdf=_single_artifact(corpus, manifest, "approved_pdf_reference").read_bytes(),
            assets=tuple(
                AssetPayload(source_name=p.name, data=p.read_bytes())
                for p in figure_paths(corpus, manifest)
            ),
        )
        kwargs = dict(
            article_id=after.canonical.article_id,
            profile_id=new.profile_id,
            source_idml_sha256=hashlib.sha256(data).hexdigest(),
            files=files,
            validator_versions={},
        )
        package = builder.build(**kwargs)
        if builder.build(**kwargs).archive != package.archive:
            raise ValueError("non-deterministic package")
        folder = output / case
        folder.mkdir(parents=True, exist_ok=True)
        for kind, catalog in migrated.items():
            (folder / f"{kind}.json").write_text(
                catalog.model_dump_json(indent=2), encoding="utf-8"
            )
        (folder / "candidate.xml").write_bytes(files[0].data)
        (folder / "candidate.zip").write_bytes(package.archive)
        rows.append(
            {
                "case": case,
                "country_attributes_added": changed,
                "xml_sha256": hashlib.sha256(files[0].data).hexdigest(),
                "package_sha256": package.package_sha256,
                "only_country_xml_delta": True,
                "catalog_migration": provenance,
                "offline_valid": True,
                "deterministic_package": True,
            }
        )
    report = {
        "version": "h1-country-codes-1.0",
        "profile_id": new.profile_id,
        "profile_sha256": hashlib.sha256(
            (ROOT / "profiles/esa-aop-1.1.json").read_bytes()
        ).hexdigest(),
        "cases": rows,
        "active_profile_changed": False,
        "gold_read": False,
        "catalog_values_changed": False,
        "ready_for_scielo": False,
    }
    (ROOT / "benchmarks/qualification/reports/h1-country-codes-v1.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report))


if __name__ == "__main__":
    main()
