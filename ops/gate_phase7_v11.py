#!/usr/bin/env python3
"""Run the content-free V-11 robustness, property, and mutation gate."""

from __future__ import annotations

import hashlib
import json
from io import BytesIO
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

from idml_foundation.domain.canonical import (
    FieldState,
    InlineKind,
    InlineNode,
    RichText,
    SourcedText,
)
from idml_foundation.domain.common import canonical_bytes
from idml_foundation.ingest.safe_zip import UnsafeArchiveError, inspect_idml
from idml_foundation.ingest.xml_security import UnsafeXmlError, parse_untrusted_xml
from idml_foundation.release.package_builder import PackageBuilder, PackageInput, PackageRole
from idml_foundation.settings import Settings

ROOT = Path(__file__).parents[1]
REPORT = ROOT / "benchmarks/qualification/reports/v11-robustness-mutation-vh19-v1.json"


def _archive_with(entries: tuple[tuple[str, bytes, int], ...] = ()) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr(
            "mimetype",
            b"application/vnd.adobe.indesign-idml-package",
            compress_type=ZIP_STORED,
        )
        archive.writestr("designmap.xml", b"<Document/>", compress_type=ZIP_DEFLATED)
        for name, content, compression in entries:
            archive.writestr(name, content, compress_type=compression)
    return output.getvalue()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("V-11 report must be a JSON object")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _published_report_gate(report: dict[str, Any]) -> dict[str, Any]:
    if report.get("version") != "phase7-v11-robustness-mutation-1.0":
        raise ValueError("unsupported V-11 report version")
    if report.get("family") != "V-11" or report.get("v11_approved") is not True:
        raise ValueError("V-11 is not approved")
    if report.get("critical_findings_open") != 0 or report.get("major_findings_open") != 0:
        raise ValueError("V-11 has an unresolved critical/major finding")
    mutation = report.get("mutation_assessment", {})
    total = mutation.get("mutants_total")
    if (
        type(total) is not int
        or total < 13
        or type(mutation.get("mutants_killed")) is not int
        or mutation["mutants_killed"] != total
        or mutation.get("score_percent") != 100
        or len(mutation.get("guards", {})) != total
    ):
        raise ValueError("V-11 mutation threshold was not met")
    if report.get("release_candidate_approved") is not False:
        raise ValueError("V-11 cannot approve the release candidate")
    if any(report.get("privacy", {}).values()):
        raise ValueError("V-11 public report violates the content-safe contract")
    expected = report.get("source_sha256", {})
    if "src/idml_foundation/release/package_builder.py" not in expected:
        raise ValueError("V11 source evidence missing")
    actual = {name: _sha256(ROOT / name) for name in expected}
    if actual != expected:
        raise ValueError("V-11 source evidence hash mismatch")
    return {
        "report_sha256": _sha256(REPORT),
        "source_files": len(actual),
        "full_tests": report.get("full_tests"),
        "line_coverage_percent": report.get("line_coverage_percent"),
        "mutation_score_percent": mutation.get("score_percent"),
    }


def _fuzz_gate() -> dict[str, int]:
    settings = Settings(environment="test")
    arbitrary = 0
    for size in range(0, 2048, 17):
        seed = hashlib.sha512(str(size).encode()).digest()
        data = (seed * ((size // len(seed)) + 1))[:size]
        try:
            inspect_idml(data, settings)
        except UnsafeArchiveError:
            arbitrary += 1
        else:
            raise AssertionError("V-11 arbitrary binary input was accepted as IDML")

    source = _archive_with(
        entries=(("Stories/Story_test.xml", b"<Story>" + b"x" * 4096 + b"</Story>", 8),)
    )
    controlled = 0
    accepted = 0
    for seed in range(128):
        candidate = bytearray(source)
        index = int.from_bytes(hashlib.sha256(str(seed).encode()).digest()[:4], "big") % len(
            candidate
        )
        candidate[index] ^= 1 << (seed % 8)
        try:
            inspect_idml(bytes(candidate), settings)
        except UnsafeArchiveError:
            controlled += 1
        else:
            accepted += 1
    return {
        "arbitrary_rejections": arbitrary,
        "zip_mutations": controlled + accepted,
        "controlled_rejections": controlled,
        "accepted_non_structural_mutations": accepted,
    }


def _xml_and_unicode_property_gate() -> dict[str, int]:
    hostile = (
        b"<!DOCTYPE x><x/>",
        b"<!ENTITY x 'y'><x/>",
        b"<x><broken></x>",
        b"<x>\x00</x>",
        b"\xff\xfeinvalid",
    )
    rejected = 0
    for candidate in hostile:
        try:
            parse_untrusted_xml(candidate)
        except UnsafeXmlError:
            rejected += 1
        else:
            raise AssertionError("V-11 hostile XML mutation was accepted")

    alphabet = ("á", "β", "漢", "🙂", "\u00a0", "\u00ad", "\t", "\n")
    for seed in range(128):
        pieces = (
            "v",
            "".join(alphabet[(seed + offset) % len(alphabet)] for offset in range(seed % 11)),
            str(seed),
        )
        rich = RichText(
            plain=SourcedText(value="".join(pieces), state=FieldState.PRESENT),
            inlines=tuple(
                InlineNode(id=f"v11-{seed}-{index}", kind=InlineKind.TEXT, text=piece)
                for index, piece in enumerate(pieces)
            ),
        )
        if RichText.model_validate_json(canonical_bytes(rich)) != rich:
            raise AssertionError("V-11 Unicode property round-trip changed content")
    return {"hostile_xml_rejected": rejected, "unicode_round_trips": 128}


def _package_property_gate() -> dict[str, Any]:
    files = (
        PackageInput(
            name="article.xml",
            role=PackageRole.XML,
            media_type="application/xml",
            data=b"<article/>",
        ),
        PackageInput(
            name="article.pdf",
            role=PackageRole.PDF,
            media_type="application/pdf",
            data=b"%PDF-1.4\n",
        ),
        PackageInput(
            name="article-gf01.png",
            role=PackageRole.ASSET,
            media_type="image/png",
            data=b"\x89PNG\r\n\x1a\nfixture",
        ),
    )
    builder = PackageBuilder()

    def build(candidate: tuple[PackageInput, ...]) -> Any:
        return builder.build(
            article_id="e20249999",
            profile_id="v11-gate",
            source_idml_sha256="a" * 64,
            files=candidate,
            validator_versions={"offline": "v11"},
        )

    baseline = build(files)
    permutations = (files, tuple(reversed(files)), files[1:] + files[:1])
    if any(build(candidate).archive != baseline.archive for candidate in permutations):
        raise AssertionError("V-11 package order property failed")
    mutated = build((*files[:-1], files[-1].model_copy(update={"data": files[-1].data + b"!"})))
    if mutated.package_sha256 == baseline.package_sha256:
        raise AssertionError("V-11 package byte mutation did not alter the bound hash")
    return {
        "order_permutations": len(permutations),
        "member_mutation_detected": True,
        "package_sha256": baseline.package_sha256,
    }


def main() -> int:
    report = _load(REPORT)
    gates = (
        ("published_report", lambda: _published_report_gate(report)),
        ("binary_fuzz", _fuzz_gate),
        ("xml_unicode_properties", _xml_and_unicode_property_gate),
        ("package_properties", _package_property_gate),
    )
    rows: list[dict[str, Any]] = []
    for name, gate in gates:
        try:
            metrics = gate()
        except Exception as exc:
            rows.append({"case": name, "passed": False, "error": type(exc).__name__})
        else:
            rows.append({"case": name, "passed": True, "metrics": metrics})
    approved = all(row["passed"] for row in rows)
    result = {
        "version": "phase7-v11-gate-1.0",
        "family": "V-11",
        "approved": approved,
        "release_candidate_approved": False,
        "production_activation_authorized": False,
        "network_required_by_gate": False,
        "restricted_content_emitted": False,
        "rows": rows,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if approved else 1


if __name__ == "__main__":
    raise SystemExit(main())
