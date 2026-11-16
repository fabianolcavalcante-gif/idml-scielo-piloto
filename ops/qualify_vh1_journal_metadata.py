"""Rebuild the two authorized articles with only the reviewed registry-field changes."""

import copy
import json
import shutil
from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, uuid5

from lxml import etree

from idml_foundation.domain.corpus import load_manifest
from idml_foundation.pipeline.profile import load_profile
from idml_foundation.pipeline.service import DeterministicPipeline
from idml_foundation.release.journal_metadata import build_journal_metadata_catalog
from idml_foundation.release.package_builder import AssetPayload, PackageBuilder
from idml_foundation.services.enrichment import KINDS
from idml_foundation.services.validation_scope import scope_digest
from ops.build_h1_real_packages import figure_paths
from ops.qualify_vh1_final_validation import SOURCES as PREVIOUS_SOURCES
from ops.qualify_vh1_reference_types import (
    BASELINE as TYPE_BASELINE,
)
from ops.qualify_vh1_reference_types import (
    CASES,
    METADATA,
    ROOT,
    RUNNER,
    build,
    refresh_authorities,
    sha,
    verify_package,
    write,
)

BASELINE = ROOT / "benchmarks/private/output/vh1-final-validation-20261014T155218Z"
REGISTRY_RUN = ROOT / "benchmarks/private/output/vh1-xpm-online-20261016T102428Z"
FIELDS = (
    "front/journal-meta/journal-title-group/journal-title",
    "front/journal-meta/publisher/publisher-name",
)
SOURCES = (
    *PREVIOUS_SOURCES,
    "src/idml_foundation/release/journal_metadata.py",
    "src/idml_foundation/release/xpm_compatibility.py",
    "ops/qualify_vh1_journal_metadata.py",
    "ops/probe_xpm_doi_comparisons.py",
    "tests/test_journal_metadata.py",
    "tests/test_xpm_compatibility.py",
)


def verify_delta(before, after):
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
    old, new = [etree.fromstring(data, parser) for data in (before, after)]
    changes = []
    for path in FIELDS:
        a, b = old.findall(path), new.findall(path)
        if len(a) != 1 or len(b) != 1 or len(a[0]) or len(b[0]):
            raise ValueError("journal_field_not_unique_or_plain")
        if a[0].text != b[0].text:
            changes.append(
                {
                    "field": path,
                    "before_sha256": sha(a[0].text.encode()),
                    "after_sha256": sha(b[0].text.encode()),
                }
            )
        b[0].text = a[0].text
    if etree.tostring(old, method="c14n") != etree.tostring(new, method="c14n"):
        raise ValueError("non_journal_metadata_change")
    return {"fields": changes, "all_other_xml_unchanged": True}


def main():
    now = datetime.now(UTC)
    output = (
        ROOT / "benchmarks/private/output" / now.strftime("vh1-journal-metadata-%Y%m%dT%H%M%SZ")
    )
    output.mkdir(exist_ok=False)
    registry = (REGISTRY_RUN / "proxy/catalogue.csv").read_bytes()
    events = [
        json.loads(line) for line in (REGISTRY_RUN / "proxy/events.jsonl").read_text().splitlines()
    ]
    collected = datetime.fromtimestamp(
        max(e["at"] for e in events if e["event"] == "catalogue_https_response"), UTC
    )
    previous = json.loads((BASELINE / "plan.json").read_bytes())
    plan = {
        "version": "vh1-journal-metadata-local-1.0",
        "created_at": now.isoformat(),
        "source_sha256": {p: sha((ROOT / p).read_bytes()) for p in SOURCES if (ROOT / p).exists()},
        "before_source_sha256": previous["source_sha256"],
        "code_sha256": {n: sha((ROOT / p).read_bytes()) for n, p in RUNNER.items()},
        "registry_sha256": sha((BASELINE / "registry.json").read_bytes()),
        "gold_read": False,
        "formal_xml_approved": False,
        "active_application_changed": False,
        "human_review_required": True,
        "autonomous_application": False,
        "remaining_ambiguous_glyphs": 1,
        "cases": {},
    }
    for name, path in RUNNER.items():
        shutil.copyfile(ROOT / path, output / name)
    shutil.copyfile(BASELINE / "registry.json", output / "registry.json")
    cache = {}
    for case, name in CASES.items():
        path = ROOT / name
        source, pdf, original, old_xml, old_zip, reference_catalog = build(case, path)
        baseline = BASELINE / case
        if (
            old_xml != (baseline / "candidate.xml").read_bytes()
            or old_zip != (baseline / "candidate.zip").read_bytes()
        ):
            raise ValueError("baseline_not_reproduced")
        catalog = build_journal_metadata_catalog(
            original.canonical,
            source_idml_sha256=sha(source),
            registry=registry,
            collected_at=collected,
            corpus_id=case,
        )
        catalogs = {}
        for base in (
            ROOT / "benchmarks/private/output/h1-country-codes-v1" / case,
            METADATA / case,
            TYPE_BASELINE / case,
        ):
            for kind, contract in KINDS.items():
                item = base / (kind + ".json")
                if item.exists():
                    catalogs[kind] = contract.model_validate_json(item.read_bytes())
        catalogs.update(reference_type_catalog=reference_catalog, journal_metadata_catalog=catalog)
        profile = load_profile(ROOT / "profiles/esa-aop-1.1.json")
        pipeline = DeterministicPipeline(profile=profile, **catalogs)
        result, repeat = [pipeline.run(source, logical_name=path.name) for _ in range(2)]
        if result.xml != repeat.xml or not result.validation.valid:
            raise ValueError("pipeline_not_deterministic_or_invalid")
        manifest = load_manifest(ROOT / f"corpus/manifests/{case}.json")
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
        xml = files[0].data
        delta = verify_delta(old_xml, xml)
        if len(delta["fields"]) != (2 if case == "esa-e20240086" else 1):
            raise ValueError("unexpected_journal_delta")
        assets = verify_package(old_zip, package)
        folder = output / case
        # Work on a new derivative only; retain every original and its proof.
        shutil.copytree(
            baseline,
            folder,
            ignore=shutil.ignore_patterns(
                "candidate.xml",
                "candidate.zip",
                "canonical.json",
                "scope.json",
                "grant.json",
                "incoming",
            ),
        )
        (folder / "candidate.xml").write_bytes(xml)
        (folder / "candidate.zip").write_bytes(package)
        write(folder / "canonical.json", result.canonical.model_dump(mode="json"))
        write(folder / "journal_metadata_catalog.json", catalog.model_dump(mode="json"))
        scope = json.loads((baseline / "scope.json").read_bytes())
        scope.update(xml_sha256=sha(xml), package_sha256=sha(package))
        # Refresh into a separate fresh directory; do not reuse prior approvals for new hashes.
        incoming = folder / "incoming"
        incoming.mkdir()
        authorities = refresh_authorities(baseline / "incoming", incoming, xml, package, cache)
        grant_id = str(
            uuid5(NAMESPACE_URL, "idml:vh1:journal-registry:LAB_ONLY:" + output.name + case)
        )
        write(
            folder / "incoming/manifest.json",
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
            bundle_sha256=sha((folder / "incoming/manifest.json").read_bytes()),
            issued_at=now.isoformat(),
            expires_at=(now + timedelta(days=1)).isoformat(),
        )
        write(folder / "grant.json", grant)
        write(folder / "scope.json", scope)
        details = copy.deepcopy(previous["cases"][case])
        details.update(
            before_xml_sha256=sha(old_xml),
            before_package_sha256=sha(old_zip),
            xml_sha256=sha(xml),
            package_sha256=sha(package),
            scope_sha256=scope_digest(scope),
            delta=delta,
            unchanged_assets=assets,
            fresh_authorities=authorities,
            journal_catalog_sha256=sha((folder / "journal_metadata_catalog.json").read_bytes()),
            deterministic=True,
            offline_valid=True,
        )
        details["files"] = {
            p.relative_to(folder).as_posix(): sha(p.read_bytes())
            for p in folder.rglob("*")
            if p.is_file()
        }
        plan["cases"][case] = details
        print(json.dumps({"case": case, "changed_fields": len(delta["fields"])}), flush=True)
    write(output / "plan.json", plan)
    print(
        json.dumps(
            {"directory": str(output), "plan_sha256": sha((output / "plan.json").read_bytes())}
        )
    )


if __name__ == "__main__":
    main()
