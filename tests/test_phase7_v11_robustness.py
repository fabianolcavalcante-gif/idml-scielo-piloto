import hashlib
import random
from io import BytesIO
from itertools import product
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

import pytest
from lxml import etree

from idml_foundation.ingest.safe_zip import UnsafeArchiveError, inspect_idml
from idml_foundation.ingest.xml_security import UnsafeXmlError
from idml_foundation.pipeline.service import DeterministicPipeline
from idml_foundation.release.package_builder import (
    PackageBuild,
    PackageBuilder,
    PackageInput,
    PackageRole,
)
from idml_foundation.settings import Settings
from tests.phase3_helpers import synthetic_idml


def _repack(
    source: bytes,
    *,
    order: str = "original",
    replacements: tuple[tuple[bytes, bytes], ...] = (),
    pretty_xml: bool = False,
) -> bytes:
    output = BytesIO()
    with ZipFile(BytesIO(source)) as archive:
        names = archive.namelist()
        if order == "reverse":
            names.reverse()
        elif order == "rotated":
            names = names[3:] + names[:3]
        with ZipFile(output, "w") as rebuilt:
            for name in names:
                data = archive.read(name)
                for before, after in replacements:
                    data = data.replace(before, after)
                if pretty_xml and name.casefold().endswith(".xml"):
                    root = etree.fromstring(data)
                    data = etree.tostring(
                        root,
                        encoding="UTF-8",
                        xml_declaration=True,
                        pretty_print=True,
                    )
                info = ZipInfo(name)
                info.compress_type = ZIP_STORED if name == "mimetype" else ZIP_DEFLATED
                rebuilt.writestr(info, data)
    return output.getvalue()


def _semantic_xml(xml: bytes) -> bytes:
    root = etree.fromstring(xml)
    for element in root.iter():
        for attribute in tuple(element.attrib):
            if etree.QName(attribute).localname in {"id", "rid"}:
                del element.attrib[attribute]
        if element.text is not None and not element.text.strip():
            element.text = None
        if element.tail is not None and not element.tail.strip():
            element.tail = None
    return etree.tostring(root, method="c14n")


def test_v11_binary_fuzz_rejects_corruption_with_controlled_errors(settings: Settings) -> None:
    randomizer = random.Random(20260911)  # noqa: S311 - deterministic fuzz corpus
    for size in range(0, 2048, 17):
        data = randomizer.randbytes(size)
        with pytest.raises(UnsafeArchiveError):
            inspect_idml(data, settings)

    source = synthetic_idml(include_table=True, include_formula=True)
    controlled = 0
    accepted = 0
    for seed in range(128):
        candidate = bytearray(source)
        index = random.Random(seed).randrange(len(candidate))  # noqa: S311
        candidate[index] ^= 1 << (seed % 8)
        try:
            inspect_idml(bytes(candidate), settings)
        except UnsafeArchiveError:
            controlled += 1
        else:
            accepted += 1
    assert controlled + accepted == 128
    assert controlled > 0


@pytest.mark.parametrize(
    "payload",
    [
        b"<!DOCTYPE x [<!ENTITY e SYSTEM 'file:///etc/passwd'>]><Document>&e;</Document>",
        b"<Document><unclosed></Document>",
        b"\xff\xfe\x00<\x00D\x00o\x00c\x00u\x00m\x00e\x00n\x00t\x00>",
        b"<Document>\x00</Document>",
        b"<Document><!ENTITY invalid></Document>",
    ],
)
def test_v11_hostile_internal_xml_fails_closed(payload: bytes) -> None:
    source = synthetic_idml()
    candidate = _repack(
        source,
        replacements=(
            (
                b'<Document Self="doc" DOMVersion="20.3" StoryList="u1 u2 u3 u4"/>',
                payload,
            ),
        ),
    )
    with pytest.raises((UnsafeXmlError, UnsafeArchiveError)):
        DeterministicPipeline().run(candidate, logical_name="ESA_2024001_AOP.idml")


def test_v11_zip_order_whitespace_and_source_id_metamorphisms_preserve_semantics() -> None:
    source = synthetic_idml(
        include_table=True,
        include_subsection=True,
        include_formula=True,
        include_inline_formula=True,
        include_correspondence=True,
        include_back_matter=True,
        include_graphic_mention=True,
        include_styled_table=True,
    )
    baseline = DeterministicPipeline().run(source, logical_name="ESA_2024001_AOP.idml")
    variants = (
        _repack(source, order="reverse"),
        _repack(source, order="rotated"),
        _repack(source, pretty_xml=True),
        _repack(
            source,
            replacements=(
                (b"u1 u2 u3 u4", b"x1 x2 x3 x4"),
                *((f'"u{index}"'.encode(), f'"x{index}"'.encode()) for index in range(1, 5)),
            ),
        ),
    )
    for variant in variants:
        result = DeterministicPipeline().run(variant, logical_name="ESA_2024001_AOP.idml")
        assert result.validation.valid
        assert _semantic_xml(result.xml) == _semantic_xml(baseline.xml)


def test_v11_unicode_styles_tables_and_mixed_content_are_stable() -> None:
    unicode_values = (
        "Português com acentuação e não\u00a0separável",
        "Ελληνικά βήτα",
        "漢字とかな",
        "emoji científico 🧬",
        "direção العربية",
        "combinação e\u0301",
    )
    source = synthetic_idml(include_table=True, include_styled_table=True)
    for index, value in enumerate(unicode_values):
        candidate = _repack(
            source,
            replacements=((b"Deterministic conversion", value.encode("utf-8")),),
        )
        first = DeterministicPipeline().run(candidate, logical_name=f"ESA_2024{index:03}_AOP.idml")
        second = DeterministicPipeline().run(candidate, logical_name=f"ESA_2024{index:03}_AOP.idml")
        assert first.validation.valid
        assert first.canonical.front.titles[0].text.value == value
        assert first.xml == second.xml

    for include_table, include_formula, include_inline, include_back in product(
        (False, True), repeat=4
    ):
        candidate = synthetic_idml(
            include_table=include_table,
            include_styled_table=include_table,
            include_formula=include_formula,
            include_inline_formula=include_inline,
            include_back_matter=include_back,
        )
        first = DeterministicPipeline().run(candidate, logical_name="ESA_2024998_AOP.idml")
        second = DeterministicPipeline().run(candidate, logical_name="ESA_2024998_AOP.idml")
        assert first.validation.valid
        assert first.xml == second.xml
        assert first.canonical == second.canonical


def test_v11_package_order_property_and_member_mutation_change_bound_hashes() -> None:
    builder = PackageBuilder()
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

    def build(candidate: tuple[PackageInput, ...]) -> PackageBuild:
        return builder.build(
            article_id="e20249999",
            profile_id="v11-property",
            source_idml_sha256="a" * 64,
            files=candidate,
            validator_versions={"offline": "v11"},
        )

    baseline = build(files)
    for candidate in (files, tuple(reversed(files)), files[1:] + files[:1]):
        result = build(candidate)
        assert result.archive == baseline.archive
        assert result.package_sha256 == baseline.package_sha256

    mutated_files = (
        *files[:-1],
        files[-1].model_copy(update={"data": files[-1].data + b"!"}),
    )
    mutated = build(mutated_files)
    assert mutated.package_sha256 != baseline.package_sha256
    assert mutated.manifest.candidate_set_sha256 != baseline.manifest.candidate_set_sha256
    assert hashlib.sha256(mutated.archive).hexdigest() == mutated.package_sha256
