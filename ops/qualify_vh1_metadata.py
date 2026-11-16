"""Rebuild authorized inputs; whitelist the complete XML delta; stage a private native lab."""

import argparse
import hashlib
import json
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from lxml import etree

from idml_foundation.domain.corpus import load_manifest
from idml_foundation.pipeline.profile import load_profile
from idml_foundation.pipeline.service import DeterministicPipeline
from idml_foundation.release.articlemeta_dates import build_articlemeta_date_catalog, source_url
from idml_foundation.release.articlemeta_orcids import build_articlemeta_orcid_catalog, person_url
from idml_foundation.release.institution_locations import (
    RULES,
    build_institution_location_catalog,
)
from idml_foundation.release.institution_locations import (
    SOURCES as LOCATION_SOURCES,
)
from idml_foundation.release.package_builder import AssetPayload, PackageBuilder
from idml_foundation.release.verified_funding import build_verified_funding_catalog
from idml_foundation.services.enrichment import KINDS
from idml_foundation.services.validation_scope import scope_digest
from ops.build_h1_real_packages import figure_paths
from ops.gate_phase7_7c06 import _single_artifact
from ops.gate_vh1_editorial import CASES, PACKAGES
from ops.prepare_vh1_scoped_socket import SOURCES

ROOT = Path(__file__).resolve().parents[1]
CODE = {**SOURCES, "run_vh1_metadata_linux.py": "ops/run_vh1_metadata_linux.py"}
CHANGED = (
    "src/idml_foundation/pipeline/canonical_mapper.py",
    "src/idml_foundation/pipeline/jats_builder.py",
    "src/idml_foundation/pipeline/metadata_normalization.py",
    "ops/qualify_vh1_metadata.py",
    "src/idml_foundation/publication_dates.py",
    "src/idml_foundation/release/formal_metadata.py",
    "src/idml_foundation/pipeline/funding_parser.py",
    "src/idml_foundation/release/articlemeta_dates.py",
    "src/idml_foundation/pipeline/service.py",
    "src/idml_foundation/services/enrichment.py",
    "src/idml_foundation/services/source_authorization.py",
    "ops/collect_vh1_articlemeta_dates.py",
    "src/idml_foundation/release/articlemeta_orcids.py",
    "ops/collect_vh1_orcid_sources.py",
    "src/idml_foundation/release/institution_locations.py",
    "ops/collect_vh1_affiliation_sources.py",
    "src/idml_foundation/release/verified_funding.py",
    "ops/collect_vh1_funding_sources.py",
)

LOCATION_ASSIGNMENTS = {
    "esa-e20240086": {"affiliation-0c293498-3dde-51ad-93e0-5a9bfa8c88c5": "tokyo_gss"},
    "esa-e20240135": {
        "affiliation-b3f1268a-9b2a-5982-867f-1756e5b3386f": "cahcet_it",
        "affiliation-74cbfab3-e992-5d7f-97e3-24b224943cc8": "easwari_it",
        "affiliation-63499094-3bdb-52d3-bff4-e4bc6ec4af14": "tindivanam_it",
        "affiliation-f78f3038-c0e9-5731-b8e0-dcdb0cf3c24f": "syed_hameedha_cs",
    },
}
# Independent XML whitelist, deliberately not derived from the enrichment catalog/rules.
EXPECTED_LOCATIONS = {
    "University of Tokyo": ("Tokyo", "JP", "Tokyo"),
    "C. Abdul Hakeem College of Engineering & Technology": ("Melvisharam", "IN", "Tamil Nadu"),
    "Easwari Engineering College": ("Chennai", "IN", "Tamil Nadu"),
    "University College of Engineering Tindivanam": ("Tindivanam", "IN", "Tamil Nadu"),
    "Syed Hameedha Arts and Science College": ("Kilakarai", "IN", "Tamil Nadu"),
}

# Frozen independent expected associations from the official record, not from candidate/catalog.
EXPECTED_ORCIDS = {
    ("Daniel Jadyr Leite", "Costa"): "0000-0003-1136-7986",
    ("Giovanna", "Collyer"): "0000-0002-3963-5973",
    ("Wilson Tadeu Lopes da", "Silva"): "0000-0002-0839-9947",
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)


def verify_delta(
    before,
    after,
    *,
    deferred_statement_sha256=None,
    articlemeta_dates=False,
    articlemeta_orcids=False,
    institution_locations=False,
    verified_funding=False,
):
    """Independent expected changes. Every other node/attribute/text must remain equal."""
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
    old, new = etree.fromstring(before, parser), etree.fromstring(after, parser)
    states = roles = dates = deferred = 0
    for aff in old.xpath("front/article-meta/aff"):
        city = aff.find('addr-line/named-content[@content-type="city"]')
        original = aff.findtext('institution[@content-type="original"]') or ""
        if (
            city is not None
            and city.text == "São Carlos (SP)"
            and aff.findtext("country") == "Brazil"
            and "São Carlos (SP), Brazil." in original
        ):
            city.text = "São Carlos"
            etree.SubElement(
                city.getparent(), "named-content", {"content-type": "state"}
            ).text = "SP"
            states += 1
    labels = {
        "Writing\u2014original draft": ("Writing \u2013 original draft", "writing-original-draft"),
        "Writing\u2014review and editing": (
            "Writing \u2013 review & editing",
            "writing-review-editing",
        ),
    }
    for role in old.xpath("front/article-meta/contrib-group/contrib/role"):
        if role.text in labels and not role.attrib:
            label, slug = labels[role.text]
            role.text = label
            role.set("content-type", "https://credit.niso.org/contributor-roles/" + slug + "/")
            roles += 1
    if deferred_statement_sha256:
        groups = old.xpath("front/article-meta/funding-group")
        if len(groups) != 1:
            raise ValueError("unexpected_funding_baseline")
        group = groups[0]
        statement = group.findtext("funding-statement")
        awards = group.findall("award-group")
        if (
            not statement
            or sha(statement.encode()) != deferred_statement_sha256
            or len(awards) != 1
            or len(awards[0]) != 1
            or awards[0][0].tag != "funding-source"
            or not statement.startswith((awards[0][0].text or "") + ",")
        ):
            raise ValueError("unexpected_funding_baseline")
        group.remove(awards[0])
        deferred = 1
    if articlemeta_dates:
        pub = old.find('front/article-meta/pub-date[@date-type="pub"]')
        history = old.find("front/article-meta/history")
        if pub is None or history is None or len(pub) != 1 or pub.findtext("year") != "2025":
            raise ValueError("unexpected_publication_baseline")
        pub.set("iso-8601-date", "2025-07-07")
        day, month = etree.Element("day"), etree.Element("month")
        day.text = month.text = "07"
        pub.insert(0, day)
        pub.insert(1, month)
        for kind, previous, proposed in (
            ("received", "2024-06-09", "2024-09-06"),
            ("accepted", "2025-09-03", "2025-03-09"),
        ):
            node = history.find(f'date[@date-type="{kind}"]')
            if node is None or node.get("iso-8601-date") != previous:
                raise ValueError("unexpected_history_baseline")
            if [node.findtext(k) for k in ("year", "month", "day")] != previous.split("-"):
                raise ValueError("unexpected_history_baseline")
            node.set("iso-8601-date", proposed)
            node.find("month").text, node.find("day").text = proposed.split("-")[1:]
        if history.find('date[@date-type="pub"]') is not None:
            raise ValueError("unexpected_history_baseline")
        node = etree.SubElement(
            history, "date", {"date-type": "pub", "iso-8601-date": "2025-07-07"}
        )
        for tag, value in (("day", "07"), ("month", "07"), ("year", "2025")):
            etree.SubElement(node, tag).text = value
    if articlemeta_orcids:
        seen = set()
        for contributor in old.xpath(
            'front/article-meta/contrib-group/contrib[@contrib-type="author"]'
        ):
            key = (contributor.findtext("name/given-names"), contributor.findtext("name/surname"))
            if (
                key not in EXPECTED_ORCIDS
                or key in seen
                or contributor.find("contrib-id") is not None
            ):
                raise ValueError("unexpected_orcid_baseline")
            seen.add(key)
            node = etree.Element(
                "contrib-id", {"contrib-id-type": "orcid", "authenticated": "false"}
            )
            node.text = EXPECTED_ORCIDS[key]
            contributor.insert(0, node)
        if seen != set(EXPECTED_ORCIDS):
            raise ValueError("unexpected_orcid_baseline")
    location_count = 0
    if institution_locations:
        for aff in old.xpath("front/article-meta/aff"):
            name = aff.findtext('institution[@content-type="orgname"]')
            if name not in EXPECTED_LOCATIONS:
                continue
            city, country, state = EXPECTED_LOCATIONS[name]
            addr = aff.find("addr-line")
            if (
                addr is None
                or addr.findtext('named-content[@content-type="city"]') != city
                or addr.find('named-content[@content-type="state"]') is not None
                or aff.find("country") is None
                or aff.find("country").get("country") != country
            ):
                raise ValueError("unexpected_location_baseline")
            etree.SubElement(addr, "named-content", {"content-type": "state"}).text = state
            location_count += 1
        if not location_count:
            raise ValueError("unexpected_location_baseline")
    if verified_funding:
        groups = old.xpath("front/article-meta/funding-group")
        if (
            len(groups) != 1
            or len(groups[0]) != 1
            or groups[0][0].tag != "funding-statement"
            or sha((groups[0][0].text or "").encode())
            != "2193d3d76c7f2f9155be71a559c4c5f927022f3a4ebc2ff78833590a5dcaa72e"
        ):
            raise ValueError("unexpected_verified_funding_baseline")
        award = etree.Element("award-group")
        etree.SubElement(
            award, "funding-source"
        ).text = "Brazilian Agricultural Research Corporation"
        etree.SubElement(award, "award-id").text = "21.17.02.001.05.00"
        groups[0].insert(0, award)
    if etree.tostring(old, method="c14n") != etree.tostring(new, method="c14n"):
        raise ValueError("unexpected_metadata_delta")
    result = {
        "states_extracted": states,
        "credit_roles_normalized": roles,
        "publication_year_added": dates,
    }
    if deferred_statement_sha256:
        result["funding_structure_deferred"] = deferred
    if articlemeta_dates:
        result["articlemeta_date_fields"] = 3
    if articlemeta_orcids:
        result["verified_author_orcids"] = 3
    if institution_locations:
        result["verified_institution_states"] = location_count
    if verified_funding:
        result["verified_funding_pairs"] = 1
    return result


def main(
    articlemeta_snapshot=None, orcid_snapshot=None, affiliation_snapshot=None, funding_snapshot=None
):
    now = datetime.now(UTC)
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    output = ROOT / "benchmarks/private/output" / ("vh1-metadata-" + run_id)
    output.mkdir(exist_ok=False)
    plan = {
        "version": "vh1-metadata-local-1.0",
        "created_at": now.isoformat(),
        "source_sha256": {name: sha((ROOT / name).read_bytes()) for name in CHANGED},
        "code_sha256": {name: sha((ROOT / path).read_bytes()) for name, path in CODE.items()},
        "cases": {},
        "gold_read": False,
        "catalog_values_changed": False,
        "active_application_changed": False,
        "formal_xml_approved": False,
    }
    for name, path in CODE.items():
        shutil.copyfile(ROOT / path, output / name)
    registry = ROOT / "config/validator-registry-vh1-scoped.json"
    shutil.copyfile(registry, output / "registry.json")
    plan["registry_sha256"] = sha(registry.read_bytes())
    profile = load_profile(ROOT / "profiles/esa-aop-1.1.json")
    vault = (
        ROOT
        / "benchmarks/private/output"
        / "incoming-25ca4293d4e180ad32b7751b50fd30cd0f66ace056ff7226cddf01640b69b1e8"
    )
    for case, filename in (
        ("esa-e20240086", "tmp/sample/ESA_2024086_AOP.idml"),
        ("esa-e20240135", "tmp/ARQUIVOS TESTE/ESA_2024135_AOP.idml"),
    ):
        source = ROOT / filename
        manifest = load_manifest(ROOT / f"corpus/manifests/{case}.json")
        # Only the source, approved PDF and figures are inputs, not gold XML.
        if _single_artifact(source.parent, manifest, "source_idml") != source:
            raise ValueError("source_identity_mismatch")
        data = source.read_bytes()
        base = ROOT / "benchmarks/private/output/h1-country-codes-v1" / case
        options = {
            kind: contract.model_validate_json((base / (kind + ".json")).read_bytes())
            for kind, contract in KINDS.items()
            if (base / (kind + ".json")).exists()
        }
        date_catalog = None
        orcid_catalog = None
        location_catalog = None
        funding_catalog = None
        funding_manifest = None
        location_manifest = {}
        person_manifest = None
        snapshot_manifest = None
        if articlemeta_snapshot and case == "esa-e20240086":
            raw_response = (articlemeta_snapshot / "articlemeta.json").read_bytes()
            snapshot_manifest = json.loads((articlemeta_snapshot / "manifest.json").read_bytes())
            if snapshot_manifest["sha256"] != sha(raw_response) or snapshot_manifest[
                "url"
            ] != source_url(snapshot_manifest["pid"]):
                raise ValueError("articlemeta_snapshot_binding_mismatch")
            original = DeterministicPipeline(profile=profile, **options).run(
                data, logical_name=source.name
            )
            date_catalog = build_articlemeta_date_catalog(
                article=original.canonical,
                source_idml_sha256=sha(data),
                response=raw_response,
                pid=snapshot_manifest["pid"],
                collected_at=snapshot_manifest["retrieved_at"],
                corpus_id=case,
            )
            options["articlemeta_date_catalog"] = date_catalog
        if orcid_snapshot and case == "esa-e20240086":
            raw_articlemeta = (orcid_snapshot / "articlemeta.json").read_bytes()
            orcid_articlemeta = json.loads(
                (orcid_snapshot / "articlemeta-manifest.json").read_bytes()
            )
            if orcid_articlemeta["sha256"] != sha(raw_articlemeta) or orcid_articlemeta[
                "url"
            ] != source_url(orcid_articlemeta["pid"]):
                raise ValueError("orcid_articlemeta_snapshot_mismatch")
            person_manifest = json.loads((orcid_snapshot / "persons-manifest.json").read_bytes())
            persons = {}
            for identifier, entry in person_manifest.items():
                if entry["url"] != person_url(identifier) or entry["status"] != "available":
                    raise ValueError("orcid_snapshot_origin_mismatch")
                raw_person = (orcid_snapshot / f"{identifier}.json").read_bytes()
                if sha(raw_person) != entry["sha256"]:
                    raise ValueError("orcid_snapshot_hash_mismatch")
                persons[identifier] = (raw_person, entry["retrieved_at"])
            original = DeterministicPipeline(profile=profile, **options).run(
                data, logical_name=source.name
            )
            orcid_catalog = build_articlemeta_orcid_catalog(
                article=original.canonical,
                source_idml_sha256=sha(data),
                response=raw_articlemeta,
                pid=orcid_articlemeta["pid"],
                collected_at=orcid_articlemeta["retrieved_at"],
                persons=persons,
                corpus_id=case,
            )
            options["articlemeta_orcid_catalog"] = orcid_catalog
        if affiliation_snapshot:
            locations = json.loads((affiliation_snapshot / "manifest.json").read_bytes())
            assignments = LOCATION_ASSIGNMENTS[case]
            required = {s for r in assignments.values() for s in RULES[r].sources}
            snapshots = {}
            for key in sorted(required):
                entry = locations[key]
                raw = (affiliation_snapshot / f"{key}.html").read_bytes()
                if sha(raw) != entry["sha256"] or entry["url"] != LOCATION_SOURCES[key].url:
                    raise ValueError("location_snapshot_binding_mismatch")
                snapshots[key] = (raw, entry["url"], entry["retrieved_at"])
                location_manifest[key] = entry
            original = DeterministicPipeline(profile=profile, **options).run(
                data, logical_name=source.name
            )
            location_catalog = build_institution_location_catalog(
                article=original.canonical,
                source_idml_sha256=sha(data),
                corpus_id=case,
                assignments=assignments,
                snapshots=snapshots,
            )
            options["institution_location_catalog"] = location_catalog
        if funding_snapshot and case == "esa-e20240086":
            funding_manifest = json.loads((funding_snapshot / "manifest.json").read_bytes())
            raw_funding = (funding_snapshot / "embrapa.pdf").read_bytes()
            if sha(raw_funding) != funding_manifest["sha256"]:
                raise ValueError("funding_snapshot_binding_mismatch")
            original = DeterministicPipeline(profile=profile, **options).run(
                data, logical_name=source.name
            )
            funding_catalog = build_verified_funding_catalog(
                article=original.canonical,
                source_idml_sha256=sha(data),
                corpus_id=case,
                funding_index=0,
                rule_id="embrapa-seg-21.17.02.001.05.00",
                response=raw_funding,
                source_url=funding_manifest["url"],
                collected_at=funding_manifest["retrieved_at"],
            )
            options["verified_funding_catalog"] = funding_catalog
        result = DeterministicPipeline(profile=profile, **options).run(
            data, logical_name=source.name
        )
        repeated = DeterministicPipeline(profile=profile, **options).run(
            data, logical_name=source.name
        )
        if result.xml != repeated.xml or not result.validation.valid:
            raise ValueError("conversion_invalid_or_unstable")
        builder = PackageBuilder()
        files = builder.scielo_files(
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
        package = builder.build(**args)
        if package.archive != builder.build(**args).archive:
            raise ValueError("package_not_deterministic")
        before = (base / "candidate.xml").read_bytes()
        if (
            sha(before) != CASES[case][0]
            or sha((base / "candidate.zip").read_bytes()) != PACKAGES[case]
        ):
            raise ValueError("baseline_mismatch")
        deferred = case == "esa-e20240086"
        delta = verify_delta(
            before,
            files[0].data,
            deferred_statement_sha256=(
                "2193d3d76c7f2f9155be71a559c4c5f927022f3a4ebc2ff78833590a5dcaa72e"
                if deferred
                else None
            ),
            articlemeta_dates=date_catalog is not None,
            articlemeta_orcids=orcid_catalog is not None,
            institution_locations=location_catalog is not None,
            verified_funding=funding_catalog is not None,
        )
        expected = (2, 3, 0) if case == "esa-e20240086" else (0, 0, 0)
        if deferred:
            expected = (*expected, 1)
        if date_catalog:
            expected = (*expected, 3)
        if orcid_catalog:
            expected = (*expected, 3)
        if location_catalog:
            expected = (*expected, 1 if case == "esa-e20240086" else 4)
        if funding_catalog:
            expected = (*expected, 1)
        if tuple(delta.values()) != expected:
            raise ValueError("expected_delta_missing")
        funding_review = deferred and funding_catalog is None
        if funding_review != (
            "funding_structure_requires_authority" in result.canonical.review_reasons
        ):
            raise ValueError("funding_review_status_mismatch")
        folder = output / case
        folder.mkdir()
        (folder / "candidate.xml").write_bytes(files[0].data)
        (folder / "candidate.zip").write_bytes(package.archive)
        if funding_catalog:
            write_json(
                folder / "verified_funding_catalog.json", funding_catalog.model_dump(mode="json")
            )
            write_json(folder / "funding-manifest.json", funding_manifest)
            shutil.copyfile(funding_snapshot / "embrapa.pdf", folder / "embrapa-funding.pdf")
        if location_catalog:
            write_json(
                folder / "institution_location_catalog.json",
                location_catalog.model_dump(mode="json"),
            )
            write_json(folder / "locations-manifest.json", location_manifest)
            for key in location_manifest:
                shutil.copyfile(affiliation_snapshot / f"{key}.html", folder / f"{key}.html")
        if orcid_catalog:
            write_json(
                folder / "articlemeta_orcid_catalog.json", orcid_catalog.model_dump(mode="json")
            )
            shutil.copyfile(
                orcid_snapshot / "persons-manifest.json", folder / "persons-manifest.json"
            )
        if date_catalog:
            write_json(
                folder / "articlemeta_date_catalog.json", date_catalog.model_dump(mode="json")
            )
            shutil.copyfile(articlemeta_snapshot / "articlemeta.json", folder / "articlemeta.json")
            shutil.copyfile(
                articlemeta_snapshot / "manifest.json", folder / "articlemeta-manifest.json"
            )
        scope = {
            "organization_id": str(uuid5(NAMESPACE_URL, "idml:vh1:socket:LAB_ONLY")),
            "resource_id": str(uuid5(NAMESPACE_URL, "idml:vh1:socket:LAB_ONLY:" + case)),
            "source_idml_sha256": sha(data),
            "journal_profile_id": profile.profile_id,
            "xml_sha256": sha(files[0].data),
            "package_sha256": package.package_sha256,
        }
        incoming = folder / "incoming"
        incoming.mkdir()
        doi = json.loads((vault / case / "authority/manifest.json").read_bytes())
        doi.update(candidate_sha256=scope["xml_sha256"], package_sha256=scope["package_sha256"])
        write_json(incoming / "doi-manifest.json", doi)
        shutil.copyfile(vault / case / "authority/crossref.json", incoming / "crossref.json")
        editorial = ROOT / "benchmarks/private/output/vh1-editorial/20261001T214623Z" / case
        context = json.loads((editorial / "manifest.json").read_bytes())
        context["candidate_sha256"] = scope["xml_sha256"]
        for path in editorial.glob("*.json"):
            if path.name != "manifest.json":
                shutil.copyfile(path, incoming / path.name)
        if orcid_catalog:
            for identifier, entry in person_manifest.items():
                context["sources"][identifier] = entry
                shutil.copyfile(
                    orcid_snapshot / f"{identifier}.json", incoming / f"{identifier}.json"
                )
        write_json(incoming / "editorial-manifest.json", context)
        grant_id = str(uuid5(NAMESPACE_URL, "idml:vh1:metadata:LAB_ONLY:" + run_id + case))
        bundle = {
            "version": "validation-authority-bundle-1.0",
            "authorization_id": grant_id,
            "scope": scope,
            "files": {p.name: sha(p.read_bytes()) for p in incoming.iterdir()},
        }
        write_json(incoming / "manifest.json", bundle)
        grant = {
            "version": "validation-authority-grant-1.0",
            "authorization_id": grant_id,
            "scope": scope,
            "bundle_sha256": sha((incoming / "manifest.json").read_bytes()),
            "status": "active",
            "destination": "vps",
            "decision_id": str(uuid5(NAMESPACE_URL, "idml:vh1:owner-storage-decision:20261001")),
            "decision_sha256": sha(
                (ROOT / "docs/authorizations/VH1_VPS_DATA_20261001.md").read_bytes()
            ),
            "issued_at": now.isoformat(),
            "expires_at": (now + timedelta(days=1)).isoformat(),
        }
        write_json(folder / "grant.json", grant)
        write_json(folder / "scope.json", scope)
        plan["cases"][case] = {
            "before_xml_sha256": sha(before),
            "before_package_sha256": PACKAGES[case],
            "xml_sha256": scope["xml_sha256"],
            "package_sha256": package.package_sha256,
            "scope_sha256": scope_digest(scope),
            "delta": delta,
            "offline_valid": True,
            "deterministic": True,
            "funding_structure_review_required": funding_review,
            "verified_funding": {
                "applied": funding_catalog is not None,
                "catalog_id": funding_catalog.catalog_id if funding_catalog else None,
                "source": funding_manifest,
                "human_review_required": True,
                "other_funders_preserved_in_statement": funding_catalog is not None,
            },
            "articlemeta_dates": {
                "applied": date_catalog is not None,
                "catalog_id": date_catalog.catalog_id if date_catalog else None,
                "snapshot_sha256": date_catalog.response_sha256 if date_catalog else None,
                "source_idml_sha256": sha(data),
                "retrieved_at": snapshot_manifest["retrieved_at"] if snapshot_manifest else None,
                "human_review_required": True,
            },
            "articlemeta_orcids": {
                "applied": orcid_catalog is not None,
                "catalog_id": orcid_catalog.catalog_id if orcid_catalog else None,
                "evidence_sha256": orcid_catalog.evidence_sha256 if orcid_catalog else None,
                "persons": person_manifest or {},
                "human_review_required": True,
                "authenticated_ownership_claimed": False,
            },
            "catalog_sha256": {
                kind: sha((base / (kind + ".json")).read_bytes())
                for kind in options
                if kind
                not in {
                    "articlemeta_date_catalog",
                    "articlemeta_orcid_catalog",
                    "institution_location_catalog",
                    "verified_funding_catalog",
                }
            },
            "institution_locations": {
                "applied": location_catalog is not None,
                "catalog_id": location_catalog.catalog_id if location_catalog else None,
                "evidence_sha256": location_catalog.evidence_sha256 if location_catalog else None,
                "sources": location_manifest,
                "human_review_required": True,
            },
            "files": {
                p.relative_to(folder).as_posix(): sha(p.read_bytes())
                for p in folder.rglob("*")
                if p.is_file()
            },
        }
    write_json(output / "plan.json", plan)
    print(
        json.dumps(
            {
                "output": str(output),
                "plan_sha256": sha((output / "plan.json").read_bytes()),
                "cases": {k: v["delta"] for k, v in plan["cases"].items()},
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--articlemeta-snapshot", type=Path)
    parser.add_argument("--orcid-snapshot", type=Path)
    parser.add_argument("--affiliation-snapshot", type=Path)
    parser.add_argument("--funding-snapshot", type=Path)
    args = parser.parse_args()
    main(
        args.articlemeta_snapshot,
        args.orcid_snapshot,
        args.affiliation_snapshot,
        args.funding_snapshot,
    )
