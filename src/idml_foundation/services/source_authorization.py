"""Operator-issued, expiring grants; neither an uploaded catalog nor AI grants consent."""

from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field

from idml_foundation.domain.common import SHA256_PATTERN, StrictModel

Location = Literal["local", "vps"]
SOURCE_KINDS = {
    "formula_catalog": {"authorized_article"},
    "crossref_metadata_catalog": {"crossref_public_record"},
    "formal_metadata_catalog": {"authorized_article", "editorial_record"},
    "editorial_enrichment_catalog": {"authorized_article", "editorial_record"},
    "articlemeta_date_catalog": {"scielo_articlemeta_record"},
    "articlemeta_orcid_catalog": {"scielo_articlemeta_orcid_records"},
    "institution_location_catalog": {"institutional_location_records"},
    "verified_funding_catalog": {"institutional_funding_record"},
    "reference_type_catalog": {"institutional_bibliographic_records"},
    "journal_metadata_catalog": {"scielo_journal_registry"},
}


class SourcePermission(StrictModel):
    source: Literal[
        "authorized_article",
        "crossref_public_record",
        "editorial_record",
        "scielo_articlemeta_record",
        "scielo_articlemeta_orcid_records",
        "institutional_location_records",
        "institutional_funding_record",
        "institutional_bibliographic_records",
        "scielo_journal_registry",
    ]
    catalog_sha256: str = Field(pattern=SHA256_PATTERN)
    evidence_sha256: str = Field(pattern=SHA256_PATTERN)
    collected_at: AwareDatetime


class SourceAuthorization(StrictModel):
    version: Literal["source-authorization-1.0"]
    authorization_id: UUID
    organization_id: UUID
    resource_id: UUID
    source_idml_sha256: str = Field(pattern=SHA256_PATTERN)
    profile_id: str = Field(min_length=1, max_length=100)
    destination: Location
    status: Literal["active", "revoked"]
    # Identifier and hash of the owner's recorded decision, not a model confidence score.
    decision_id: UUID
    decision_sha256: str = Field(pattern=SHA256_PATTERN)
    issued_at: AwareDatetime
    expires_at: AwareDatetime
    catalogs: dict[str, SourcePermission] = Field(min_length=1, max_length=10)

    def check(
        self,
        *,
        authorization_id: UUID,
        organization_id: str,
        resource_id: str,
        source_sha256: str,
        profile_id: str,
        destination: Location,
        catalog_hashes: dict[str, str],
        now: datetime | None = None,
    ) -> None:
        instant = now or datetime.now(UTC)
        if instant.tzinfo is None:
            raise ValueError("source_authorization_invalid")
        expected = (
            authorization_id,
            organization_id,
            resource_id,
            source_sha256,
            profile_id,
            destination,
        )
        actual = (
            self.authorization_id,
            str(self.organization_id),
            str(self.resource_id),
            self.source_idml_sha256,
            self.profile_id,
            self.destination,
        )
        if actual != expected or self.status != "active":
            raise ValueError("source_authorization_invalid")
        if not self.issued_at <= instant < self.expires_at:
            raise ValueError("source_authorization_invalid")
        if self.expires_at - self.issued_at > timedelta(days=30):
            raise ValueError("source_authorization_invalid")
        if {kind: item.catalog_sha256 for kind, item in self.catalogs.items()} != catalog_hashes:
            raise ValueError("source_authorization_invalid")
        for kind, item in self.catalogs.items():
            if item.source not in SOURCE_KINDS.get(kind, set()):
                raise ValueError("source_authorization_invalid")
            # Public mutable records must be renewed; article evidence remains hash-bound.
            max_age = timedelta(
                days=7
                if item.source
                in {
                    "crossref_public_record",
                    "scielo_articlemeta_record",
                    "scielo_articlemeta_orcid_records",
                    "institutional_location_records",
                    "institutional_funding_record",
                    "institutional_bibliographic_records",
                    "scielo_journal_registry",
                }
                else 30
            )
            if not self.issued_at - max_age <= item.collected_at <= self.issued_at:
                raise ValueError("source_authorization_invalid")
            if instant - item.collected_at > max_age:
                raise ValueError("source_authorization_invalid")
