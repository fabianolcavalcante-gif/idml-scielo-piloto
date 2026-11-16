"""Missing author identifiers backed by an exact article roster and public ORCID records.

No fuzzy search, authorship edits, authenticated-ownership assertion, or network I/O.
"""

import hashlib
import json
import re
import unicodedata
from datetime import datetime
from typing import Any, Literal, Self

from pydantic import AwareDatetime, Field, model_validator

from idml_foundation.ai.security import payload_digest
from idml_foundation.domain.canonical import (
    CanonicalArticle,
    Contributor,
    SourcedText,
    _valid_orcid,
)
from idml_foundation.domain.common import (
    SHA256_PATTERN,
    Evidence,
    EvidenceLocator,
    SourceKind,
    StrictModel,
    stable_id,
)
from idml_foundation.release.articlemeta_dates import MAX_RESPONSE, _field, source_url

VERSION = "articlemeta-orcid-catalog-1.0"


def normalized_name(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def person_url(identifier: str) -> str:
    if not re.fullmatch(
        r"[0-9]{4}-[0-9]{4}-[0-9]{4}-[0-9]{3}[0-9X]", identifier
    ) or not _valid_orcid(identifier):
        raise ValueError("articlemeta_orcid_invalid")
    return f"https://pub.orcid.org/v3.0/{identifier}/person"


def public_name_matches(raw: bytes, identifier: str, name: str) -> bool:
    if not 0 < len(raw) <= 1024**2:
        raise ValueError("articlemeta_orcid_response_budget")
    record = json.loads(raw)
    if not isinstance(record, dict) or record.get("path") != f"/{identifier}/person":
        raise ValueError("articlemeta_orcid_record_mismatch")
    person = record.get("name")
    if not isinstance(person, dict) or person.get("visibility") != "public":
        return False
    values = {}
    for key in ("given-names", "family-name", "credit-name"):
        field = person.get(key)
        value = field.get("value") if isinstance(field, dict) else None
        values[key] = value.strip() if isinstance(value, str) else ""
    names = [values["credit-name"]]
    if values["given-names"]:
        names.append((values["given-names"] + " " + values["family-name"]).strip())
    return bool(name.strip()) and normalized_name(name) in {normalized_name(n) for n in names if n}


class SnapshotReference(StrictModel):
    sha256: str = Field(pattern=SHA256_PATTERN)
    collected_at: AwareDatetime


class OrcidAddition(StrictModel):
    contributor_id: str = Field(min_length=1, max_length=200)
    contributor_sha256: str = Field(pattern=SHA256_PATTERN)
    identifier: str
    articlemeta_index: int = Field(ge=0, le=999)
    person: SnapshotReference

    @model_validator(mode="after")
    def checksum(self) -> Self:
        person_url(self.identifier)
        return self


def contributor_digest(contributor: Contributor) -> str:
    return payload_digest(contributor.model_dump(mode="json", exclude={"orcid"}))


class ArticleMetaOrcidCatalog(StrictModel):
    version: Literal["articlemeta-orcid-catalog-1.0"]
    catalog_id: str = Field(pattern=SHA256_PATTERN)
    corpus_id: str = Field(min_length=3, max_length=100)
    journal_profile_id: str = Field(min_length=3, max_length=100)
    source_idml_sha256: str = Field(pattern=SHA256_PATTERN)
    doi: str = Field(min_length=7, max_length=200)
    pid: str
    articlemeta: SnapshotReference
    additions: tuple[OrcidAddition, ...] = Field(min_length=1, max_length=1000)
    human_review_required: Literal[True]

    @model_validator(mode="after")
    def complete(self) -> Self:
        source_url(self.pid)
        for field in ("contributor_id", "identifier", "articlemeta_index"):
            if len({getattr(a, field) for a in self.additions}) != len(self.additions):
                raise ValueError("articlemeta_orcid_duplicate")
        if self.catalog_id != payload_digest(self.model_dump(mode="json", exclude={"catalog_id"})):
            raise ValueError("articlemeta_orcid_catalog_digest")
        return self

    @property
    def collected_at(self) -> datetime:
        return min(self.articlemeta.collected_at, *(a.person.collected_at for a in self.additions))

    @property
    def evidence_sha256(self) -> str:
        return payload_digest(
            {
                "articlemeta": self.articlemeta.model_dump(mode="json"),
                "persons": {a.identifier: a.person.model_dump(mode="json") for a in self.additions},
            }
        )

    def apply(self, article: CanonicalArticle, *, source_idml_sha256: str) -> CanonicalArticle:
        dois = [
            i.value.value.casefold()
            for i in article.front.article_identifiers
            if i.kind == "doi" and i.value.value
        ]
        if (
            source_idml_sha256 != self.source_idml_sha256
            or article.journal_profile_id != self.journal_profile_id
            or dois != [self.doi.casefold()]
        ):
            raise ValueError("articlemeta_orcid_scope_mismatch")
        contributors = {c.id: c for c in article.front.contributors}
        evidence = []
        values = {}
        for entry in self.additions:
            target = contributors.get(entry.contributor_id)
            if (
                target is None
                or target.contributor_type != "person"
                or contributor_digest(target) != entry.contributor_sha256
            ):
                raise ValueError("articlemeta_orcid_contributor_changed")
            ids = []
            for kind, snapshot, url, locator in (
                (
                    "articlemeta",
                    self.articlemeta,
                    source_url(self.pid),
                    f"article/v10/{entry.articlemeta_index}/k",
                ),
                ("orcid", entry.person, person_url(entry.identifier), "name"),
            ):
                eid = stable_id(
                    article.article_id,
                    "evidence",
                    f"articlemeta-orcid:{self.catalog_id}:{entry.identifier}:{kind}",
                )
                ids.append(eid)
                evidence.append(
                    Evidence(
                        id=eid,
                        source_kind=SourceKind.SYSTEM,
                        locator=EvidenceLocator(
                            artifact_sha256=snapshot.sha256, logical_path=url + "#/" + locator
                        ),
                        content_sha256=sha(entry.identifier.encode()),
                        description="Editorial author association and public ORCID name; not OAuth",
                    )
                )
            values[target.id] = SourcedText(
                value=entry.identifier,
                state="present",
                evidence_ids=tuple(ids),
                confidence=1.0,
                transformation="articlemeta-author-and-public-orcid-record",
            )
        reason = f"articlemeta_orcids_pending_human:{self.catalog_id}"
        present = {e.id for e in article.evidence}
        if any(e.id in present for e in evidence):
            if (
                all(e in article.evidence for e in evidence)
                and all(contributors[k].orcid == v for k, v in values.items())
                and reason in article.review_reasons
            ):
                return article
            raise ValueError("articlemeta_orcid_partial_application")
        # Even an explicit missing/rejected field is a decision, not permission to replace it.
        if any(contributors[k].orcid is not None for k in values):
            raise ValueError("articlemeta_orcid_existing_decision")
        enriched = article.model_copy(
            update={
                "front": article.front.model_copy(
                    update={
                        "contributors": tuple(
                            c.model_copy(update={"orcid": values[c.id]}) if c.id in values else c
                            for c in article.front.contributors
                        )
                    }
                ),
                "evidence": (*article.evidence, *evidence),
                "review_reasons": (*article.review_reasons, reason),
            }
        )
        return CanonicalArticle.model_validate(enriched.model_dump(mode="json"))


def build_articlemeta_orcid_catalog(
    *,
    article: CanonicalArticle,
    source_idml_sha256: str,
    response: bytes,
    pid: str,
    collected_at: str,
    persons: dict[str, tuple[bytes, str]],
    corpus_id: str,
) -> ArticleMetaOrcidCatalog:
    source_url(pid)
    if not 0 < len(response) <= MAX_RESPONSE:
        raise ValueError("articlemeta_orcid_response_budget")
    record = json.loads(response)
    metadata = record.get("article") if isinstance(record, dict) else None
    if (
        not isinstance(metadata, dict)
        or not isinstance(record.get("doi"), str)
        or record.get("code") != pid
        or metadata.get("code") != pid
        or _field(metadata, "v880") != pid
        or record.get("collection") != "scl"
        or record["doi"].casefold() != _field(metadata, "v237").casefold()
    ):
        raise ValueError("articlemeta_orcid_record_identity")
    authors = metadata.get("v10")
    if not isinstance(authors, list) or len(authors) != len(article.front.contributors):
        raise ValueError("articlemeta_orcid_roster_mismatch")
    lookup = {}
    identifiers = set()
    for index, row in enumerate(authors):
        if not isinstance(row, dict) or any(
            not isinstance(row.get(k), str) or not row[k].strip() for k in ("n", "s", "k")
        ):
            raise ValueError("articlemeta_orcid_author_invalid")
        person_url(row["k"])
        key = (normalized_name(row["n"]), normalized_name(row["s"]))
        if key in lookup or row["k"] in identifiers:
            raise ValueError("articlemeta_orcid_duplicate")
        lookup[key] = (index, row["k"])
        identifiers.add(row["k"])
    if set(persons) != identifiers:
        raise ValueError("articlemeta_orcid_public_records_incomplete")
    additions = []
    seen = set()
    for c in article.front.contributors:
        if c.name is None or c.name.prefix or c.name.suffix:
            raise ValueError("articlemeta_orcid_name_unsupported")
        given, family = c.name.given_names.value, c.name.surname.value
        key = (normalized_name(given or ""), normalized_name(family or ""))
        if key not in lookup or key in seen:
            raise ValueError("articlemeta_orcid_author_mismatch")
        seen.add(key)
        index, identifier = lookup[key]
        raw, retrieved = persons[identifier]
        if not public_name_matches(raw, identifier, f"{given} {family}"):
            raise ValueError("articlemeta_orcid_public_name_unconfirmed")
        if c.orcid is not None:
            raise ValueError("articlemeta_orcid_existing_decision")
        additions.append(
            OrcidAddition(
                contributor_id=c.id,
                contributor_sha256=contributor_digest(c),
                identifier=identifier,
                articlemeta_index=index,
                person=SnapshotReference(sha256=sha(raw), collected_at=retrieved),
            )
        )
    body: dict[str, Any] = dict(
        version=VERSION,
        corpus_id=corpus_id,
        journal_profile_id=article.journal_profile_id,
        source_idml_sha256=source_idml_sha256,
        doi=record["doi"].casefold(),
        pid=pid,
        articlemeta=SnapshotReference(sha256=sha(response), collected_at=collected_at).model_dump(
            mode="json"
        ),
        additions=[a.model_dump(mode="json") for a in additions],
        human_review_required=True,
    )
    catalog = ArticleMetaOrcidCatalog.model_validate({**body, "catalog_id": payload_digest(body)})
    catalog.apply(article, source_idml_sha256=source_idml_sha256)
    return catalog
