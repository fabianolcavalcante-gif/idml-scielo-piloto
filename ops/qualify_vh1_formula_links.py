"""Rebuild both authorized IDMLs; allow five verified literal links, no other XML edits."""

import hashlib
import json
import shutil
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5
from zipfile import ZipFile

from lxml import etree

from idml_foundation.domain.corpus import load_manifest
from idml_foundation.pipeline.profile import load_profile
from idml_foundation.pipeline.service import DeterministicPipeline
from idml_foundation.release.package_builder import AssetPayload, PackageBuilder
from idml_foundation.services.enrichment import KINDS
from idml_foundation.services.validation_scope import scope_digest
from ops.build_h1_real_packages import figure_paths
from ops.gate_phase7_7c06 import _single_artifact
from ops.gate_vh1_metadata import FINAL
from ops.qualify_vh1_metadata import CHANGED, CODE

ROOT = Path(__file__).resolve().parents[1]
PREVIOUS = ROOT / "benchmarks/private/output/vh1-metadata-20261006T223858Z"
EXPECTED = (
    (
        "paragraph-4a114303-b1e1-5337-b3da-76e75502eda7",
        "e-formula-a0b70f7d-e29e-564b-b0e4-0dc404ed6767",
        "8",
    ),
    (
        "paragraph-1c1c74a8-63e4-56da-ade9-82fa1d5dc0c1",
        "e-formula-99b0b7d3-3648-5221-867c-824e3a10e170",
        "4",
    ),
    (
        "paragraph-21051275-2f2b-5734-8ebe-5f3186ddff9b",
        "e-formula-500818b8-d682-5149-893e-c989336435b0",
        "12",
    ),
    (
        "paragraph-0117c9cd-6d96-50fe-9745-34234489dccb",
        "e-formula-44665dfc-6476-50ef-a786-f9a5fe6a51f7",
        "14",
    ),
    (
        "paragraph-74569f2a-2fa8-5fbd-bcec-e7d7f5c8e02f",
        "e-formula-0e118109-65d4-56f5-8082-3ea1436f0d10",
        "we have",
    ),
)
SOURCES = (
    *CHANGED,
    "src/idml_foundation/pipeline/object_reference_resolver.py",
    "ops/qualify_vh1_formula_links.py",
)
RUNNER = {**CODE, "run_vh1_history_linux.py": "ops/run_vh1_history_linux.py"}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)


def verify_delta(before, after, *, first):
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
    old, new = (etree.fromstring(xml, parser) for xml in (before, after))
    rows = []
    for paragraph, target, text in EXPECTED if first else ():
        xpath = ".//p[@id=$p]/xref[@rid=$rid]"
        candidates = new.xpath(xpath, p=paragraph, rid=target)
        if old.xpath(xpath, p=paragraph, rid=target) or len(candidates) != 1:
            raise ValueError("formula_link_missing_or_duplicate")
        node = candidates[0]
        if (
            node.attrib != {"rid": target, "ref-type": "disp-formula"}
            or len(node)
            or node.text != text
        ):
            raise ValueError("formula_link_unexpected_anchor")
        destinations = new.xpath(".//disp-formula[@id=$rid]", rid=target)
        if len(destinations) != 1:
            raise ValueError("formula_link_destination_not_unique")
        rows.append(
            {"paragraph_id": paragraph, "target_id": target, "anchor_sha256": sha(text.encode())}
        )
        parent = node.getparent()
        previous = node.getprevious()
        retained = (node.text or "") + (node.tail or "")
        if previous is None:
            parent.text = (parent.text or "") + retained
        else:
            previous.tail = (previous.tail or "") + retained
        parent.remove(node)
    if etree.tostring(old, method="c14n") != etree.tostring(new, method="c14n"):
        raise ValueError("non_link_xml_change")
    return {"added_links": rows, "all_other_xml_unchanged": True, "mathml_unchanged": True}


def verify_package(before, after):
    with ZipFile(BytesIO(before)) as old, ZipFile(BytesIO(after)) as new:
        if old.namelist() != new.namelist():
            raise ValueError("formula_package_members_changed")
        retained = {}
        for name in old.namelist():
            if name.endswith(".xml") or name == "conversion-manifest.json":
                continue
            if old.read(name) != new.read(name):
                raise ValueError("formula_package_asset_changed")
            retained[name] = sha(new.read(name))
    return retained


def main():
    now = datetime.now(UTC)
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    output = ROOT / "benchmarks/private/output" / ("vh1-formula-links-" + run_id)
    output.mkdir(exist_ok=False)
    profile = load_profile(ROOT / "profiles/esa-aop-1.1.json")
    plan = {
        "version": "vh1-formula-links-local-1.0",
        "created_at": now.isoformat(),
        "source_sha256": {p: sha((ROOT / p).read_bytes()) for p in SOURCES},
        "code_sha256": {n: sha((ROOT / p).read_bytes()) for n, p in RUNNER.items()},
        "gold_read": False,
        "catalog_values_changed": False,
        "active_application_changed": False,
        "formal_xml_approved": False,
        "cases": {},
    }
    for name, source in RUNNER.items():
        shutil.copyfile(ROOT / source, output / name)
    registry = ROOT / "config/validator-registry-vh1-history.json"
    shutil.copyfile(registry, output / "registry.json")
    plan["registry_sha256"] = sha(registry.read_bytes())
    for case, source_name in (
        ("esa-e20240086", "tmp/sample/ESA_2024086_AOP.idml"),
        ("esa-e20240135", "tmp/ARQUIVOS TESTE/ESA_2024135_AOP.idml"),
    ):
        source = ROOT / source_name
        data = source.read_bytes()
        manifest = load_manifest(ROOT / f"corpus/manifests/{case}.json")
        _single_artifact(source.parent, manifest, "source_idml")
        baseline = PREVIOUS / case
        if (
            tuple(sha((baseline / f"candidate.{ext}").read_bytes()) for ext in ("xml", "zip"))
            != FINAL[case]
        ):
            raise ValueError("formula_baseline_mismatch")
        catalogs, catalog_hashes = {}, {}
        for folder in (ROOT / "benchmarks/private/output/h1-country-codes-v1" / case, baseline):
            for kind, contract in KINDS.items():
                path = folder / (kind + ".json")
                if path.exists():
                    catalogs[kind] = contract.model_validate_json(path.read_bytes())
                    catalog_hashes[kind] = sha(path.read_bytes())
        pipeline = DeterministicPipeline(profile=profile, **catalogs)
        result, repeated = [pipeline.run(data, logical_name=source.name) for _ in range(2)]
        if result.xml != repeated.xml or not result.validation.valid:
            raise ValueError("formula_conversion_invalid_or_unstable")
        package_builder = PackageBuilder()
        files = package_builder.scielo_files(
            package_stem=profile.package_stem(result.canonical.article_id),
            xml=result.xml,
            pdf=_single_artifact(source.parent, manifest, "approved_pdf_reference").read_bytes(),
            assets=tuple(
                AssetPayload(source_name=p.name, data=p.read_bytes())
                for p in figure_paths(source.parent, manifest)
            ),
        )
        args = dict(
            article_id=result.canonical.article_id,
            profile_id=profile.profile_id,
            source_idml_sha256=sha(data),
            files=files,
            validator_versions={},
        )
        package = package_builder.build(**args)
        if package.archive != package_builder.build(**args).archive:
            raise ValueError("formula_package_not_deterministic")
        xml = files[0].data
        delta = verify_delta(
            (baseline / "candidate.xml").read_bytes(), xml, first=case == "esa-e20240086"
        )
        assets = verify_package((baseline / "candidate.zip").read_bytes(), package.archive)
        folder = output / case
        folder.mkdir()
        (folder / "candidate.xml").write_bytes(xml)
        (folder / "candidate.zip").write_bytes(package.archive)
        (folder / "canonical.json").write_text(
            result.canonical.model_dump_json(indent=2), encoding="utf-8"
        )
        scope = json.loads((baseline / "scope.json").read_bytes())
        scope.update(xml_sha256=sha(xml), package_sha256=sha(package.archive))
        incoming = folder / "incoming"
        incoming.mkdir()
        for path in (baseline / "incoming").glob("*.json"):
            if path.name == "manifest.json":
                continue
            raw = path.read_bytes()
            if path.name in {"doi-manifest.json", "editorial-manifest.json"}:
                item = json.loads(raw)
                item["candidate_sha256"] = scope["xml_sha256"]
                if path.name == "doi-manifest.json":
                    item["package_sha256"] = scope["package_sha256"]
                write(incoming / path.name, item)
            else:
                (incoming / path.name).write_bytes(raw)
        grant_id = str(uuid5(NAMESPACE_URL, "idml:vh1:formula-links:LAB_ONLY:" + run_id + case))
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
            "source_idml_sha256": sha(data),
            "before_xml_sha256": FINAL[case][0],
            "xml_sha256": scope["xml_sha256"],
            "package_sha256": scope["package_sha256"],
            "scope_sha256": scope_digest(scope),
            "catalog_sha256": catalog_hashes,
            "offline_valid": True,
            "deterministic": True,
            "delta": delta,
            "unchanged_assets": assets,
            "files": {
                p.relative_to(folder).as_posix(): sha(p.read_bytes())
                for p in folder.rglob("*")
                if p.is_file()
            },
        }
    write(output / "plan.json", plan)
    print(
        json.dumps(
            {
                "directory": str(output),
                "plan_sha256": sha((output / "plan.json").read_bytes()),
                "cases": {k: v["delta"] for k, v in plan["cases"].items()},
            }
        )
    )


if __name__ == "__main__":
    main()
