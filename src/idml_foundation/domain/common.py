import hashlib
import json
from enum import StrEnum
from typing import Any, Self
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, model_validator

DOMAIN_NAMESPACE = UUID("295d003e-0285-5e43-b33c-d6d2a6bf7051")
SHA256_PATTERN = r"^[0-9a-f]{64}$"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceKind(StrEnum):
    IDML = "idml"
    PDF = "pdf"
    APPROVED_XML = "approved_xml"
    ASSET = "asset"
    HUMAN = "human"
    SYSTEM = "system"


class BoundingBox(StrictModel):
    x: float
    y: float
    width: float = Field(ge=0)
    height: float = Field(ge=0)


class EvidenceLocator(StrictModel):
    artifact_sha256: str = Field(pattern=SHA256_PATTERN)
    logical_path: str = Field(min_length=1, max_length=500)
    element_id: str | None = Field(default=None, max_length=200)
    page_index: int | None = Field(default=None, ge=0)
    box: BoundingBox | None = None
    start_offset: int | None = Field(default=None, ge=0)
    end_offset: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def offsets_are_ordered(self) -> Self:
        if self.end_offset is not None and self.start_offset is None:
            raise ValueError("end_offset requires start_offset")
        if (
            self.start_offset is not None
            and self.end_offset is not None
            and self.end_offset < self.start_offset
        ):
            raise ValueError("end_offset must be greater than or equal to start_offset")
        return self


class Evidence(StrictModel):
    id: str = Field(min_length=1, max_length=120)
    source_kind: SourceKind
    locator: EvidenceLocator
    content_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    description: str = Field(min_length=1, max_length=500)


def stable_id(article_key: str, kind: str, source_locator: str) -> str:
    """Generate an ID stable across retries and model serialization cycles."""
    normalized = "\x1f".join(part.strip() for part in (article_key, kind, source_locator))
    return f"{kind}-{uuid5(DOMAIN_NAMESPACE, normalized)}"


def canonical_bytes(value: BaseModel | dict[str, Any]) -> bytes:
    payload = (
        value.model_dump(mode="json", exclude_none=False) if isinstance(value, BaseModel) else value
    )
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def content_digest(value: BaseModel | dict[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()
