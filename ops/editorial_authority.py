"""Bound public evidence for VH-04; never derive expected values from candidate XML.

Only the ESA regular/continuous issue model is qualified here. Native validators
remain responsible for comparing volume/issue/section. ORCID matching confirms
public record/name consistency, NOT authenticated ownership of an identifier.
"""

import copy
import hashlib
import json
import re
import unicodedata
from datetime import UTC, datetime, timedelta

from lxml import etree

ISSUE_URL = "https://articlemeta.scielo.org/api/v1/issue/?collection=scl&code=1413-415220250001"
PROFILE = "esa-aop-1.1.0"
MAX_SNAPSHOT = 1024**2
ORCID = re.compile(r"[0-9]{4}-[0-9]{4}-[0-9]{4}-[0-9]{3}[0-9X]")


def digest(value):
    return hashlib.sha256(value).hexdigest()


def parse_candidate(candidate):
    if not 0 < len(candidate) <= 100 * 1024**2:
        raise ValueError("editorial_candidate_budget")
    return etree.fromstring(
        candidate, etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
    )


def orcid_identifiers(tree):
    return sorted(set(tree.xpath('.//contrib-id[@contrib-id-type="orcid"]/text()')))


def valid_orcid(value):
    if not isinstance(value, str) or not ORCID.fullmatch(value):
        return False
    total = 0
    for digit in value.replace("-", "")[:-1]:
        total = (total + int(digit)) * 2
    check = (12 - total % 11) % 11
    return value[-1] == ("X" if check == 10 else str(check))


def normalized_name(value):
    # Deliberately no fuzzy match, initials expansion, accent stripping or token sorting.
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())


def _fresh(value, now):
    retrieved = datetime.fromisoformat(value)
    if (
        retrieved.utcoffset() is None
        or now.utcoffset() is None
        or not timedelta(0) <= now - retrieved <= timedelta(days=7)
    ):
        raise ValueError("editorial_authority_expired")


def _field(issue, key, *, required=False):
    items = issue.get(key, [])
    if not items and not required:
        return None
    if (
        not isinstance(items, list)
        or len(items) != 1
        or not isinstance(items[0], dict)
        or not isinstance(items[0].get("_"), str)
        or not items[0]["_"].strip()
    ):
        raise ValueError("editorial_issue_field_invalid")
    return items[0]["_"].strip()


def journal_context(record, tree):
    """Decode official ArticleMeta fields using the published Xylose mapping."""
    issns = set(tree.xpath("./front/journal-meta/issn/text()"))
    years = set(tree.xpath("./front/article-meta/pub-date/year/text()"))
    if (
        not isinstance(record, dict)
        or record.get("code") != "1413-415220250001"
        or record.get("collection") != "scl"
        or record.get("publication_year") != "2025"
        or record.get("issue_type") != "regular"
        or not isinstance(record.get("code_title"), list)
        or not issns
        or not issns <= set(record["code_title"])
        or years != {record["publication_year"]}
    ):
        raise ValueError("editorial_journal_scope_mismatch")
    issue = record["issue"]
    if (
        issue.get("code") != record["code"]
        or issue.get("collection") != "scl"
        or _field(issue, "v131")
        or _field(issue, "v132")
        or _field(issue, "v41")
    ):
        raise ValueError("editorial_issue_unsupported")
    sections = {}
    section_keys = set()
    for entry in issue.get("v49", []):
        if (
            not isinstance(entry, dict)
            or not all(isinstance(entry.get(k), str) and entry[k].strip() for k in ("c", "l", "t"))
            or not re.fullmatch(r"[a-z]{2}", entry["l"])
            or (entry["c"], entry["l"]) in section_keys
        ):
            raise ValueError("editorial_sections_invalid")
        section_keys.add((entry["c"], entry["l"]))
        sections.setdefault(entry["l"], []).append(entry["t"])
    if not sections:
        raise ValueError("editorial_sections_missing")
    return {
        "issues": [
            {
                "volume": _field(issue, "v31", required=True),
                "number": _field(issue, "v32"),
                "supplement": None,
            }
        ],
        "toc_sections": sections,
    }


class BoundEditorialAuthority:
    def __init__(self, candidate, manifest, reader, *, now, profile=PROFILE, crossref=None):
        if (
            set(manifest) != {"version", "profile_id", "candidate_sha256", "sources"}
            or manifest["version"] != "editorial-authority-1.0"
            or manifest["profile_id"] != profile
            or profile != PROFILE
            or manifest["candidate_sha256"] != digest(candidate)
            or not isinstance(manifest["sources"], dict)
        ):
            raise ValueError("editorial_manifest_binding_invalid")
        self._manifest = copy.deepcopy(manifest)
        self.candidate_sha256 = digest(candidate)
        tree = parse_candidate(candidate)
        self._crossref = crossref
        self._doi = tree.xpath("string(./front/article-meta/article-id[@pub-id-type='doi'])")
        if crossref is not None:
            crossref.lookup(self._doi, candidate_sha256=self.candidate_sha256, now=now)
        self._tree_digest = digest(etree.tostring(tree, method="c14n"))
        self._orcids = orcid_identifiers(tree)
        expected_sources = {"journal"} | {i for i in self._orcids if valid_orcid(i)}
        if set(manifest["sources"]) != expected_sources:
            raise ValueError("editorial_source_set_mismatch")
        self._records = {}
        for key, entry in self._manifest["sources"].items():
            url = ISSUE_URL if key == "journal" else f"https://pub.orcid.org/v3.0/{key}/person"
            if (
                not isinstance(entry, dict)
                or set(entry) != {"url", "retrieved_at", "sha256", "status"}
                or entry["url"] != url
                or entry["status"] not in {"available", "unavailable"}
            ):
                raise ValueError("editorial_source_invalid")
            _fresh(entry["retrieved_at"], now)
            if entry["status"] == "unavailable":
                if entry["sha256"] is not None:
                    raise ValueError("editorial_unavailable_source_invalid")
                continue
            raw = reader(key + ".json")
            if not 0 < len(raw) <= MAX_SNAPSHOT or digest(raw) != entry["sha256"]:
                raise ValueError("editorial_snapshot_mismatch")
            self._records[key] = json.loads(raw)
        self._journal = (
            journal_context(self._records["journal"], tree) if "journal" in self._records else {}
        )
        for key, record in self._records.items():
            if key != "journal" and (
                not isinstance(record, dict) or record.get("path") != f"/{key}/person"
            ):
                raise ValueError("editorial_orcid_record_mismatch")

    def check(self, *, now=None, tree=None):
        for entry in self._manifest["sources"].values():
            _fresh(entry["retrieved_at"], now or datetime.now(UTC))
        if tree is not None:
            root = tree.getroot() if hasattr(tree, "getroot") else tree
            if digest(etree.tostring(root, method="c14n")) != self._tree_digest:
                raise ValueError("editorial_runtime_candidate_mismatch")

    def journal(self, *, now=None):
        self.check(now=now)
        return copy.deepcopy(self._journal)

    def lookup_orcid(self, identifier, name, *, now=None):
        self.check(now=now)
        result = {"status": "unknown", "reason": "unavailable"}
        if identifier not in self._orcids or not valid_orcid(identifier):
            return {**result, "reason": "identifier_out_of_scope_or_invalid"}
        record = self._records.get(identifier)
        if record is None:
            return result
        person_name = record.get("name")
        if (
            not isinstance(person_name, dict)
            or str(person_name.get("visibility", "")).casefold() != "public"
        ):
            return {**result, "reason": "public_name_unavailable"}
        names = []
        given = (person_name.get("given-names") or {}).get("value")
        family = (person_name.get("family-name") or {}).get("value")
        credit = (person_name.get("credit-name") or {}).get("value")
        if isinstance(given, str) and isinstance(family, str) and given.strip() and family.strip():
            names.append(f"{given} {family}")
        elif isinstance(given, str) and given.strip() and family is None:
            # ORCID permits an absent family-name; some records put the FULL name
            # in given-names. Still require equality to the complete XML name.
            names.append(given)
        if isinstance(credit, str) and credit.strip():
            names.append(credit)
        if not isinstance(name, str) or not name.strip() or not names:
            return {**result, "reason": "public_name_unavailable"}
        if normalized_name(name) not in {normalized_name(n) for n in names}:
            if self._crossref is not None:
                work = self._crossref.lookup(
                    self._doi, candidate_sha256=self.candidate_sha256, now=now or datetime.now(UTC)
                )["message"]
                authors = work.get("author", [])
                matching_ids = [
                    author
                    for author in authors
                    if isinstance(author, dict)
                    and author.get("ORCID") == "https://orcid.org/" + identifier
                ]
                if len(matching_ids) == 1:
                    author = matching_ids[0]
                    given, family = author.get("given"), author.get("family")
                    if (
                        isinstance(given, str)
                        and isinstance(family, str)
                        and given.strip()
                        and family.strip()
                        and normalized_name(f"{given} {family}") == normalized_name(name)
                    ):
                        return {
                            "status": "registered",
                            "reason": "public_registry_and_crossref_author_match",
                        }
            return {"status": "unconfirmed", "reason": "name_not_confirmed"}
        return {"status": "registered", "reason": "public_record_and_name_match"}
