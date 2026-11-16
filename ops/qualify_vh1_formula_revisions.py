"""Source-bound formula revisions, exact XML whitelist and isolated native staging."""

import argparse
import copy
import json
import shutil
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, build_opener
from uuid import NAMESPACE_URL, uuid5

from lxml import etree

from idml_foundation.ai.formula_catalog import FormulaTranscriptionEntry, revise_formula_catalog
from idml_foundation.ai.visual_formula_corpus import PdfFormulaCrop, render_formula_crop
from idml_foundation.domain.corpus import load_manifest
from idml_foundation.mathml import canonical_mathml
from idml_foundation.pipeline.profile import load_profile
from idml_foundation.pipeline.service import DeterministicPipeline
from idml_foundation.release.package_builder import AssetPayload, PackageBuilder
from idml_foundation.services.enrichment import KINDS
from idml_foundation.services.validation_scope import scope_digest
from ops.build_h1_real_packages import figure_paths
from ops.collect_vh1_editorial_sources import NoRedirect, fetch
from ops.gate_phase7_7c06 import _single_artifact
from ops.gate_vh1_formula_links import FINAL as BEFORE
from ops.qualify_vh1_formula_links import (
    RUNNER,
    sha,
    verify_package,
    write,
)
from ops.qualify_vh1_formula_links import (
    SOURCES as LINK_SOURCES,
)

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "benchmarks/private/output/vh1-formula-links-20261007T202358Z"
METADATA = ROOT / "benchmarks/private/output/vh1-metadata-20261006T223858Z"
SOURCES = (
    *LINK_SOURCES,
    "src/idml_foundation/ai/formula_catalog.py",
    "ops/qualify_vh1_formula_revisions.py",
    "ops/collect_vh1_editorial_sources.py",
)
CASES = {
    "esa-e20240086": "tmp/sample/ESA_2024086_AOP.idml",
    "esa-e20240135": "tmp/ARQUIVOS TESTE/ESA_2024135_AOP.idml",
}
NS = {"m": "http://www.w3.org/1998/Math/MathML"}


def math_bytes(node):
    fragment = copy.deepcopy(node)
    fragment.attrib.pop("id", None)
    return canonical_mathml(
        etree.tostring(fragment, encoding="unicode", with_tail=False),
        display=fragment.get("display") == "block",
    ).encode()


def verify_delta(before, after, changes):
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
    old, new = (etree.fromstring(x, parser) for x in (before, after))
    a, b = (r.xpath(".//m:math", namespaces=NS) for r in (old, new))
    if len(a) != len(b):
        raise ValueError("formula_set_changed")
    observed, expected, changed = Counter(), Counter(), []
    for row in changes:
        expected[(row["before_sha256"], row["after_sha256"])] += 1
    for x, y in zip(a, b, strict=True):
        if x.get("id") != y.get("id") or x.getparent().get("id") != y.getparent().get("id"):
            raise ValueError("formula_identity_changed")
        left, right = sha(math_bytes(x)), sha(math_bytes(y))
        if left != right:
            observed[(left, right)] += 1
            changed.append(
                {"id": x.getparent().get("id"), "before_sha256": left, "after_sha256": right}
            )
            replacement = copy.deepcopy(x)
            replacement.tail = y.tail
            y.getparent().replace(y, replacement)
    if observed != expected:
        raise ValueError("formula_delta_outside_review")
    if etree.tostring(old, method="c14n") != etree.tostring(new, method="c14n"):
        raise ValueError("non_formula_xml_change")
    return {"changes": changed, "all_other_xml_unchanged": True, "formula_count": len(a)}


def refresh_authorities(baseline, incoming, xml, package, cache):
    """Perform real fresh retrievals; never renew an old snapshot's timestamp."""
    tree = etree.fromstring(xml, etree.XMLParser(resolve_entities=False, no_network=True))
    doi = tree.xpath("string(front/article-meta/article-id[@pub-id-type='doi'])")
    url = "https://api.crossref.org/works/" + quote(doi, safe="")
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "IDML-VH1/1.0"})
    with build_opener(NoRedirect()).open(request, timeout=30) as response:
        if response.status != 200 or response.headers.get_content_type() != "application/json":
            raise ValueError("doi_refresh_invalid")
        raw = response.read(10 * 1024**2 + 1)
        if len(raw) > 10 * 1024**2:
            raise ValueError("doi_refresh_budget")
        json.loads(raw)
    doi_manifest = json.loads((baseline / "doi-manifest.json").read_bytes())
    doi_manifest.update(
        candidate_sha256=sha(xml),
        package_sha256=sha(package),
        snapshot_sha256=sha(raw),
        retrieved_at=datetime.now(UTC).isoformat(),
    )
    # Preserve the file names expected by the qualified broker bundle.
    (incoming / "crossref.json").write_bytes(raw)
    write(incoming / "doi-manifest.json", doi_manifest)
    editorial = json.loads((baseline / "editorial-manifest.json").read_bytes())
    editorial["candidate_sha256"] = sha(xml)
    for key, record in editorial["sources"].items():
        url = record["url"]
        if url not in cache:
            data = fetch(url)
            if data is None:
                raise ValueError("editorial_refresh_unavailable")
            cache[url] = data, datetime.now(UTC).isoformat()
        data, at = cache[url]
        record.update(sha256=sha(data), retrieved_at=at, status="available")
        (incoming / (key + ".json")).write_bytes(data)
    write(incoming / "editorial-manifest.json", editorial)
    return {
        "doi": {"sha256": sha(raw), "retrieved_at": doi_manifest["retrieved_at"]},
        "editorial": {
            k: {"sha256": r["sha256"], "retrieved_at": r["retrieved_at"]}
            for k, r in editorial["sources"].items()
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", type=Path, required=True)
    args = parser.parse_args()
    audit_raw = args.audit.read_bytes()
    audit = json.loads(audit_raw)
    if (
        audit["version"] != "vh1-private-formula-source-review-1.0"
        or audit["gold_read"] is not False
        or set(audit["cases"]) != set(CASES)
    ):
        raise ValueError("formula_audit_invalid")
    now = datetime.now(UTC)
    output = (
        ROOT / "benchmarks/private/output" / now.strftime("vh1-formula-revisions-%Y%m%dT%H%M%SZ")
    )
    output.mkdir(exist_ok=False)
    (output / "source-review.json").write_bytes(audit_raw)
    plan = {
        "version": "vh1-formula-revisions-local-1.0",
        "created_at": now.isoformat(),
        "audit_sha256": sha(audit_raw),
        "source_sha256": {p: sha((ROOT / p).read_bytes()) for p in SOURCES},
        "code_sha256": {n: sha((ROOT / p).read_bytes()) for n, p in RUNNER.items()},
        "gold_read": False,
        "formal_xml_approved": False,
        "active_application_changed": False,
        "human_review_required": True,
        "autonomous_application": False,
        "cases": {},
    }
    for name, path in RUNNER.items():
        shutil.copyfile(ROOT / path, output / name)
    registry = ROOT / "config/validator-registry-vh1-history.json"
    shutil.copyfile(registry, output / "registry.json")
    plan["registry_sha256"] = sha(registry.read_bytes())
    profile = load_profile(ROOT / "profiles/esa-aop-1.1.json")
    cache = {}
    for case, name in CASES.items():
        folder = output / case
        folder.mkdir()
        data_path = ROOT / name
        manifest = load_manifest(ROOT / f"corpus/manifests/{case}.json")
        source = _single_artifact(data_path.parent, manifest, "source_idml").read_bytes()
        pdf_path = _single_artifact(data_path.parent, manifest, "approved_pdf_reference")
        pdf = pdf_path.read_bytes()
        review = audit["cases"][case]
        if sha(pdf) != review["source_pdf_sha256"]:
            raise ValueError("source_pdf_changed")
        catalogs = {}
        hashes = {}
        for base in (
            ROOT / "benchmarks/private/output/h1-country-codes-v1" / case,
            METADATA / case,
        ):
            for kind, contract in KINDS.items():
                path = base / (kind + ".json")
                if path.exists():
                    catalogs[kind] = contract.model_validate_json(path.read_bytes())
                    hashes[kind] = sha(path.read_bytes())
        original = catalogs["formula_catalog"]
        if hashes["formula_catalog"] != review["previous_catalog_sha256"]:
            raise ValueError("source_catalog_changed")
        by_id = {e.case_id: e for e in original.entries}
        if len(review["entries"]) != len(by_id) or {r["case_id"] for r in review["entries"]} != set(
            by_id
        ):
            raise ValueError("formula_audit_incomplete")
        corrections, crops = [], {}
        changes = []
        for row in review["entries"]:
            old = by_id[row["case_id"]]
            if row["before_sha256"] != old.mathml_sha256:
                raise ValueError("formula_audit_stale")
            if row["status"] not in {
                "source_correction",
                "reviewed_no_confirmed_transcription_defect",
                "glyph_or_style_review_pending",
            }:
                raise ValueError("formula_audit_status_invalid")
            if row["status"] != "source_correction":
                continue
            crop = render_formula_crop(
                pdf_path, PdfFormulaCrop(row["page_index"], tuple(row["bbox"]))
            )
            crops[old.case_id] = crop
            (folder / (old.case_id + ".png")).write_bytes(crop)
            x0, y0, x1, y1 = row["bbox"]
            correction = FormulaTranscriptionEntry.model_validate(
                {
                    **old.model_dump(mode="json"),
                    "mathml": row["mathml"],
                    "mathml_sha256": row["after_sha256"],
                    "qualification": {
                        "method": "development-visual-source-review-1.0",
                        "previous_catalog_id": original.catalog_id,
                        "previous_mathml": old.mathml,
                        "previous_mathml_sha256": old.mathml_sha256,
                        "previous_qualification": old.qualification.model_dump(mode="json"),
                        "corrected_mathml_sha256": row["after_sha256"],
                        "source_idml_sha256": sha(source),
                        "source_pdf_sha256": sha(pdf),
                        "page_index": row["page_index"],
                        "box": {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0},
                        "crop_sha256": sha(crop),
                        "reviewed_at": now.isoformat(),
                        "reason_code": row["reason_code"],
                        "human_review_required": True,
                        "gold_exposed_to_agent": False,
                        "autonomous_application": False,
                    },
                }
            )
            corrections.append(correction)
            changes.append(row)
        revised = revise_formula_catalog(
            original,
            source_idml=source,
            source_pdf=pdf,
            corrections=tuple(corrections),
            crops=crops,
        )
        write(folder / "formula_catalog.json", revised.model_dump(mode="json"))
        catalogs["formula_catalog"] = revised
        pipeline = DeterministicPipeline(profile=profile, **catalogs)
        result, repeat = [pipeline.run(source, logical_name=data_path.name) for _ in range(2)]
        if result.xml != repeat.xml or not result.validation.valid:
            raise ValueError("formula_pipeline_invalid")
        builder = PackageBuilder()
        files = builder.scielo_files(
            package_stem=profile.package_stem(result.canonical.article_id),
            xml=result.xml,
            pdf=pdf,
            assets=tuple(
                AssetPayload(source_name=p.name, data=p.read_bytes())
                for p in figure_paths(data_path.parent, manifest)
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
        baseline = BASELINE / case
        old_xml, old_zip = [
            (baseline / ("candidate." + ext)).read_bytes() for ext in ("xml", "zip")
        ]
        if (sha(old_xml), sha(old_zip)) != BEFORE[case]:
            raise ValueError("formula_baseline_changed")
        delta = verify_delta(old_xml, xml, changes)
        assets = verify_package(old_zip, package)
        (folder / "candidate.xml").write_bytes(xml)
        (folder / "candidate.zip").write_bytes(package)
        write(folder / "canonical.json", result.canonical.model_dump(mode="json"))
        scope = json.loads((baseline / "scope.json").read_bytes())
        scope.update(xml_sha256=sha(xml), package_sha256=sha(package))
        incoming = folder / "incoming"
        incoming.mkdir()
        authorities = refresh_authorities(baseline / "incoming", incoming, xml, package, cache)
        grant_id = str(
            uuid5(NAMESPACE_URL, "idml:vh1:formula-revisions:LAB_ONLY:" + output.name + case)
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
            "scope_sha256": scope_digest(scope),
            "previous_catalog_sha256": review["previous_catalog_sha256"],
            "catalog_id": revised.catalog_id,
            "catalog_sha256": sha((folder / "formula_catalog.json").read_bytes()),
            "unchanged_catalogs": {k: v for k, v in hashes.items() if k != "formula_catalog"},
            "offline_valid": True,
            "deterministic": True,
            "delta": delta,
            "unchanged_assets": assets,
            "review_counts": dict(Counter(r["status"] for r in review["entries"])),
            "fresh_authorities": authorities,
            "files": {
                p.relative_to(folder).as_posix(): sha(p.read_bytes())
                for p in folder.rglob("*")
                if p.is_file()
            },
        }
        print(
            json.dumps(
                {"case": case, "counts": plan["cases"][case]["review_counts"], "delta": delta}
            ),
            flush=True,
        )
    write(output / "plan.json", plan)
    print(
        json.dumps(
            {"directory": str(output), "plan_sha256": sha((output / "plan.json").read_bytes())}
        )
    )


if __name__ == "__main__":
    main()
