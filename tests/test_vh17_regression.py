from io import BytesIO
from struct import unpack_from
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from idml_foundation.ingest.safe_zip import UnsafeArchiveError, inspect_idml
from idml_foundation.release.package_builder import PackageBuilder, PackageInput, PackageRole
from tests.test_ingest_security_v02 import archive_with


@pytest.mark.parametrize(
    ("repeat_xml", "expected"),
    [(False, "requires exactly one XML and one PDF"), (True, "filenames must be unique")],
)
def test_incomplete_or_duplicate_package_is_rejected(repeat_xml, expected):
    xml = PackageInput(
        name="article.xml", role=PackageRole.XML, media_type="application/xml", data=b"<article/>"
    )
    with pytest.raises(ValueError, match=expected):
        PackageBuilder().build(
            article_id="e20249999",
            profile_id="v11",
            source_idml_sha256="a" * 64,
            files=(xml, xml) if repeat_xml else (xml,),
            validator_versions={"offline": "v11"},
        )


def test_corrupt_deflate_block_is_rejected(settings):
    source = archive_with((("Stories/test.xml", b"<Story/>", ZIP_DEFLATED),))
    inspect_idml(source, settings)
    with ZipFile(BytesIO(source)) as archive:
        offset = archive.getinfo("Stories/test.xml").header_offset
    name_size, extra_size = unpack_from("<HH", source, offset + 26)
    start = offset + 30 + name_size + extra_size
    corrupted = bytearray(source)
    corrupted[start] |= 0b111  # Reserved deflate block type and final-block bit.
    with pytest.raises(UnsafeArchiveError):
        inspect_idml(bytes(corrupted), settings)
