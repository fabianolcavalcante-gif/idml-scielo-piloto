"""Live, content-free Gate G2 validation executed inside the API container."""

import secrets

from idml_foundation.database import session_scope
from idml_foundation.domain.canonical import (
    BackMatter,
    CanonicalArticle,
    FieldState,
    FrontMatter,
    JournalIdentity,
    SourcedText,
)
from idml_foundation.domain.common import Evidence, EvidenceLocator, SourceKind, content_digest
from idml_foundation.domain.metrics import QualityDecision, QualityMetrics, evaluate_quality
from idml_foundation.domain.raw import RawArticle, RawSpread, RawStory
from idml_foundation.models import Organization, Resource
from idml_foundation.services.snapshots import load_snapshot, store_snapshot

suffix = secrets.token_hex(6)
source_sha = "a" * 64
evidence = Evidence(
    id=f"evidence-{suffix}",
    source_kind=SourceKind.SYSTEM,
    locator=EvidenceLocator(
        artifact_sha256=source_sha,
        logical_path="synthetic/gate-g2.json",
    ),
    description="Content-free Gate G2 evidence",
)
raw = RawArticle(
    article_id=f"gate-article-{suffix}",
    source_artifact_sha256=source_sha,
    document_self_id=f"document-{suffix}",
    stories=(
        RawStory(
            id=f"story-{suffix}",
            source_self_id=f"source-story-{suffix}",
            evidence_ids=(evidence.id,),
        ),
    ),
    frames=(),
    spreads=(
        RawSpread(
            id=f"spread-{suffix}",
            source_self_id=f"source-spread-{suffix}",
            page_indices=(0,),
            evidence_ids=(evidence.id,),
        ),
    ),
    evidence=(evidence,),
)


def present(value: str) -> SourcedText:
    return SourcedText(
        value=value,
        state=FieldState.PRESENT,
        evidence_ids=(evidence.id,),
        confidence=1.0,
    )


canonical = CanonicalArticle(
    article_id=raw.article_id,
    journal_profile_id="esa-sps-1.10-v1",
    source_raw_sha256=content_digest(raw),
    front=FrontMatter(
        journal=JournalIdentity(title=present("Synthetic Gate Journal")),
        article_identifiers=(),
        article_category=present("research-article"),
        titles=(),
        contributors=(),
        affiliations=(),
        publication_date=present("2026-08-24"),
    ),
    body=(),
    back=BackMatter(),
    evidence=(evidence,),
)

with session_scope() as db:
    tenant = Organization(slug=f"gate-g2-{suffix}", name="Gate G2 Tenant")
    foreign_tenant = Organization(slug=f"gate-g2-foreign-{suffix}", name="Foreign Tenant")
    db.add_all([tenant, foreign_tenant])
    db.flush()
    resource = Resource(organization_id=tenant.id, title="Gate G2 synthetic article")
    db.add(resource)
    db.flush()

    raw_snapshot, raw_created = store_snapshot(
        db,
        organization_id=tenant.id,
        resource_id=resource.id,
        document=raw,
        revision=1,
    )
    duplicate, duplicate_created = store_snapshot(
        db,
        organization_id=tenant.id,
        resource_id=resource.id,
        document=raw,
        revision=2,
    )
    canonical_snapshot, canonical_created = store_snapshot(
        db,
        organization_id=tenant.id,
        resource_id=resource.id,
        document=canonical,
        revision=1,
    )
    assert raw_created and canonical_created
    assert not duplicate_created and duplicate.id == raw_snapshot.id
    assert load_snapshot(raw_snapshot) == raw
    assert load_snapshot(canonical_snapshot) == canonical

    try:
        store_snapshot(
            db,
            organization_id=foreign_tenant.id,
            resource_id=resource.id,
            document=raw,
            revision=1,
        )
    except ValueError:
        pass
    else:
        raise AssertionError("cross-tenant snapshot write was accepted")

metrics = QualityMetrics(
    text_fidelity=1,
    metadata_accuracy=1,
    author_accuracy=1,
    affiliation_accuracy=1,
    reference_accuracy=1,
    figure_accuracy=1,
    table_accuracy=1,
    cross_reference_accuracy=1,
)
assert evaluate_quality(metrics).decision == QualityDecision.PASS
print("domain_round_trip=raw,canonical")
print("snapshot_idempotency=pass")
print("snapshot_cross_tenant=blocked")
print("quality_policy=pass")
print("G2_LIVE_TESTS=PASS")
