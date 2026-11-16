from __future__ import annotations

import hashlib
import json

import pytest

from idml_foundation.release.crossref_authority import (
    build_crossref_metadata_authority_catalog,
)
from tests.domain_helpers import canonical_article, sourced


def _source_article():
    article = canonical_article()
    contributor = article.front.contributors[0]
    return article.model_copy(
        update={
            "front": article.front.model_copy(
                update={
                    "contributors": (
                        contributor.model_copy(
                            update={"orcid": sourced("https://orcid.org/0000-0002-1825-0097")}
                        ),
                    )
                }
            )
        }
    )


def _crossref_response() -> bytes:
    return json.dumps(
        {
            "status": "ok",
            "message": {
                "DOI": "10.1/example",
                "container-title": ["Journal Authority"],
                "alternative-id": ["S1234-56782026000100224"],
                "author": [
                    {
                        "ORCID": "https://orcid.org/0000-0002-1825-0097",
                        "given": "Ana Maria",
                        "family": "Silva Costa",
                    }
                ],
            },
        },
        separators=(",", ":"),
    ).encode()


def test_crossref_catalog_applies_names_identifier_and_journal_with_provenance() -> None:
    article = _source_article()
    response = _crossref_response()
    catalog, report = build_crossref_metadata_authority_catalog(
        article=article,
        source_idml_sha256="a" * 64,
        crossref_response=response,
        corpus_id="fixture-crossref",
    )

    enriched = catalog.apply(article, source_idml_sha256="a" * 64)
    contributor = enriched.front.contributors[0]

    assert contributor.name is not None
    assert contributor.name.given_names.value == "Ana Maria"
    assert contributor.name.surname.value == "Silva Costa"
    assert contributor.name.surname.transformation == "crossref-doi-authority"
    assert enriched.front.journal.title.value == "Journal Authority"
    assert [(item.kind, item.value.value) for item in enriched.front.article_identifiers] == [
        ("doi", "10.1/example"),
        ("other", "00224"),
    ]
    assert hashlib.sha256(response).hexdigest() == catalog.crossref_response_sha256
    assert report["restricted_content_emitted"] is False
    assert any(
        reason.startswith("crossref_metadata_authority_pending_human:")
        for reason in enriched.review_reasons
    )


def test_crossref_catalog_fails_closed_when_current_name_changes() -> None:
    article = _source_article()
    catalog, _ = build_crossref_metadata_authority_catalog(
        article=article,
        source_idml_sha256="a" * 64,
        crossref_response=_crossref_response(),
        corpus_id="fixture-crossref",
    )
    contributor = article.front.contributors[0]
    assert contributor.name is not None
    changed = article.model_copy(
        update={
            "front": article.front.model_copy(
                update={
                    "contributors": (
                        contributor.model_copy(
                            update={
                                "name": contributor.name.model_copy(
                                    update={
                                        "surname": contributor.name.surname.model_copy(
                                            update={"value": "Changed"}
                                        )
                                    }
                                )
                            }
                        ),
                    )
                }
            )
        }
    )

    with pytest.raises(ValueError, match="current name hash mismatch"):
        catalog.apply(changed, source_idml_sha256="a" * 64)
