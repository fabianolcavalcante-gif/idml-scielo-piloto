"""Rebuild authorized inputs; permit only reviewed bibliographic field changes."""

import argparse
import copy
import json
import shutil
from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, uuid5

from lxml import etree

from idml_foundation.domain.corpus import load_manifest
from idml_foundation.pipeline.profile import load_profile
from idml_foundation.pipeline.service import DeterministicPipeline
from idml_foundation.release.package_builder import AssetPayload, PackageBuilder
from idml_foundation.release.reference_types import RULES, build_reference_type_catalog
from idml_foundation.services.enrichment import KINDS
from idml_foundation.services.validation_scope import scope_digest
from ops.build_h1_real_packages import figure_paths
from ops.gate_phase7_7c06 import _single_artifact
from ops.gate_vh1_reference_metadata import FINAL as BEFORE
from ops.qualify_vh1_glyphs import (
    CASES,
    METADATA,
    ROOT,
    RUNNER,
    refresh_authorities,
    sha,
    verify_package,
    write,
)
from ops.qualify_vh1_reference_metadata import SOURCES as PREVIOUS_SOURCES

BASELINE = ROOT / "benchmarks/private/output/vh1-reference-metadata-20261009T195009Z"
CONTRACT = "benchmarks/qualification/contracts/vh1-reference-types-delta-v1.json"
SOURCES = (
    *PREVIOUS_SOURCES,
    "src/idml_foundation/release/reference_types.py",
    "src/idml_foundation/services/source_authorization.py",
    "ops/collect_vh1_reference_sources.py",
    "src/idml_foundation/domain/canonical.py",
    "src/idml_foundation/domain/schema_migrations.py",
    "schemas/canonical-article-1.6.0.schema.json",
    "ops/qualify_vh1_reference_types.py",
    CONTRACT,
)


def trees(before, after):
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
    return [etree.fromstring(x, parser) for x in (before, after)]


def digest(node):
    return sha(etree.tostring(node, method="c14n"))


def inspect_delta(before, after):
    """Inventory entire structured citations; every resulting text must be literal."""
    old, new = trees(before, after)
    rows = []
    refs = [r.findall("back/ref-list/ref") for r in (old, new)]
    for index, (a, b) in enumerate(zip(*refs, strict=True), 1):
        left, right = [r.find("element-citation") for r in (a, b)]
        if left is None or right is None or a.get("id") != b.get("id"):
            raise ValueError("reference_identity_mismatch")
        if digest(left) == digest(right):
            continue
        text = "".join(b.find("mixed-citation").itertext())
        spans = []
        for node in right.iter():
            if node.text and node.text.strip():
                literal = node.text
                start = text.find(literal)
                if start < 0:
                    raise ValueError("field_not_literal_source:" + node.tag)
                spans.append(
                    {
                        "tag": node.tag,
                        "start": start,
                        "end": start + len(literal),
                        "sha256": sha(literal.encode()),
                    }
                )
        rows.append(
            {
                "position": index,
                "id": a.get("id"),
                "field": "element-citation",
                "before_sha256": digest(left),
                "after_sha256": digest(right),
                "mixed_citation_sha256": sha(text.encode()),
                "source_spans": spans,
                "publication_type": right.get("publication-type"),
                "access_dates": len(right.findall("date-in-citation")),
            }
        )
    return rows


def verify_delta(before, after, expected):
    observed = inspect_delta(before, after)
    if observed != expected:
        raise ValueError("unreviewed_reference_metadata")
    old, new = trees(before, after)
    for row in expected:
        path = "back/ref-list/ref[@id=$id]/element-citation"
        a, b = [r.xpath(path, id=row["id"]) for r in (old, new)]
        if len(a) != 1 or len(b) != 1:
            raise ValueError("reference_identity_not_unique")
        replacement = copy.deepcopy(a[0])
        replacement.tail = b[0].tail
        b[0].getparent().replace(b[0], replacement)
    if etree.tostring(old, method="c14n") != etree.tostring(new, method="c14n"):
        raise ValueError("non_reference_metadata_change")
    return {
        "fields": observed,
        "reference_count": len(old.findall("back/ref-list/ref")),
        "changed_references": len(observed),
        "all_other_xml_unchanged": True,
        "mixed_citations_unchanged": True,
    }


SNAPSHOTS = ROOT / "benchmarks/private/output/vh1-reference-sources-20261013T183201Z"
SELECTIONS = {
    "esa-e20240086": {
        "reference-a3f6a367-c1f9-5543-9306-a2e7615fc0d1": "saae-mananciais",
        "reference-d1f110b2-25dc-5f3f-8d0b-dfbbaf5e3ba7": "srac-3700",
    },
    "esa-e20240135": {
        "reference-ff139fbc-b398-59da-9326-587309014e6a": "who-situation-106",
    },
}
SNAPSHOT_FILES = {
    "saae-mananciais": "saae.html",
    "srac-3700": "srac.pdf",
    "who-situation-106": "who.html",
}


def build(case, path):
    source = path.read_bytes()
    manifest = load_manifest(ROOT / f"corpus/manifests/{case}.json")
    if _single_artifact(path.parent, manifest, "source_idml").read_bytes() != source:
        raise ValueError("source_idml_mismatch")
    pdf = _single_artifact(path.parent, manifest, "approved_pdf_reference").read_bytes()
    catalogs = {}
    for base in (
        ROOT / "benchmarks/private/output/h1-country-codes-v1" / case,
        METADATA / case,
        BASELINE / case,
    ):
        for kind, contract in KINDS.items():
            item = base / (kind + ".json")
            if item.exists():
                catalogs[kind] = contract.model_validate_json(item.read_bytes())
    profile = load_profile(ROOT / "profiles/esa-aop-1.1.json")
    original = DeterministicPipeline(profile=profile, **catalogs).run(
        source, logical_name=path.name
    )
    snapshots = json.loads((SNAPSHOTS / "manifest.json").read_bytes())
    selected = SELECTIONS[case]
    for rule_id in selected.values():
        row = snapshots[SNAPSHOT_FILES[rule_id]]
        if row["url"] != RULES[rule_id].source_url or row["sha256"] != RULES[rule_id].source_sha256:
            raise ValueError("reference_source_manifest_mismatch")
    catalog = build_reference_type_catalog(
        article=original.canonical,
        source_idml_sha256=sha(source),
        corpus_id=case,
        selections=selected,
        responses={
            rule: (SNAPSHOTS / SNAPSHOT_FILES[rule]).read_bytes() for rule in selected.values()
        },
        collected_at=max(
            snapshots[SNAPSHOT_FILES[rule]]["retrieved_at"] for rule in selected.values()
        ),
    )
    pipeline = DeterministicPipeline(profile=profile, **catalogs, reference_type_catalog=catalog)
    result, repeat = [pipeline.run(source, logical_name=path.name) for _ in range(2)]
    if result.xml != repeat.xml or not result.validation.valid:
        raise ValueError("pipeline_invalid")
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
    kwargs = dict(
        article_id=result.canonical.article_id,
        profile_id=profile.profile_id,
        source_idml_sha256=sha(source),
        files=files,
        validator_versions={},
    )
    package = builder.build(**kwargs).archive
    if package != builder.build(**kwargs).archive:
        raise ValueError("package_not_deterministic")
    return source, pdf, result, files[0].data, package, catalog


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inspect", action="store_true")
    args = parser.parse_args()
    now = datetime.now(UTC)
    output = ROOT / "benchmarks/private/output" / now.strftime("vh1-reference-types-%Y%m%dT%H%M%SZ")
    output.mkdir(exist_ok=False)
    previous = json.loads((BASELINE / "plan.json").read_bytes())
    plan = {
        "version": "vh1-reference-types-local-1.0",
        "created_at": now.isoformat(),
        "source_sha256": {p: sha((ROOT / p).read_bytes()) for p in SOURCES if (ROOT / p).exists()},
        "before_source_sha256": previous["source_sha256"],
        "code_sha256": {n: sha((ROOT / p).read_bytes()) for n, p in RUNNER.items()},
        "gold_read": False,
        "formal_xml_approved": False,
        "active_application_changed": False,
        "human_review_required": True,
        "autonomous_application": False,
        "remaining_ambiguous_glyphs": 1,
        "inspection_only": args.inspect,
        "cases": {},
    }
    for name, path in RUNNER.items():
        shutil.copyfile(ROOT / path, output / name)
    registry = ROOT / "config/validator-registry-vh1-history.json"
    shutil.copyfile(registry, output / "registry.json")
    plan["registry_sha256"] = sha(registry.read_bytes())
    expected = {} if args.inspect else json.loads((ROOT / CONTRACT).read_bytes())["cases"]
    cache = {}
    for case, name in CASES.items():
        folder = output / case
        folder.mkdir()
        source, pdf, result, xml, package, catalog = build(case, ROOT / name)
        baseline = BASELINE / case
        old_xml, old_zip = [
            (baseline / ("candidate." + ext)).read_bytes() for ext in ("xml", "zip")
        ]
        if (sha(old_xml), sha(old_zip)) != BEFORE[case]:
            raise ValueError("baseline_changed")
        delta = (
            {"fields": inspect_delta(old_xml, xml), "inspection_only": True}
            if args.inspect
            else verify_delta(old_xml, xml, expected[case])
        )
        assets = verify_package(old_zip, package)
        (folder / "candidate.xml").write_bytes(xml)
        (folder / "candidate.zip").write_bytes(package)
        write(folder / "canonical.json", result.canonical.model_dump(mode="json"))
        shutil.copyfile(baseline / "formula_catalog.json", folder / "formula_catalog.json")
        write(folder / "reference_type_catalog.json", catalog.model_dump(mode="json"))
        source_folder = folder / "sources"
        source_folder.mkdir()
        shutil.copyfile(SNAPSHOTS / "manifest.json", source_folder / "manifest.json")
        for rule_id in SELECTIONS[case].values():
            filename = SNAPSHOT_FILES[rule_id]
            shutil.copyfile(SNAPSHOTS / filename, source_folder / filename)
        scope = json.loads((baseline / "scope.json").read_bytes())
        scope.update(xml_sha256=sha(xml), package_sha256=sha(package))
        authorities = None
        if not args.inspect:
            incoming = folder / "incoming"
            incoming.mkdir()
            authorities = refresh_authorities(baseline / "incoming", incoming, xml, package, cache)
            grant_id = str(
                uuid5(NAMESPACE_URL, "idml:vh1:reference-types:LAB_ONLY:" + output.name + case)
            )
            write(
                incoming / "manifest.json",
                {
                    "version": "validation-authority-bundle-1.0",
                    "authorization_id": grant_id,
                    "scope": scope,
                    "files": {p.name: sha(p.read_bytes()) for p in incoming.iterdir()},
                },
            )
            grant = json.loads((baseline / "grant.json").read_bytes())
            grant.update(
                authorization_id=grant_id,
                scope=scope,
                bundle_sha256=sha((incoming / "manifest.json").read_bytes()),
                issued_at=now.isoformat(),
                expires_at=(now + timedelta(days=1)).isoformat(),
            )
            write(folder / "grant.json", grant)
            write(folder / "scope.json", scope)
        plan["cases"][case] = {
            "source_idml_sha256": sha(source),
            "source_pdf_sha256": sha(pdf),
            "before_xml_sha256": sha(old_xml),
            "before_package_sha256": sha(old_zip),
            "xml_sha256": sha(xml),
            "package_sha256": sha(package),
            "catalog_sha256": sha((folder / "formula_catalog.json").read_bytes()),
            "scope_sha256": scope_digest(scope),
            "offline_valid": True,
            "deterministic": True,
            "delta": delta,
            "unchanged_assets": assets,
            "fresh_authorities": authorities,
            "files": {
                p.relative_to(folder).as_posix(): sha(p.read_bytes())
                for p in folder.rglob("*")
                if p.is_file()
            },
        }
        print(json.dumps({"case": case, "changed_fields": len(delta["fields"])}), flush=True)
    write(output / "plan.json", plan)
    print(
        json.dumps(
            {"directory": str(output), "plan_sha256": sha((output / "plan.json").read_bytes())}
        )
    )


if __name__ == "__main__":
    main()
