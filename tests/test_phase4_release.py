import hashlib
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from pypdf import PdfWriter

from idml_foundation.pipeline.service import DeterministicPipeline
from idml_foundation.pipeline.validation import OfflineJatsValidator
from idml_foundation.release.fidelity import FidelityEngine, FidelityReport, PdfTextSource
from idml_foundation.release.package_builder import (
    AssetPayload,
    PackageBuilder,
    PackageInput,
    PackageRole,
)
from idml_foundation.release.policy import (
    HumanReleaseOverride,
    ReleaseDecision,
    ReleasePolicy,
)
from idml_foundation.release.repair import RepairKind, SafeRepairEngine
from idml_foundation.release.validation_engine import ValidationEngine
from idml_foundation.release.xpm import (
    XpmAttestation,
    XpmReportParser,
    XpmWarningAcceptance,
)
from tests.phase3_helpers import synthetic_idml


def _blank_pdf() -> bytes:
    buffer = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.write(buffer)
    return buffer.getvalue()


def _package() -> tuple[bytes, str]:
    xml = b"<article/>"
    build = PackageBuilder().build(
        article_id="e20240001",
        profile_id="esa-aop-1.0.0",
        source_idml_sha256="a" * 64,
        files=(
            PackageInput(
                name="article.xml", role=PackageRole.XML, media_type="application/xml", data=xml
            ),
            PackageInput(
                name="article.pdf",
                role=PackageRole.PDF,
                media_type="application/pdf",
                data=_blank_pdf(),
            ),
        ),
        validator_versions={"offline-jats": "1.0"},
    )
    return build.archive, build.package_sha256


def test_validation_engine_normalizes_and_binds_results_to_candidate() -> None:
    engine = ValidationEngine()
    xml = b"<article/>"
    run = engine.packtools_run(
        xml,
        {
            "results": [
                {"level": "warning", "code": "missing-value", "message": "required missing"},
                {"severity": "error", "message": "DTD element invalid", "xpath": "/article"},
            ]
        },
        tool_sha256="b" * 64,
    )
    report = engine.aggregate(xml, (run,), ("packtools",))
    assert report.complete
    assert not report.valid
    assert [item.category for item in run.issues] == ["deterministic", "missing-source"]

    unavailable = engine.unavailable("xpm", "4.0.096", xml, "worker-not-configured")
    assert unavailable.failure_code == "worker-not-configured"
    with pytest.raises(ValueError, match="does not belong"):
        engine.aggregate(b"different", (run,), ("packtools",))


def test_safe_repair_is_bounded_audited_and_idempotent() -> None:
    source = b'<article><p id=" target ">x</p><xref rid="  target  ">1</xref></article>'
    repaired, report = SafeRepairEngine().repair(source)

    assert b'id="target"' in repaired
    assert b'rid="target"' in repaired
    assert {item.kind for item in report.operations} == {
        RepairKind.TRIM_ID,
        RepairKind.NORMALIZE_RID_WHITESPACE,
    }
    second, second_report = SafeRepairEngine().repair(repaired)
    assert second == repaired
    assert not second_report.operations
    with pytest.raises(ValueError, match="max_passes"):
        SafeRepairEngine().repair(source, max_passes=3)
    validator = OfflineJatsValidator(Path(__file__).parents[1] / "vendor" / "jats" / "1.3")
    _, _, validations = SafeRepairEngine().repair_and_revalidate(source, validator)
    assert len(validations) == 2


def test_package_builder_is_byte_deterministic_and_self_describing() -> None:
    first, first_sha = _package()
    second, second_sha = _package()
    assert first == second
    assert first_sha == second_sha == hashlib.sha256(first).hexdigest()
    with ZipFile(BytesIO(first)) as archive:
        assert archive.namelist() == ["article.pdf", "article.xml", "conversion-manifest.json"]

    with pytest.raises(ValueError, match="safe basename"):
        PackageInput(
            name="../bad.xml", role=PackageRole.XML, media_type="application/xml", data=b""
        )


def test_scielo_file_resolution_renames_and_rebinds_graphics() -> None:
    xml = b"""<?xml version="1.0"?><article xmlns:xlink="http://www.w3.org/1999/xlink">
    <body><fig><graphic xlink:href="Figure1.jpg"/></fig></body></article>"""
    files = PackageBuilder().scielo_files(
        package_stem="1809-4457-esa-30-e20240001",
        xml=xml,
        pdf=_blank_pdf(),
        assets=(AssetPayload(source_name="Figure1.jpg", data=b"jpeg"),),
    )
    assert [item.name for item in files] == [
        "1809-4457-esa-30-e20240001.xml",
        "1809-4457-esa-30-e20240001.pdf",
        "1809-4457-esa-30-e20240001-gf01.jpg",
    ]
    assert b"1809-4457-esa-30-e20240001-gf01.jpg" in files[0].data
    with pytest.raises(ValueError, match="not referenced"):
        PackageBuilder().scielo_files(
            package_stem="article",
            xml=xml,
            pdf=_blank_pdf(),
            assets=(
                AssetPayload(source_name="Figure1.jpg", data=b"jpeg"),
                AssetPayload(source_name="extra.jpg", data=b"jpeg"),
            ),
        )
    with pytest.raises(ValueError, match="exactly one"):
        PackageBuilder().build(
            article_id="x",
            profile_id="x",
            source_idml_sha256="a" * 64,
            files=(
                PackageInput(
                    name="x.xml",
                    role=PackageRole.XML,
                    media_type="application/xml",
                    data=b"x",
                ),
            ),
            validator_versions={},
        )


def test_xpm_contract_and_release_policy_fail_closed() -> None:
    archive, package_sha = _package()
    report = b"""<html><body><!-- 4.0.096 22/04/2019 -->
    <span>Total of blocking errors</span>: 0 <span>Total of fatal errors</span>: 0
    <span>Total of errors</span>: 0 <span>Total of warnings</span>: 2</body></html>"""
    report_sha = hashlib.sha256(report).hexdigest()
    parser = XpmReportParser()
    xpm = parser.parse_attested(
        report,
        XpmAttestation(
            candidate_package_sha256=package_sha,
            report_sha256=report_sha,
            tool_sha256="c" * 64,
            xpm_version="4.0.096",
            command_id="xpm-package-maker",
            environment="dedicated-windows-worker",
        ),
    )
    assert not xpm.passed and xpm.xpm_version == "4.0.096"
    xpm = parser.accept_warnings(
        xpm,
        XpmWarningAcceptance(
            acceptance_id="accept-xpm-warnings-1",
            xpm_version="4.0.096",
            warning_count=2,
            report_sha256=report_sha,
            accepted_by="phase-4-test-policy",
            justification="As duas advertências pertencem à fixture controlada deste teste.",
            evidence_sha256=report_sha,
        ),
    )
    assert xpm.passed

    validation_engine = ValidationEngine()
    validator = validation_engine.packtools_run(archive, [], tool_sha256="b" * 64)
    validation = validation_engine.aggregate(archive, (validator,), ("packtools",))
    fidelity = FidelityReport(
        pdf_sha256="d" * 64,
        xml_sha256="e" * 64,
        page_count=1,
        text_extraction_available=True,
        pdf_text_source=PdfTextSource.TEXT_LAYER,
        components=(),
        minimum_pdf_recall=0.8,
        minimum_xml_recall=0.98,
        passed=True,
    )
    ready = ReleasePolicy().assess(
        package_sha256=package_sha,
        validation=validation,
        fidelity=fidelity,
        xpm=xpm,
    )
    assert ready.decision == ReleaseDecision.READY_FOR_SCIELO

    overridden = ReleasePolicy().assess(
        package_sha256=package_sha,
        validation=validation,
        fidelity=fidelity,
        xpm=xpm,
        review_reasons=("editorial-review",),
        human_override=HumanReleaseOverride(
            override_id="override-1",
            approved_by_user_id="user-1",
            company_id="company-1",
            justification="Revisão editorial humana documentada e aprovada.",
            evidence_sha256="f" * 64,
        ),
    )
    assert overridden.human_override_id == "override-1"

    unavailable = XpmReportParser().unavailable(package_sha, "xpm-worker-unavailable")
    blocked = ReleasePolicy().assess(
        package_sha256=package_sha,
        validation=validation,
        fidelity=fidelity,
        xpm=unavailable,
    )
    assert blocked.decision == ReleaseDecision.VALIDATION_UNAVAILABLE


def test_fidelity_engine_reports_unextractable_pdf_without_ocr_guessing() -> None:
    pipeline = DeterministicPipeline()
    result = pipeline.run(synthetic_idml(), logical_name="ESA_2024001_AOP.idml")
    report = FidelityEngine().compare(result.canonical, result.xml, _blank_pdf())

    assert report.page_count == 1
    assert not report.text_extraction_available
    assert report.pdf_text_source == PdfTextSource.UNAVAILABLE
    assert not report.passed
    ocr_report = FidelityEngine().compare(
        result.canonical,
        result.xml,
        _blank_pdf(),
        ocr_text="Deterministic conversion Ana Silva Introduction Plain emphasis",
    )
    assert ocr_report.pdf_text_source == PdfTextSource.OCR


def test_parser_collects_spread_assets_separately_from_story_assets() -> None:
    source = synthetic_idml()
    output = BytesIO()
    with ZipFile(BytesIO(source)) as original, ZipFile(output, "w", ZIP_DEFLATED) as updated:
        for name in original.namelist():
            data = original.read(name)
            if name.startswith("Spreads/"):
                data = data.replace(
                    b"</Spread>",
                    b'<Rectangle><Image><Link Self="spread-link" '
                    b'LinkResourceURI="file:C:/secret/Figure2.jpg" '
                    b'LinkResourceFormat="$ID/JPEG"/></Image></Rectangle></Spread>',
                )
            updated.writestr(name, data)
    raw = DeterministicPipeline().run(output.getvalue(), logical_name="ESA_2024001_AOP.idml").raw
    assert {item.logical_path for item in raw.assets} == {"Figure 1.jpg", "Figure2.jpg"}
    assert any(item.relationship == "external-layout-asset" for item in raw.links)
