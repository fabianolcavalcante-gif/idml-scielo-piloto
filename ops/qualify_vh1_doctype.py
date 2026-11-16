"""Prepare isolated exact-header comparisons; never migrate stored user versions."""

import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile

from lxml import etree

from idml_foundation.domain.canonical import CanonicalArticle
from idml_foundation.pipeline.jats_builder import JATS_PUBLIC_ID, JatsBuilder
from idml_foundation.pipeline.validation import OfflineJatsValidator
from idml_foundation.release.package_builder import (
    AssetPayload,
    ConversionManifest,
    PackageBuilder,
    PackageInput,
)
from ops.qualify_vh1_composed import BASE, write
from ops.qualify_vh1_xpm_linux import checked_members

OLD = b"-//NLM//DTD JATS (Z39.96) Journal Publishing DTD v1.3 20210610//EN"
ARTICLES = ("esa-e20240086", "esa-e20240135")
MODERN_MATRIX = [
    (ARTICLES[0], "corrected"),
    (ARTICLES[1], "corrected"),
    (ARTICLES[0], "invalid_fn"),
    (ARTICLES[0], "wrong_version"),
]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def tree(raw):
    parser = etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True)
    return etree.tostring(etree.fromstring(raw, parser), method="c14n")


def prepare(root, source):
    plan = json.loads((BASE / "plan.json").read_bytes())
    validator = OfflineJatsValidator(source / "vendor/jats/1.3")
    rows = []
    for article in ARTICLES:
        package = (BASE / article / "candidate.zip").read_bytes()
        assert sha(package) == plan["cases"][article]["package_sha256"]
        with ZipFile(BASE / article / "candidate.zip") as archive:
            members = checked_members(archive)
        name = next(n for n in members if n.endswith(".xml"))
        xml = members[name]
        assert xml.count(OLD) == 1
        corrected = xml.replace(OLD, JATS_PUBLIC_ID.encode(), 1)
        assert tree(corrected) == tree(xml)
        canonical = CanonicalArticle.model_validate_json(
            (BASE / article / "canonical.json").read_bytes()
        )
        built = JatsBuilder().build(canonical)
        old_root, new_root = [
            etree.fromstring(raw, etree.XMLParser(load_dtd=False, no_network=True))
            for raw in (xml, built)
        ]
        href = "{http://www.w3.org/1999/xlink}href"
        old_graphics, new_graphics = [
            r.xpath("//*[local-name()='graphic' or local-name()='inline-graphic']")
            for r in (old_root, new_root)
        ]
        assert len(old_graphics) == len(new_graphics)
        builder = PackageBuilder()
        files = builder.scielo_files(
            package_stem=name[:-4],
            xml=built,
            pdf=members[name[:-4] + ".pdf"],
            assets=tuple(
                AssetPayload(source_name=old.get(href), data=members[old.get(href)])
                for old in old_graphics
            ),
        )
        assert files[0].data.rstrip(b"\n") == corrected.rstrip(b"\n")
        old_manifest = ConversionManifest.model_validate_json(members["conversion-manifest.json"])
        assert all(sha(members[f.name]) == f.sha256 for f in old_manifest.files)
        variants = {"original": xml, "corrected": corrected}
        if article == ARTICLES[0]:
            assert b'fn-type="coi-statement"' in corrected
            variants["invalid_fn"] = corrected.replace(
                b'fn-type="coi-statement"', b'fn-type="invented"', 1
            )
            variants["wrong_version"] = corrected.replace(
                b'dtd-version="1.3"', b'dtd-version="1.1"', 1
            )
        for variant, raw in variants.items():
            folder = root / (article + "-" + variant)
            folder.mkdir(mode=0o700)
            (folder / "candidate.xml").write_bytes(raw)
            (folder / "candidate.xml").chmod(0o444)
            changed = builder.build(
                article_id=old_manifest.article_id,
                profile_id=old_manifest.profile_id,
                source_idml_sha256=old_manifest.source_idml_sha256,
                validator_versions=old_manifest.validator_versions,
                files=tuple(
                    PackageInput(
                        name=f.name,
                        role=f.role,
                        media_type=f.media_type,
                        data=raw if f.name == name else members[f.name],
                    )
                    for f in old_manifest.files
                ),
            )
            (folder / "candidate.zip").write_bytes(changed.archive)
            (folder / "candidate.zip").chmod(0o444)
            result = validator.validate(raw, asset_names=set(members))
            codes = sorted({i.code for i in result.issues})
            assert result.valid == (variant == "corrected")
            if variant == "original":
                assert codes == ["unexpected-doctype"]
            rows.append(
                dict(
                    case=folder.name,
                    source_package_sha256=sha(package),
                    xml_sha256=sha(raw),
                    package_sha256=changed.package_sha256,
                    canonical_tree_unchanged=tree(raw) == tree(xml),
                    rebuilt_with_current_builder=variant == "corrected",
                    conversion_manifest_updated=True,
                    assets_unchanged=True,
                    offline_valid=result.valid,
                    offline_issue_codes=codes,
                )
            )
    write(
        root / "plan.json",
        dict(version="vh1-doctype-comparison-1.0", cases=rows, publication_approved=False),
    )
    print(json.dumps(dict(prepared=len(rows), corrected_valid=2)))


def authorities(root):
    from ops.qualify_vh1_formula_revisions import refresh_authorities

    now = datetime.now(timezone.utc)  # noqa: UP017 - shared host-compatible convention
    cache = {}
    for article, variant in MODERN_MATRIX:
        folder = root / (article + "-" + variant)
        original = BASE / article
        xml = (folder / "candidate.xml").read_bytes()
        package = (folder / "candidate.zip").read_bytes()
        scope = json.loads((original / "scope.json").read_bytes())
        scope.update(xml_sha256=sha(xml), package_sha256=sha(package))
        write(folder / "scope.json", scope)
        incoming = folder / "incoming"
        incoming.mkdir(mode=0o700)
        refresh_authorities(original / "incoming", incoming, xml, package, cache)
        grant_id = str(uuid4())
        write(
            incoming / "manifest.json",
            dict(
                version="validation-authority-bundle-1.0",
                authorization_id=grant_id,
                scope=scope,
                files={p.name: sha(p.read_bytes()) for p in incoming.iterdir()},
            ),
        )
        grant = json.loads((original / "grant.json").read_bytes())
        grant.update(
            authorization_id=grant_id,
            scope=scope,
            bundle_sha256=sha((incoming / "manifest.json").read_bytes()),
            issued_at=now.isoformat(),
            expires_at=(now + timedelta(days=1)).isoformat(),
        )
        write(folder / "grant.json", grant)
        print(json.dumps(dict(authorities_prepared=folder.name)), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["prepare", "authorities"], default="prepare")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    if args.phase == "prepare":
        prepare(args.root, args.source)
    else:
        authorities(args.root)
