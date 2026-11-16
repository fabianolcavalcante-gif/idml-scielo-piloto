"""Versioned, IDML/XML-independent article domain models."""

from idml_foundation.domain.canonical import CANONICAL_SCHEMA_VERSION, CanonicalArticle
from idml_foundation.domain.common import canonical_bytes, content_digest, stable_id
from idml_foundation.domain.raw import RAW_SCHEMA_VERSION, RawArticle

__all__ = [
    "CANONICAL_SCHEMA_VERSION",
    "RAW_SCHEMA_VERSION",
    "CanonicalArticle",
    "RawArticle",
    "canonical_bytes",
    "content_digest",
    "stable_id",
]
