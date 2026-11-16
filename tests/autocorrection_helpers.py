"""Synthetic IDML bytes + operator fixture. No private article or actual consent."""

import hashlib
from io import BytesIO
from pathlib import Path
from uuid import UUID
from zipfile import ZIP_STORED, ZipFile

from idml_foundation.domain.canonical import CanonicalArticle
from idml_foundation.domain.common import content_digest
from idml_foundation.ingest.scanner import ScanResult
from idml_foundation.models import Organization, Resource
from idml_foundation.pipeline.validation import OfflineJatsValidator
from idml_foundation.services.artifacts import store_idml_artifact, store_supporting_artifact
from idml_foundation.services.autocorrection_executor import register_extraction_grant
from idml_foundation.services.autocorrection_sources import ExtractionGrant
from idml_foundation.services.snapshots import store_snapshot
from tests.test_autocorrection_policy import sample


class SyntheticCleanScanner:
    def scan(self, data):
        return ScanResult(clean=True, status="clamav_clean")


def source_data():
    data = sample()
    member = (
        b'<Story Self="story"><ParagraphStyleRange Self="country">'
        b"<CharacterStyleRange><Content>Brazil</Content></CharacterStyleRange>"
        b'</ParagraphStyleRange><ParagraphStyleRange Self="affiliation">'
        b"<CharacterStyleRange><Content>Example University, City, Brazil</Content>"
        b"</CharacterStyleRange></ParagraphStyleRange>"
        b'<Link Self="link" LinkResourceURI="article-gf01.jpg"/></Story>'
    )
    archive = BytesIO()
    with ZipFile(archive, "w", compression=ZIP_STORED) as output:
        output.writestr("mimetype", b"application/vnd.adobe.indesign-idml-package")
        output.writestr("designmap.xml", b"<Document/>")
        output.writestr("Stories/Story_u1.xml", member)
    data["idml"] = archive.getvalue()
    data["asset"] = b"\xff\xd8\xffsynthetic-image-bytes-not-an-actual-image"
    raw = data["article"].model_dump(mode="json")
    digest = hashlib.sha256(data["idml"]).hexdigest()
    raw["assets"][0]["sha256"] = hashlib.sha256(data["asset"]).hexdigest()
    for index, element_id in enumerate(("country", "link", "affiliation")):
        raw["evidence"][index + 1]["locator"].update(artifact_sha256=digest, element_id=element_id)
    data["article"] = CanonicalArticle.model_validate(raw)
    scope = data["context"].scope.model_copy(
        update={
            "source_idml_sha256": digest,
            "snapshot_sha256": content_digest(data["article"]),
        }
    )
    data["intent"] = data["intent"].model_copy(update={"scope": scope})
    data["context"] = data["context"].model_copy(update={"scope": scope})
    data["grants"] = tuple(
        ExtractionGrant(
            authorization_id=e.authorization_id,
            decision_sha256=e.authorization_decision_sha256,
            scope=scope,
            operation=op.operation,
            subject_id=op.subject_id,
            evidence_id=op.evidence_id,
            locator=data["article"].evidence[index + 1].locator,
            source_text_sha256=e.source_text_sha256,
            collected_at=e.collected_at,
            issued_at=e.issued_at,
            expires_at=e.expires_at,
        )
        for index, (op, e) in enumerate(
            zip(data["intent"].operations, data["evidence"], strict=True)
        )
    )
    return data


def persisted_data(db, settings):
    data = source_data()
    scope = data["context"].scope
    db.add(Organization(id=str(scope.organization_id), slug="automation-test", name="Synthetic"))
    db.flush()
    db.add(
        Resource(
            id=str(scope.resource_id), organization_id=str(scope.organization_id), title="Test"
        )
    )
    db.flush()
    source, _ = store_idml_artifact(
        db,
        organization_id=str(scope.organization_id),
        original_name="source.idml",
        data=data["idml"],
        settings=settings,
        scanner=SyntheticCleanScanner(),
    )
    store_supporting_artifact(
        db,
        organization_id=str(scope.organization_id),
        original_name="article-gf01.jpg",
        data=data["asset"],
        settings=settings,
        scanner=SyntheticCleanScanner(),
    )
    snapshot, _ = store_snapshot(
        db,
        organization_id=str(scope.organization_id),
        resource_id=str(scope.resource_id),
        document=data["article"],
        revision=1,
        source_artifact_id=source.id,
    )
    scope = scope.model_copy(update={"snapshot_id": UUID(snapshot.id)})
    data["context"] = data["context"].model_copy(update={"scope": scope})
    data["intent"] = data["intent"].model_copy(update={"scope": scope})
    data["grants"] = tuple(g.model_copy(update={"scope": scope}) for g in data["grants"])
    for grant in data["grants"]:
        register_extraction_grant(db, organization_id=str(scope.organization_id), grant=grant)
    db.commit()
    data["snapshot"] = snapshot
    data["settings"] = settings
    data["validator"] = OfflineJatsValidator(Path("vendor/jats/1.3"))
    return data


def stage_kwargs(data):
    return {
        key: data[key] for key in ("intent", "context", "profile", "settings", "validator", "now")
    } | {
        "organization_id": str(data["context"].scope.organization_id),
    }
