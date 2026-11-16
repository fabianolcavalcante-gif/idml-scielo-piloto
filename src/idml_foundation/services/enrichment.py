"""Load operator-provisioned catalogs, scoped to tenant/resource/source, never user paths."""

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from idml_foundation.ai.formula_catalog import FormulaTranscriptionCatalog
from idml_foundation.domain.common import SHA256_PATTERN, StrictModel
from idml_foundation.pipeline.profile import load_profile
from idml_foundation.pipeline.service import DeterministicPipeline
from idml_foundation.release.articlemeta_dates import ArticleMetaDateCatalog
from idml_foundation.release.articlemeta_orcids import ArticleMetaOrcidCatalog
from idml_foundation.release.crossref_authority import CrossrefMetadataAuthorityCatalog
from idml_foundation.release.editorial_enrichment import EditorialEnrichmentCatalog
from idml_foundation.release.formal_metadata import FormalMetadataAuthorityCatalog
from idml_foundation.release.institution_locations import InstitutionLocationCatalog
from idml_foundation.release.journal_metadata import JournalMetadataCatalog
from idml_foundation.release.reference_types import ReferenceTypeCatalog
from idml_foundation.release.verified_funding import VerifiedFundingCatalog
from idml_foundation.services.source_authorization import SourceAuthorization
from idml_foundation.settings import Settings

Catalog = (
    FormulaTranscriptionCatalog
    | CrossrefMetadataAuthorityCatalog
    | FormalMetadataAuthorityCatalog
    | EditorialEnrichmentCatalog
    | ArticleMetaDateCatalog
    | ArticleMetaOrcidCatalog
    | InstitutionLocationCatalog
    | VerifiedFundingCatalog
    | ReferenceTypeCatalog
    | JournalMetadataCatalog
)

KINDS: dict[str, type[Catalog]] = {
    "formula_catalog": FormulaTranscriptionCatalog,
    "crossref_metadata_catalog": CrossrefMetadataAuthorityCatalog,
    "formal_metadata_catalog": FormalMetadataAuthorityCatalog,
    "editorial_enrichment_catalog": EditorialEnrichmentCatalog,
    "articlemeta_date_catalog": ArticleMetaDateCatalog,
    "articlemeta_orcid_catalog": ArticleMetaOrcidCatalog,
    "institution_location_catalog": InstitutionLocationCatalog,
    "verified_funding_catalog": VerifiedFundingCatalog,
    "reference_type_catalog": ReferenceTypeCatalog,
    "journal_metadata_catalog": JournalMetadataCatalog,
}


def bundle_path(organization_id: str, resource_id: str, source_sha256: str) -> Path:
    scope = f"{organization_id}:{resource_id}:{source_sha256}"
    return Path(hashlib.sha256(scope.encode("ascii")).hexdigest())


class CatalogBundle(StrictModel):
    version: Literal["enrichment-bundle-1.1"]
    authorization_id: UUID
    organization_id: str
    resource_id: str
    source_idml_sha256: str = Field(pattern=SHA256_PATTERN)
    profile_id: str
    catalogs: dict[str, str] = Field(min_length=1, max_length=10)


def _read(root: Path, relative: Path, limit: int) -> bytes:
    path = root
    for part in relative.parts:
        path = path / part
        if (
            path.is_symlink()
            or path.is_junction()
            or not path.resolve().is_relative_to(root.resolve())
        ):
            raise ValueError("unsafe enrichment path")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if not data or len(data) > limit:
        raise ValueError("enrichment size budget")
    return data


@dataclass
class EnrichmentSelection:
    catalogs: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=lambda: {"status": "not_configured"})

    def pipeline(self, settings: Settings) -> DeterministicPipeline:
        return DeterministicPipeline(
            settings=settings, profile=load_profile(settings.journal_profile_path), **self.catalogs
        )


def select_enrichment(
    settings: Settings,
    *,
    organization_id: str,
    resource_id: str,
    source_sha256: str,
    profile_id: str,
) -> EnrichmentSelection:
    if settings.enrichment_root is None:
        return EnrichmentSelection()
    try:
        for value in (organization_id, resource_id):
            if str(UUID(value)) != value:
                raise ValueError("noncanonical identifier")
        if not re.fullmatch(SHA256_PATTERN, source_sha256):
            raise ValueError("invalid source hash")
        root = settings.enrichment_root
        if settings.enrichment_location is None or not root.is_dir():
            raise ValueError("configured enrichment root unavailable")
        if any(p.is_symlink() or p.is_junction() for p in (root, *root.absolute().parents)):
            raise ValueError("unsafe enrichment root")
        relative = bundle_path(organization_id, resource_id, source_sha256)
        parent = root
        for part in relative.parts:
            parent = parent / part
            if (
                parent.is_symlink()
                or parent.is_junction()
                or not parent.resolve().is_relative_to(root.resolve())
            ):
                raise ValueError("unsafe enrichment scope")
        # A configured article bundle must be complete; only an absent article has no match.
        directory = root / relative
        if not directory.exists() and not directory.is_symlink():
            return EnrichmentSelection(provenance={"status": "no_matching_bundle"})
        raw_manifest = _read(root, relative / "manifest.json", 16 * 1024)
        manifest = CatalogBundle.model_validate_json(raw_manifest)
        if (
            manifest.organization_id,
            manifest.resource_id,
            manifest.source_idml_sha256,
            manifest.profile_id,
        ) != (organization_id, resource_id, source_sha256, profile_id):
            raise ValueError("bundle scope mismatch")
        raw_authorization = _read(
            root, Path("authorizations") / f"{manifest.authorization_id}.json", 16 * 1024
        )
        authorization = SourceAuthorization.model_validate_json(raw_authorization)
        authorization.check(
            authorization_id=manifest.authorization_id,
            organization_id=organization_id,
            resource_id=resource_id,
            source_sha256=source_sha256,
            profile_id=profile_id,
            destination=settings.enrichment_location,
            catalog_hashes=manifest.catalogs,
        )
        catalogs = {}
        for kind, expected_hash in manifest.catalogs.items():
            if kind not in KINDS or not re.fullmatch(SHA256_PATTERN, expected_hash):
                raise ValueError("unsupported catalog")
            data = _read(root, relative / f"{kind}.json", 8 * 1024**2)
            if hashlib.sha256(data).hexdigest() != expected_hash:
                raise ValueError("catalog hash mismatch")
            catalog = KINDS[kind].model_validate_json(data)
            if isinstance(catalog, ReferenceTypeCatalog):
                permission = authorization.catalogs[kind]
                if (
                    permission.evidence_sha256 != catalog.evidence_sha256
                    or permission.collected_at != catalog.collected_at
                ):
                    raise ValueError("reference type evidence mismatch")
            if isinstance(catalog, InstitutionLocationCatalog):
                permission = authorization.catalogs[kind]
                if (
                    permission.evidence_sha256 != catalog.evidence_sha256
                    or permission.collected_at != catalog.collected_at
                    or any(s.collected_at > authorization.issued_at for s in catalog.snapshots)
                ):
                    raise ValueError("institution location evidence mismatch")
            if isinstance(catalog, ArticleMetaOrcidCatalog):
                permission = authorization.catalogs[kind]
                if (
                    permission.evidence_sha256 != catalog.evidence_sha256
                    or permission.collected_at != catalog.collected_at
                    or any(
                        ref.collected_at > authorization.issued_at
                        for ref in (catalog.articlemeta, *(a.person for a in catalog.additions))
                    )
                ):
                    raise ValueError("articlemeta orcid evidence mismatch")
            if isinstance(
                catalog, ArticleMetaDateCatalog | VerifiedFundingCatalog | JournalMetadataCatalog
            ):
                permission = authorization.catalogs[kind]
                if (
                    permission.evidence_sha256 != catalog.response_sha256
                    or permission.collected_at != catalog.collected_at
                ):
                    raise ValueError("articlemeta catalog evidence mismatch")
            if (
                catalog.source_idml_sha256 != source_sha256
                or catalog.journal_profile_id != profile_id
            ):
                raise ValueError("catalog scope mismatch")
            catalogs[kind] = catalog
        return EnrichmentSelection(
            catalogs=catalogs,
            provenance={
                "status": "selected",
                "manifest_sha256": hashlib.sha256(raw_manifest).hexdigest(),
                "catalog_sha256": manifest.catalogs,
                "source_idml_sha256": source_sha256,
                "profile_id": profile_id,
                "authorization_id": str(authorization.authorization_id),
                "authorization_sha256": hashlib.sha256(raw_authorization).hexdigest(),
                "authorization_expires_at": authorization.expires_at.isoformat(),
                "location": authorization.destination,
                "human_review_required": True,
            },
        )
    except (OSError, ValueError):
        # Pydantic errors may include private metadata; never propagate their detail to jobs/logs.
        raise ValueError("enrichment_bundle_invalid") from None
