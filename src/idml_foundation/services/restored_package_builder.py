"""Rebuild exact restored content; never re-enrich, repair or reuse old reports."""

import hashlib
from dataclasses import dataclass
from typing import Any

from idml_foundation.domain.canonical import CanonicalArticle
from idml_foundation.pipeline.jats_builder import JatsBuilder
from idml_foundation.pipeline.profile import JournalProfile
from idml_foundation.pipeline.validation import OfflineJatsValidator, ValidationReport
from idml_foundation.release.package_builder import (
    AssetPayload,
    PackageBuild,
    PackageBuilder,
    PackageRole,
)
from idml_foundation.services.autocorrection_package import _graphics, _root, _verify_packaging
from idml_foundation.services.autocorrection_promotion_policy import draft_admission
from idml_foundation.services.package_validation import Executor, assess_rebuilt_package
from idml_foundation.services.xpm_execution import XpmExecutor
from idml_foundation.settings import Settings


@dataclass(frozen=True)
class RestoredBuild:
    xml: bytes
    package: PackageBuild
    reports: dict[str, Any]
    decision: dict[str, Any]
    scope: dict[str, str]


def build_restored_package(
    *,
    article: CanonicalArticle,
    organization_id: str,
    resource_id: str,
    source_sha256: str,
    pdf: bytes,
    assets: tuple[AssetPayload, ...],
    profile: JournalProfile,
    settings: Settings,
    validator: OfflineJatsValidator,
    executor: Executor | None,
    xpm_executor: XpmExecutor | None,
) -> RestoredBuild:
    if article.journal_profile_id != profile.profile_id:
        raise ValueError("restored_profile_mismatch")
    xml = JatsBuilder(sps_version=profile.sps_version).build(article)
    hrefs = [node.get("{http://www.w3.org/1999/xlink}href", "") for node in _graphics(_root(xml))]
    if (
        len(hrefs) != len(set(hrefs))
        or len(assets) != len({asset.source_name for asset in assets})
        or set(hrefs) != {asset.source_name for asset in assets}
    ):
        raise ValueError("restored_package_requires_exact_asset_mapping")
    if not pdf.startswith(b"%PDF-"):
        raise ValueError("restored_pdf_invalid")
    if len(xml) + len(pdf) + sum(len(a.data) for a in assets) > settings.upload_max_bytes:
        raise ValueError("restored_package_too_large")
    stem = profile.package_stem(article.article_id)
    builder = PackageBuilder()
    files = builder.scielo_files(package_stem=stem, xml=xml, pdf=pdf, assets=assets)
    xml = _verify_packaging(xml, files, assets, package_stem=stem, pdf=pdf)
    offline = None
    try:
        report = validator.validate(
            xml, asset_names={f.name for f in files if f.role == PackageRole.ASSET}
        )
        report = ValidationReport.model_validate(report.model_dump(mode="python"))
        if report.xml_sha256 != hashlib.sha256(xml).hexdigest() or report.valid == any(
            i.severity == "error" for i in report.issues
        ):
            raise ValueError("offline_report_mismatch")
        offline = report
    except Exception:
        # Exceptions may contain private XML or executor credentials.
        offline = None
    package = builder.build(
        article_id=article.article_id,
        profile_id=profile.profile_id,
        source_idml_sha256=source_sha256,
        files=files,
        validator_versions={"offline": offline.validator_profile if offline else "unavailable"},
    )
    if package.package_size_bytes > settings.upload_max_bytes:
        raise ValueError("restored_package_too_large")
    scope = dict(
        organization_id=organization_id,
        resource_id=resource_id,
        source_idml_sha256=source_sha256,
        journal_profile_id=profile.profile_id,
        xml_sha256=hashlib.sha256(xml).hexdigest(),
        package_sha256=package.package_sha256,
    )
    formal = assess_rebuilt_package(
        xml=xml,
        package=package.archive,
        executor=executor,
        settings=settings,
        offline_valid=offline is not None and offline.valid,
        xpm_executor=xpm_executor,
        scope=scope,
    )
    reports = dict(
        offline=offline.model_dump(mode="json") if offline else None,
        formal=formal,
        manifest=package.manifest.model_dump(mode="json"),
    )
    decision = draft_admission(
        offline=reports["offline"],
        formal=formal,
        xml_sha256=scope["xml_sha256"],
        package_sha256=scope["package_sha256"],
        validation_scope=scope,
    )
    return RestoredBuild(xml, package, reports, decision, scope)
