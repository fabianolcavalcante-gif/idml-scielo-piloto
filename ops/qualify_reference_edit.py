"""Build the isolated e20240086 edit case from the supplied publication renditions."""

import hashlib
import json
import re
from datetime import timedelta
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from idml_foundation.database import Base
from idml_foundation.domain.canonical import CanonicalArticle, FieldState
from idml_foundation.domain.common import content_digest
from idml_foundation.ingest.scanner import build_scanner
from idml_foundation.models import Organization, Resource, utcnow
from idml_foundation.pipeline.autocorrection_evidence import qualify_fields
from idml_foundation.pipeline.jats_builder import JatsBuilder
from idml_foundation.pipeline.profile import load_profile
from idml_foundation.pipeline.validation import OfflineJatsValidator
from idml_foundation.release.package_builder import AssetPayload, PackageBuilder
from idml_foundation.services.artifacts import store_idml_artifact, store_supporting_artifact
from idml_foundation.services.autocorrection_authorization import RevisionEditAuthorization
from idml_foundation.services.jobs import create_job
from idml_foundation.services.snapshots import store_snapshot
from idml_foundation.services.xpm_query_targets import parse_candidate
from idml_foundation.worker import process_job
from ops.qualify_edit_cycle import config, save
from ops.qualify_source_access_http import authorize


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def prepared(root, inputs, reference, scanner):
    settings = config(root)
    profile = load_profile(settings.journal_profile_path)
    manifest = json.loads(Path("corpus/manifests/esa-e20240086.json").read_bytes())

    def verified(role):
        (row,) = [r for r in manifest["artifacts"] if r["role"] == role]
        name = Path(row["logical_path"]).name
        raw = (inputs / name).read_bytes()
        if sha(raw) != row["sha256"]:
            raise ValueError("reference_hash_mismatch")
        return name, raw

    source, idml = verified("source_idml")
    _, published_xml = verified("approved_xml_reference")
    pdf_name, pdf = verified("approved_pdf_reference")
    scope = json.loads((reference / "scope.json").read_bytes())
    assert scope["source_idml_sha256"] == sha(idml)
    prior = (reference / "candidate.zip").read_bytes()
    assert (
        sha(prior)
        == scope["package_sha256"]
        == "7c0d7052ff7c84d15cb077d2b7cbf736f5045ee167cb7902f2a63d331da4b07f"
    )
    article = CanonicalArticle.model_validate_json((inputs / "canonical.json").read_bytes())
    builder = JatsBuilder(sps_version=profile.sps_version)
    complete = builder.build(article)
    full = parse_candidate(complete)
    gold = parse_candidate(published_xml)
    doi_path = "front/article-meta/article-id[@pub-id-type='doi']"
    assert full.findtext(doi_path) and full.findtext(doi_path) == gold.findtext(doi_path)
    href = "{http://www.w3.org/1999/xlink}href"
    published = [g.get(href) for g in gold.iter() if g.tag in ("graphic", "inline-graphic")]
    logical = [g.get(href) for g in full.iter() if g.tag in ("graphic", "inline-graphic")]
    assert len(set(logical)) == len(set(published)) == len(logical) == len(published) == 5
    assets = []
    selected = []
    bindings = []
    from io import BytesIO

    with ZipFile(BytesIO(prior)) as archive:
        stem = profile.package_stem(article.article_id)
        assert (
            sha(archive.read(stem + ".xml")) == scope["xml_sha256"]
            and archive.read(stem + ".pdf") == pdf
        )
        for i, (name, published_name) in enumerate(zip(logical, published, strict=True), 1):
            assert (
                re.fullmatch(rf"Figure{i}\.jpg", name) and published_name == f"{stem}-gf{i:02}.jpg"
            )
            (row,) = [
                r
                for r in manifest["artifacts"]
                if r["role"] == "figure_asset" and Path(r["logical_path"]).name == published_name
            ]
            raw = (inputs / published_name).read_bytes()
            assert raw == archive.read(published_name) and sha(raw) == row["sha256"]
            (asset,) = [a for a in article.assets if a.logical_name == name]
            selected.append(
                asset.model_copy(update=dict(sha256=sha(raw), state=FieldState.PRESENT))
            )
            assets.append(AssetPayload(source_name=name, data=raw, media_type="image/jpeg"))
            bindings.append(
                dict(xml_reference=published_name, canonical_reference=name, sha256=sha(raw))
            )
    mapped = {a.id: a for a in selected}
    working = article.model_copy(
        update={"assets": tuple(mapped.get(a.id, a) for a in article.assets)}
    )
    assert builder.build(working) == complete

    def package(xml):
        b = PackageBuilder()
        files = b.scielo_files(package_stem=stem, xml=xml, pdf=pdf, assets=tuple(assets))
        packaged = next(f.data for f in files if f.role.value == "xml")
        report = OfflineJatsValidator(Path("vendor/jats/1.3")).validate(
            packaged, asset_names=set(published)
        )
        assert report.valid
        built = b.build(
            article_id=working.article_id,
            profile_id=profile.profile_id,
            source_idml_sha256=sha(idml),
            files=files,
            validator_versions={"offline": report.validator_profile},
        )
        return built.package_sha256, sha(packaged)

    assert package(complete) == (scope["package_sha256"], scope["xml_sha256"])
    masked = working.model_dump(mode="json")
    (target,) = [
        aff
        for aff in masked["front"]["affiliations"]
        if aff["institution"]["value"] == "University of Tokyo"
    ]
    literal = target["original_text"]["value"]
    assert literal in [n.text for n in gold.findall(".//aff/institution[@content-type='original']")]
    target["original_text"] = None
    qualified = qualify_fields(
        CanonicalArticle.model_validate(masked), idml=idml, profile=profile, settings=settings
    )
    (binding,) = qualified.catalog.bindings
    assert (
        binding.operation == "affiliation-original-literal" and binding.subject_id == target["id"]
    )
    masked_zip, masked_xml = package(builder.build(qualified.article))
    assert masked_zip != scope["package_sha256"]
    engine = create_engine(settings.database_url)
    try:
        Base.metadata.create_all(engine)
        factory = sessionmaker(engine, expire_on_commit=False)
        with factory() as db:
            org = Organization(slug="reference", name="Isolated reference")
            db.add(org)
            db.flush()
            resource = Resource(organization_id=org.id, title="Isolated reference")
            db.add(resource)
            db.flush()
            kwargs = dict(organization_id=org.id, scanner=scanner, settings=settings)
            art, _ = store_idml_artifact(db, original_name=source, data=idml, **kwargs)
            pdf_record = store_supporting_artifact(db, original_name=pdf_name, data=pdf, **kwargs)
            for payload in assets:
                uploaded = store_supporting_artifact(
                    db, original_name=payload.source_name, data=payload.data, **kwargs
                )
                assert uploaded.scanner_status == "clamav_clean"
            assert art.scanner_status == pdf_record.scanner_status == "clamav_clean"
            snapshot, _ = store_snapshot(
                db,
                organization_id=org.id,
                resource_id=resource.id,
                source_artifact_id=art.id,
                revision=1,
                document=qualified.article,
            )
            now = utcnow()
            decision = RevisionEditAuthorization(
                authorization_id=uuid4(),
                organization_id=org.id,
                resource_id=resource.id,
                snapshot_id=snapshot.id,
                review_version=resource.version,
                source_idml_sha256=art.sha256,
                canonical_sha256=snapshot.content_sha256,
                catalog_sha256=content_digest(qualified.catalog),
                decision_sha256=content_digest(
                    {"qualification": "published-renditions", "scope": scope, "field": target["id"]}
                ),
                destination="vps",
                status="active",
                collected_at=now,
                issued_at=now,
                expires_at=now + timedelta(hours=1),
            )
            directory = root / "decisions" / "autocorrection-authorizations"
            directory.mkdir(parents=True)
            (directory / f"{decision.authorization_id}.json").write_text(decision.model_dump_json())
            payload = dict(
                resource_id=resource.id,
                canonical_snapshot_id=snapshot.id,
                review_version=resource.version,
                authorization_id=str(decision.authorization_id),
            )
            job, _ = create_job(
                db,
                organization_id=org.id,
                kind="autocorrection.preflight",
                payload=payload,
                idempotency_key=uuid4().hex,
                correlation_id=uuid4().hex,
                actor_id="qualification",
            )
            db.commit()
            process_job(job.id, factory, settings=settings)
            db.refresh(job)
            assert (
                job.state == "succeeded"
                and job.result["state"] == "staged"
                and job.result["offline_valid"]
            )
            assert job.result["xml_sha256"] == sha(complete)
            evidence = dict(
                article="esa-e20240086",
                source_sha256=art.sha256,
                authorized_literal_sha256=sha(literal.encode()),
                expected_candidate_xml_sha256=sha(complete),
                package_sha256=scope["package_sha256"],
                package_xml_sha256=scope["xml_sha256"],
                masked_package_sha256=masked_zip,
                bindings=bindings,
                original_link_bytes_verified=False,
            )
            save(
                root / "case.json",
                dict(
                    job_id=job.id,
                    pdf_id=pdf_record.id,
                    synthetic=False,
                    published_reference=evidence,
                    baseline={"cases": [{"xml_input_sha256": masked_xml}]},
                ),
            )
        authorize(factory, settings, dict(resource_id=resource.id, organization_id=org.id))
    finally:
        engine.dispose()


if __name__ == "__main__":
    root = Path("/case")
    prepared(root, Path("/inputs"), Path("/reference"), build_scanner(config(root)))
