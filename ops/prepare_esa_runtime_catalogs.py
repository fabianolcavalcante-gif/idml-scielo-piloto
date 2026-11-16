"""Prepare private catalog material for the two ESA development articles from verified inputs."""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from idml_foundation.ai.formula_catalog import FormulaVisualRevision
from idml_foundation.domain.corpus import load_manifest
from idml_foundation.pipeline.profile import load_profile
from idml_foundation.pipeline.service import DeterministicPipeline
from idml_foundation.release import (
    articlemeta_dates,
    articlemeta_orcids,
    crossref_authority,
    formal_metadata,
    institution_locations,
    journal_metadata,
    reference_types,
    verified_funding,
)
from idml_foundation.services.enrichment import KINDS
from ops.collect_vh1_articlemeta_dates import PID
from ops.gate_phase7_7c06 import _single_artifact
from ops.qualify_vh1_metadata import LOCATION_ASSIGNMENTS
from ops.qualify_vh1_reference_types import CASES, ROOT, SELECTIONS, SNAPSHOT_FILES

FORMULAS = ROOT / "benchmarks/private/output/vh1-reference-types-20261014T104156Z"
ORCIDS = ("0000-0003-1136-7986", "0000-0002-3963-5973", "0000-0002-0839-9947")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def prepare(case, directory, inputs, output):
    records = json.loads((inputs / "verified-manifest.json").read_bytes())
    corpus = load_manifest(ROOT / f"corpus/manifests/{case}.json")
    profile = load_profile(ROOT / "profiles/esa-aop-1.1.json")
    path = _single_artifact(directory, corpus, "source_idml")
    data = path.read_bytes()
    source_hash = digest(data)
    pdf = _single_artifact(directory, corpus, "approved_pdf_reference").read_bytes()
    published = _single_artifact(directory, corpus, "approved_xml_reference").read_bytes()
    base = dict(corpus_id=case, source_idml_sha256=source_hash)
    catalogs, permissions, deferred = {}, {}, []
    first = case == "esa-e20240086"
    checked = datetime.now(UTC).isoformat()

    def read(key, expected_url):
        spec = records[key]
        if spec["status"] != "available" or spec["url"] != expected_url:
            raise ValueError("source_unavailable")
        raw = (inputs / (key + ".bin")).read_bytes()
        if digest(raw) != spec["sha256"]:
            raise ValueError("source_digest_mismatch")
        return raw

    def article():
        return (
            DeterministicPipeline(profile=profile, **catalogs)
            .run(data, logical_name=path.name)
            .canonical
        )

    def add(kind, value, source, evidence, collected):
        raw = value.model_dump_json().encode()
        if (
            value.source_idml_sha256 != source_hash
            or value.journal_profile_id != profile.profile_id
        ):
            raise ValueError("catalog_source_mismatch")
        catalogs[kind] = value
        (output / (kind + ".json")).write_bytes(raw)
        permissions[kind] = dict(
            source=source,
            catalog_sha256=digest(raw),
            evidence_sha256=evidence,
            collected_at=collected,
        )

    output.mkdir(parents=True, exist_ok=False)
    raw_formulas = (FORMULAS / case / "formula_catalog.json").read_bytes()
    proof = ROOT / "benchmarks/qualification/reports/vh1-reference-types-linux-v1.json"
    expected = json.loads(proof.read_bytes())["qualification"]["cases"][case]["catalog_sha256"]
    if digest(raw_formulas) != expected:
        raise ValueError("qualified_formula_catalog_changed")
    f = KINDS["formula_catalog"].model_validate_json(raw_formulas)
    if any(
        e.qualification.source_pdf_sha256 != digest(pdf)
        for e in f.entries
        if isinstance(e.qualification, FormulaVisualRevision)
    ):
        raise ValueError("formula_pdf_mismatch")
    add("formula_catalog", f, "authorized_article", digest(pdf), checked)
    crkey = "crossref86" if first else "crossref"
    doi = "10.1590%2Fs1413-415220240086" if first else "10.1590%2Fs1413-415220240135"
    cr = read(crkey, "https://api.crossref.org/works/" + doi)
    if not first:
        cat, _ = crossref_authority.build_crossref_metadata_authority_catalog(
            article=article(), crossref_response=cr, **base
        )
        add(
            "crossref_metadata_catalog",
            cat,
            "crossref_public_record",
            digest(cr),
            records[crkey]["retrieved_at"],
        )
    historic = ROOT / "benchmarks/private/output/h1-country-codes-v1" / case
    previous = KINDS["formal_metadata_catalog"].model_validate_json(
        (historic / "formal_metadata_catalog.json").read_bytes()
    )
    if previous.formal_reference_sha256 and previous.formal_reference_sha256 != digest(published):
        raise ValueError("formal_reference_mismatch")
    cat, _ = formal_metadata.build_formal_metadata_authority_catalog(
        article=article(),
        crossref_response=cr,
        formal_reference_xml=published if previous.formal_reference_sha256 else None,
        **base,
    )
    add(
        "formal_metadata_catalog",
        cat,
        "editorial_record",
        digest(cr),
        records[crkey]["retrieved_at"],
    )
    if first:
        cat = KINDS["editorial_enrichment_catalog"].model_validate_json(
            (historic / "editorial_enrichment_catalog.json").read_bytes()
        )
        assert cat.approved_xml_sha256 == digest(published)
        add("editorial_enrichment_catalog", cat, "editorial_record", digest(published), checked)
        raw = read("articlemeta", articlemeta_dates.source_url(PID))
        date = records["articlemeta"]["retrieved_at"]
        cat = articlemeta_dates.build_articlemeta_date_catalog(
            article=article(), response=raw, pid=PID, collected_at=date, **base
        )
        add(
            "articlemeta_date_catalog",
            cat,
            "scielo_articlemeta_record",
            cat.response_sha256,
            cat.collected_at.isoformat(),
        )
        people = {
            i: (read(i, articlemeta_orcids.person_url(i)), records[i]["retrieved_at"])
            for i in ORCIDS
        }
        cat = articlemeta_orcids.build_articlemeta_orcid_catalog(
            article=article(), response=raw, pid=PID, collected_at=date, persons=people, **base
        )
        add(
            "articlemeta_orcid_catalog",
            cat,
            "scielo_articlemeta_orcid_records",
            cat.evidence_sha256,
            cat.collected_at.isoformat(),
        )
    assignments, snapshots = {}, {}
    for aff, rule in LOCATION_ASSIGNMENTS[case].items():
        if rule == "easwari_it" and records["easwari"]["status"] != "available":
            rule = "easwari_it_disclosure"
        group = {}
        try:
            for key in institution_locations.RULES[rule].sources:
                url = institution_locations.SOURCES[key].url
                group[key] = (read(key, url), url, records[key]["retrieved_at"])
                institution_locations.verify_snapshot(key, *group[key])
        except ValueError as e:
            deferred.append(
                dict(field="institution_location", rule=rule, reason=str(e).splitlines()[0][:80])
            )
            continue
        assignments[aff] = rule
        snapshots.update(group)
    if assignments:
        cat = institution_locations.build_institution_location_catalog(
            article=article(), assignments=assignments, snapshots=snapshots, **base
        )
        add(
            "institution_location_catalog",
            cat,
            "institutional_location_records",
            cat.evidence_sha256,
            cat.collected_at.isoformat(),
        )
    if first:
        rule = "embrapa-seg-21.17.02.001.05.00"
        url = verified_funding.RULES[rule].source_url
        cat = verified_funding.build_verified_funding_catalog(
            article=article(),
            funding_index=0,
            rule_id=rule,
            response=read("funding", url),
            source_url=url,
            collected_at=records["funding"]["retrieved_at"],
            **base,
        )
        add(
            "verified_funding_catalog",
            cat,
            "institutional_funding_record",
            cat.response_sha256,
            cat.collected_at.isoformat(),
        )
    selections, responses, dates = {}, {}, []
    for ref, rule in SELECTIONS[case].items():
        key = SNAPSHOT_FILES[rule].replace(".", "_")
        if records[key]["status"] != "available":
            deferred.append(dict(field="reference_type", rule=rule, reason="source_unavailable"))
            continue
        raw = read(key, reference_types.RULES[rule].source_url)
        if not reference_types.RULES[rule].accepts(digest(raw)):
            deferred.append(dict(field="reference_type", rule=rule, reason="source_bytes_changed"))
            continue
        selections[ref] = rule
        responses[rule] = raw
        dates.append(records[key]["retrieved_at"])
    if selections:
        cat = reference_types.build_reference_type_catalog(
            article=article(),
            selections=selections,
            responses=responses,
            collected_at=min(dates),
            **base,
        )
        add(
            "reference_type_catalog",
            cat,
            "institutional_bibliographic_records",
            cat.evidence_sha256,
            cat.collected_at.isoformat(),
        )
    cat = journal_metadata.build_journal_metadata_catalog(
        article(),
        registry=read("journal", journal_metadata.REGISTRY_URL),
        collected_at=datetime.fromisoformat(records["journal"]["retrieved_at"]),
        **base,
    )
    add(
        "journal_metadata_catalog",
        cat,
        "scielo_journal_registry",
        cat.response_sha256,
        cat.collected_at.isoformat(),
    )
    final = DeterministicPipeline(profile=profile, **catalogs).run(data, logical_name=path.name)
    assert final.validation.valid
    receipt = dict(
        source_idml_sha256=source_hash,
        profile_id=profile.profile_id,
        catalogs=permissions,
        deferred=deferred,
        xml_sha256=digest(final.xml),
    )
    (output / "material.json").write_text(json.dumps(receipt, indent=2))
    print(
        json.dumps(dict(case=case, catalogs=len(catalogs), deferred=deferred, offline_valid=True)),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    for case, source in CASES.items():
        prepare(case, (ROOT / source).parent, args.inputs, args.output / case)
