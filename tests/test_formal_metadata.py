from __future__ import annotations

import hashlib
import json

import pytest
from lxml import etree

from idml_foundation.domain.canonical import FieldState, SourcedText
from idml_foundation.pipeline.jats_builder import JatsBuilder
from idml_foundation.release.formal_metadata import (
    FormalMetadataAuthorityCatalog,
    build_formal_metadata_authority_catalog,
)
from tests.domain_helpers import canonical_article


def _response() -> bytes:
    return json.dumps(
        {
            "status": "ok",
            "message": {
                "DOI": "10.1/example",
                "published": {"date-parts": [[2025]]},
                "published-online": {"date-parts": [[2025]]},
                "issued": {"date-parts": [[2025]]},
                "volume": "30",
                "license": [
                    {"URL": "http://creativecommons.org/licenses/by/4.0/"},
                    {"URL": "http://creativecommons.org/licenses/by/4.0/"},
                ],
            },
        }
    ).encode()


def test_formal_metadata_authority_is_content_addressed_and_applies() -> None:
    article = canonical_article()
    article = article.model_copy(
        update={
            "front": article.front.model_copy(
                update={
                    "publication_date": SourcedText(
                        state=FieldState.MISSING,
                        transformation="not-in-source",
                        confidence=1.0,
                    ),
                    "volume": None,
                    "license_url": None,
                }
            )
        }
    )
    response = _response()
    catalog, report = build_formal_metadata_authority_catalog(
        article=article,
        source_idml_sha256="a" * 64,
        crossref_response=response,
        corpus_id="test-corpus",
    )
    enriched = catalog.apply(article, source_idml_sha256="a" * 64)

    assert enriched.front.publication_date.value == "2025"
    assert enriched.front.volume and enriched.front.volume.value == "30"
    assert enriched.front.license_url
    assert enriched.front.license_url.value == "https://creativecommons.org/licenses/by/4.0/"
    assert report["crossref_response_sha256"] == hashlib.sha256(response).hexdigest()
    assert report["restricted_content_emitted"] is False


def test_formal_metadata_authority_rejects_catalog_tampering() -> None:
    article = canonical_article()
    catalog, _ = build_formal_metadata_authority_catalog(
        article=article,
        source_idml_sha256="a" * 64,
        crossref_response=_response(),
        corpus_id="test-corpus",
    )
    payload = catalog.model_dump(mode="json")
    payload["volume"] = "31"

    with pytest.raises(ValueError, match="catalog ID mismatch"):
        FormalMetadataAuthorityCatalog.model_validate(payload)


def test_year_only_authority_emits_publication_and_collection_without_invented_day() -> None:
    article = canonical_article()
    article = article.model_copy(
        update={
            "front": article.front.model_copy(
                update={
                    "publication_date": SourcedText(state=FieldState.MISSING),
                }
            )
        }
    )
    catalog, _ = build_formal_metadata_authority_catalog(
        article=article,
        source_idml_sha256="a" * 64,
        crossref_response=_response(),
        corpus_id="test-corpus",
    )
    enriched = catalog.apply(article, source_idml_sha256="a" * 64)
    xml = etree.fromstring(JatsBuilder().build(enriched))
    dates = xml.findall("./front/article-meta/pub-date")
    assert {d.get("date-type") for d in dates} == {"pub", "collection"}
    assert all(d.findtext("year") == "2025" for d in dates)
    assert all(d.find("day") is None and d.find("month") is None for d in dates)
