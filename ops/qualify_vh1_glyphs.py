"""Qualify four source-confirmed script letters and explicit IDML run positions."""

import json
import shutil
from collections import Counter
from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, uuid5
from zipfile import ZipFile

from lxml import etree
from pypdf import PdfReader

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
from ops.gate_phase7_7c06 import _single_artifact
from ops.gate_vh1_formula_revisions import FINAL as BEFORE
from ops.qualify_vh1_formula_revisions import (
    CASES,
    METADATA,
    NS,
    ROOT,
    RUNNER,
    refresh_authorities,
    sha,
    verify_package,
    write,
)
from ops.qualify_vh1_formula_revisions import SOURCES as PREVIOUS_SOURCES
from ops.qualify_vh1_formula_revisions import (
    verify_delta as verify_math_delta,
)

BASELINE = ROOT / "benchmarks/private/output/vh1-formula-revisions-20261008T131739Z"
SOURCES = (
    *PREVIOUS_SOURCES,
    "src/idml_foundation/pipeline/idml_parser.py",
    "ops/qualify_vh1_glyphs.py",
)
GLYPHS = {"008": ("A", 1), "011": ("X", 2), "016": ("A", 1), "017": ("X", 1)}
# Independently checked against the source run Position=Normal and PDF pages 4/5.
# This is a validation whitelist, never a production article-specific rewrite.
POSITIONS = {
    "list-b082b13a-7d6c-5a2c-b2fc-f73a89aeb640": {"\u2190": 4, "\u2124": 3},
    "paragraph-31a4a342-53c2-5dd1-8b59-ec897d9092d9": {"\u2124": 1},
    "paragraph-9dc6ddaf-1865-5c01-bd9d-ba42f6835f83": {"\u2124 ": 1, "\u211d": 1},
    "list-d6467a00-3037-5aa0-b49c-a4d417bbfef5": {"\u2190": 4},
}


def unwrap(node):
    parent, previous = node.getparent(), node.getprevious()
    value = (node.text or "") + (node.tail or "")
    if previous is None:
        parent.text = (parent.text or "") + value
    else:
        previous.tail = (previous.tail or "") + value
    parent.remove(node)


def verify_delta(before, after, changes, *, first):
    old = etree.fromstring(before, etree.XMLParser(resolve_entities=False, no_network=True))
    removed = []
    for identifier, counts in {}.items() if first else POSITIONS.items():
        matches = old.xpath(".//p[@id=$id]", id=identifier)
        if len(matches) != 1:
            raise ValueError("position_paragraph_not_unique")
        nodes = [n for n in matches[0].findall("sub") if n.text in counts]
        if Counter(n.text for n in nodes) != counts:
            raise ValueError("position_source_mismatch")
        for node in nodes:
            if len(node) or node.attrib:
                raise ValueError("position_not_atomic")
            removed.append({"parent": identifier, "text_sha256": sha(node.text.encode())})
            unwrap(node)
    delta = verify_math_delta(etree.tostring(old), after, changes)
    return {**delta, "source_normal_positions": removed}


def inspect_source(pdf_path, idml_path):
    """Retain source facts, including malformed ToUnicode, not inferred mathematics."""
    page = PdfReader(pdf_path, strict=True).pages[3]
    chunks = []

    def visitor(text, cm, tm, font, size):
        if (
            font
            and text.strip()
            and any(name in str(font.get("/BaseFont")) for name in ("LBIDBB", "ANYKDX", "TAMUJL"))
        ):
            chunks.append({"text": text, "font": str(font.get("/BaseFont")), "matrix": tm})

    page.extract_text(visitor_text=visitor)
    with ZipFile(idml_path) as archive:
        raw = archive.read("Stories/Story_u2b9.xml")
    root = etree.fromstring(raw, etree.XMLParser(resolve_entities=False, no_network=True))
    runs = root.xpath(".//CharacterStyleRange[@Position='Normal']")
    positions = Counter("".join(r.xpath("./Content/text()")) for r in runs)
    if positions != {"\u2190": 9, "\u2124": 4, "\u2124 ": 1, "\u211d": 1}:
        raise ValueError("source_normal_run_inventory_changed")
    font = page["/Resources"]["/Font"]["/C2_4"].get_object()
    cmap = font["/ToUnicode"].get_object().get_data()
    return {
        "story_sha256": sha(raw),
        "normal_positions": dict(positions),
        "pdf_font_chunks": chunks,
        "ambiguous_cmap_sha256": sha(cmap),
        "ambiguous_cmap": cmap.decode("ascii"),
        "source_characters_retained": ["U+0404", "U+00D8"],
        "abstention": {
            "case_id": "esa-math-notes-inline-005",
            "reason": (
                "slanted glyph and defective duplicated ToUnicode mapping; "
                "no reliable bar/letter decision"
            ),
            "mathml_unchanged": True,
            "human_review_required": True,
        },
        "gold_read": False,
    }


def revised_catalog(case, folder, source, pdf_path, now):
    previous_path = BASELINE / case / "formula_catalog.json"
    previous = KINDS["formula_catalog"].model_validate_json(previous_path.read_bytes())
    if case.endswith("86"):
        return previous, []
    original = KINDS["formula_catalog"].model_validate_json(
        (
            ROOT / "benchmarks/private/output/h1-country-codes-v1" / case / "formula_catalog.json"
        ).read_bytes()
    )
    locations = {
        c["case_id"]: c
        for c in json.loads(
            (ROOT / "config/visual-formula-crops-esa-e20240135-v1.json").read_bytes()
        )["crops"]
    }
    corrections, crops, changes = [], {}, []
    old_by_id = {e.case_id: e for e in original.entries}
    for entry in previous.entries:
        short = entry.case_id.removeprefix("esa-math-notes-inline-")
        if short not in GLYPHS:
            if hasattr(entry.qualification, "previous_catalog_id"):
                corrections.append(entry)
                crops[entry.case_id] = (BASELINE / case / (entry.case_id + ".png")).read_bytes()
            continue
        letter, count = GLYPHS[short]
        tree = etree.fromstring(entry.mathml.encode())
        nodes = tree.xpath(".//m:mi[text()=$letter]", namespaces=NS, letter=letter)
        if len(nodes) != count or any(n.attrib for n in nodes):
            raise ValueError("script_letter_source_changed")
        for node in nodes:
            node.set("mathvariant", "script")
        after = canonical_mathml(etree.tostring(tree, encoding="unicode"), display=False)
        location = locations[entry.case_id]
        crop = render_formula_crop(
            pdf_path, PdfFormulaCrop(location["page_index"], tuple(location["bbox"]))
        )
        crops[entry.case_id] = crop
        (folder / (entry.case_id + ".png")).write_bytes(crop)
        x0, y0, x1, y1 = location["bbox"]
        old = old_by_id[entry.case_id]
        correction = FormulaTranscriptionEntry.model_validate(
            {
                **old.model_dump(mode="json"),
                "mathml": after,
                "mathml_sha256": sha(after.encode()),
                "qualification": {
                    "method": "development-visual-source-review-1.0",
                    "previous_catalog_id": original.catalog_id,
                    "previous_mathml": old.mathml,
                    "previous_mathml_sha256": old.mathml_sha256,
                    "previous_qualification": old.qualification.model_dump(mode="json"),
                    "corrected_mathml_sha256": sha(after.encode()),
                    "source_idml_sha256": sha(source),
                    "source_pdf_sha256": sha(pdf_path.read_bytes()),
                    "page_index": location["page_index"],
                    "box": {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0},
                    "crop_sha256": sha(crop),
                    "reviewed_at": now.isoformat(),
                    "reason_code": "symbol_mismatch",
                    "human_review_required": True,
                    "gold_exposed_to_agent": False,
                    "autonomous_application": False,
                },
            }
        )
        corrections.append(correction)
        changes.append(
            {"before_sha256": entry.mathml_sha256, "after_sha256": correction.mathml_sha256}
        )
    revised = revise_formula_catalog(
        original,
        source_idml=source,
        source_pdf=pdf_path.read_bytes(),
        corrections=tuple(corrections),
        crops=crops,
    )
    # The fourteen preceding corrections and their original provenance must be exact.
    for old, new in zip(previous.entries, revised.entries, strict=True):
        if old.case_id.removeprefix("esa-math-notes-inline-") not in GLYPHS and old != new:
            raise ValueError("previous_formula_revision_changed")
    return revised, changes


def main():
    now = datetime.now(UTC)
    output = ROOT / "benchmarks/private/output" / now.strftime("vh1-glyphs-%Y%m%dT%H%M%SZ")
    output.mkdir(exist_ok=False)
    plan = {
        "version": "vh1-glyphs-local-1.0",
        "created_at": now.isoformat(),
        "source_sha256": {p: sha((ROOT / p).read_bytes()) for p in SOURCES},
        "code_sha256": {n: sha((ROOT / p).read_bytes()) for n, p in RUNNER.items()},
        "gold_read": False,
        "formal_xml_approved": False,
        "active_application_changed": False,
        "human_review_required": True,
        "autonomous_application": False,
        "cases": {},
        "remaining_ambiguous_glyphs": 1,
    }
    for name, path in RUNNER.items():
        shutil.copyfile(ROOT / path, output / name)
    registry = ROOT / "config/validator-registry-vh1-history.json"
    shutil.copyfile(registry, output / "registry.json")
    plan["registry_sha256"] = sha(registry.read_bytes())
    cache = {}
    for case, name in CASES.items():
        folder = output / case
        folder.mkdir()
        data_path = ROOT / name
        source = data_path.read_bytes()
        manifest = load_manifest(ROOT / f"corpus/manifests/{case}.json")
        if _single_artifact(data_path.parent, manifest, "source_idml").read_bytes() != source:
            raise ValueError("source_idml_mismatch")
        pdf_path = _single_artifact(data_path.parent, manifest, "approved_pdf_reference")
        pdf = pdf_path.read_bytes()
        catalogs = {}
        for base in (
            ROOT / "benchmarks/private/output/h1-country-codes-v1" / case,
            METADATA / case,
            BASELINE / case,
        ):
            for kind, contract in KINDS.items():
                path = base / (kind + ".json")
                if path.exists():
                    catalogs[kind] = contract.model_validate_json(path.read_bytes())
        catalog, changes = revised_catalog(case, folder, source, pdf_path, now)
        catalogs["formula_catalog"] = catalog
        write(folder / "formula_catalog.json", catalog.model_dump(mode="json"))
        if case.endswith("135"):
            write(folder / "source-inspection.json", inspect_source(pdf_path, data_path))
        profile = load_profile(ROOT / "profiles/esa-aop-1.1.json")
        pipeline = DeterministicPipeline(profile=profile, **catalogs)
        result, repeat = [pipeline.run(source, logical_name=data_path.name) for _ in range(2)]
        if result.xml != repeat.xml or not result.validation.valid:
            raise ValueError("pipeline_invalid")
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
            raise ValueError("baseline_changed")
        delta = verify_delta(old_xml, xml, changes, first=case.endswith("86"))
        assets = verify_package(old_zip, package)
        (folder / "candidate.xml").write_bytes(xml)
        (folder / "candidate.zip").write_bytes(package)
        write(folder / "canonical.json", result.canonical.model_dump(mode="json"))
        scope = json.loads((baseline / "scope.json").read_bytes())
        scope.update(xml_sha256=sha(xml), package_sha256=sha(package))
        incoming = folder / "incoming"
        incoming.mkdir()
        authorities = refresh_authorities(baseline / "incoming", incoming, xml, package, cache)
        grant_id = str(uuid5(NAMESPACE_URL, "idml:vh1:glyphs:LAB_ONLY:" + output.name + case))
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
            "previous_catalog_sha256": sha((baseline / "formula_catalog.json").read_bytes()),
            "catalog_id": catalog.catalog_id,
            "catalog_sha256": sha((folder / "formula_catalog.json").read_bytes()),
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
        print(
            json.dumps(
                {
                    "case": case,
                    "formula_changes": len(changes),
                    "position_changes": len(delta["source_normal_positions"]),
                }
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
