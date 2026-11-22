import json
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, SerializerFunctionWrapHandler, model_serializer

from idml_foundation.domain.common import StrictModel

DIRECT_PARAGRAPH_SUFFIX = " [direct paragraph properties]"


class JournalProfile(StrictModel):
    profile_id: str
    profile_version: str
    journal_title: str
    journal_abbreviated_title: str
    journal_publisher_id: str
    journal_print_issn: str
    journal_issn: str
    publisher_name: str
    primary_language: str = Field(pattern=r"^[a-z]{2,3}$")
    secondary_language: str = Field(pattern=r"^[a-z]{2,3}$")
    article_category: str
    subject_category: str
    license_text: str
    country_codes: dict[str, str]
    sps_version: str = Field(pattern=r"^sps-\d+\.\d+$")
    package_name_template: str
    style_roles: dict[str, str]
    # Exact InDesign style names (as exported, e.g. "zp.Texto") for templates whose
    # styles carry no numeric journal prefix. Checked before the numeric prefix.
    style_name_roles: dict[str, str] = Field(default_factory=dict)
    # Optional: derive the article id (elocation) from the DOI instead of the file name,
    # e.g. RBEPID 10.1590/1980-549720250033 -> e250033.
    article_id_from_doi: str | None = None
    article_id_template: str | None = None
    # Day/month order of history dates per language ("dmy" default, "mdy" for US style).
    history_date_order: dict[str, str] = Field(default_factory=dict)
    # Reference list style; None keeps the historical ABNT-oriented parser.
    reference_style: Literal["vancouver"] | None = None
    license_url: str | None = None
    # Ordered (DOI regex, id template) rules; the first match wins (e.g. errata ids).
    article_id_rules: tuple[tuple[str, str], ...] = ()

    @model_serializer(mode="wrap")
    def _omit_empty_name_roles(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        # Profiles that do not use name-based roles keep their historical serialization,
        # so their content digests (pinned by qualification evidence) do not change.
        data: dict[str, Any] = handler(self)
        if not self.style_name_roles:
            data.pop("style_name_roles", None)
        if not self.history_date_order:
            data.pop("history_date_order", None)
        for optional in (
            "article_id_from_doi",
            "article_id_template",
            "reference_style",
            "license_url",
        ):
            if getattr(self, optional) is None:
                data.pop(optional, None)
        if not self.article_id_rules:
            data.pop("article_id_rules", None)
        return data

    def article_id_for_doi(self, doi: str | None) -> str | None:
        if not doi:
            return None
        for pattern, template in self.article_id_rules:
            if rule := re.search(pattern, doi):
                return template.format(**rule.groupdict(default=""))
        if not (self.article_id_from_doi and self.article_id_template):
            return None
        match = re.search(self.article_id_from_doi, doi)
        return self.article_id_template.format(**match.groupdict()) if match else None

    def package_stem(self, article_id: str) -> str:
        value = self.package_name_template.replace("{article_id}", article_id)
        if not value or any(character in value for character in "/\\"):
            raise ValueError("profile produced an unsafe package name")
        return value

    def role_for_style(self, source_name: str, prefix: str | None) -> str | None:
        # The parser records local overrides as "<style> [direct paragraph properties]";
        # the semantic role is the one of the underlying style.
        base_name = source_name.removesuffix(DIRECT_PARAGRAPH_SUFFIX).strip()
        named = self.style_name_roles.get(base_name)
        return named if named is not None else self.role_for_prefix(prefix)

    def role_for_prefix(self, prefix: str | None) -> str | None:
        if prefix is None:
            return None
        return self.style_roles.get(prefix) or self.style_roles.get(prefix.split(".", 1)[0])


def default_profile_path() -> Path:
    return Path(__file__).resolve().parents[3] / "profiles" / "esa-aop-1.0.json"


def load_profile(path: Path | None = None) -> JournalProfile:
    profile_path = path or default_profile_path()
    return JournalProfile.model_validate(json.loads(profile_path.read_text(encoding="utf-8")))
