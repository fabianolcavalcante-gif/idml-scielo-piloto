"""Qualify the final XML delta and consolidate the original native warning evidence."""

import argparse
import copy
import json
import shutil
from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, uuid5

from lxml import etree

from idml_foundation.services.validation_scope import scope_digest
from ops.gate_vh1_reference_types import FINAL as BEFORE
from ops.qualify_vh1_reference_types import (
    CASES,
    ROOT,
    RUNNER,
    SELECTIONS,
    SNAPSHOT_FILES,
    SNAPSHOTS,
    build,
    refresh_authorities,
    sha,
    verify_package,
    write,
)
from ops.qualify_vh1_reference_types import SOURCES as PREVIOUS_SOURCES

BASELINE = ROOT / "benchmarks/private/output/vh1-reference-types-20261014T104156Z"
CONTRACT = "benchmarks/qualification/contracts/vh1-final-validation-delta-v1.json"
SOURCES = (
    *PREVIOUS_SOURCES,
    "src/idml_foundation/pipeline/affiliation_hierarchy.py",
    "ops/qualify_vh1_final_validation.py",
    CONTRACT,
)


def trees(before, after):
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
    return [etree.fromstring(x, parser) for x in (before, after)]


def digest(node):
    return sha(etree.tostring(node, method="c14n"))


def inspect_delta(before, after):
    old, new = trees(before, after)
    rows = []
    for a, b in zip(
        old.findall("front/article-meta/aff"), new.findall("front/article-meta/aff"), strict=True
    ):
        if a.get("id") != b.get("id"):
            raise ValueError("affiliation_identity_changed")
        if digest(a) == digest(b):
            continue
        first = a.find("institution[@content-type='orgdiv1']")
        parts = [
            b.find("institution[@content-type='" + key + "']") for key in ("orgdiv1", "orgdiv2")
        ]
        if first is None or any(n is None or not n.text or len(n) for n in parts):
            raise ValueError("division_missing")
        if ", ".join(n.text for n in parts) != first.text:
            raise ValueError("division_not_literal")
        if first.text not in a.findtext("institution[@content-type='original']", ""):
            raise ValueError("original_mismatch")
        rows.append(
            {
                "id": a.get("id"),
                "before_sha256": digest(a),
                "after_sha256": digest(b),
                "original_sha256": sha(
                    a.findtext("institution[@content-type='original']").encode()
                ),
                "combined_divisions_sha256": sha(first.text.encode()),
                "divisions_sha256": [sha(n.text.encode()) for n in parts],
            }
        )
    return rows


def verify_delta(before, after, expected):
    observed = inspect_delta(before, after)
    if observed != expected:
        raise ValueError("unreviewed_affiliation_change")
    old, new = trees(before, after)
    for row in expected:
        path = "front/article-meta/aff[@id=$id]"
        a, b = [r.xpath(path, id=row["id"]) for r in (old, new)]
        if len(a) != 1 or len(b) != 1:
            raise ValueError("affiliation_not_unique")
        # Only the institutional subdivision may differ, including its attributes.
        first = a[0].find("institution[@content-type='orgdiv1']")
        a_parts = b[0].findall("institution[@content-type='orgdiv1']")
        b_parts = b[0].findall("institution[@content-type='orgdiv2']")
        if len(a_parts) != 1 or len(b_parts) != 1:
            raise ValueError("division_not_unique")
        if any(
            dict(n.attrib) != {"content-type": key}
            for n, key in zip((a_parts[0], b_parts[0]), ("orgdiv1", "orgdiv2"), strict=True)
        ):
            raise ValueError("division_attributes_changed")
        replacement = copy.deepcopy(first)
        b[0].replace(a_parts[0], replacement)
        b[0].remove(b_parts[0])
    if digest(old) != digest(new):
        raise ValueError("non_hierarchy_change")
    return {
        "fields": observed,
        "changed_affiliations": len(observed),
        "all_other_xml_unchanged": True,
        "source_text_preserved": True,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inspect", action="store_true")
    args = parser.parse_args()
    now = datetime.now(UTC)
    output = (
        ROOT / "benchmarks/private/output" / now.strftime("vh1-final-validation-%Y%m%dT%H%M%SZ")
    )
    output.mkdir(exist_ok=False)
    previous = json.loads((BASELINE / "plan.json").read_bytes())
    plan = {
        "version": "vh1-final-validation-local-1.0",
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
                uuid5(NAMESPACE_URL, "idml:vh1:final-validation:LAB_ONLY:" + output.name + case)
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
