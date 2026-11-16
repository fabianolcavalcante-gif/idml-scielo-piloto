import hashlib
from io import BytesIO
from zipfile import ZIP_STORED, ZipFile

import pytest

from idml_foundation.ingest.safe_zip import UnsafeArchiveError, inspect_idml
from idml_foundation.ingest.xml_security import (
    UnsafeXmlError,
    XmlComplexityBudget,
    parse_untrusted_xml,
)
from idml_foundation.models import Artifact
from idml_foundation.pipeline.idml_parser import IdmlParser
from idml_foundation.services.artifacts import read_artifact_bytes
from tests.helpers import make_idml


@pytest.mark.parametrize(
    "content",
    [b"<r><a/><b/></r>", b"<r a='1' b='2'/>", b"<r><!--a--><!--b--></r>", b"<r><?a x?><?b x?></r>"],
)
def test_xml_complexity_counts_elements_attributes_comments_and_pi(content):
    with pytest.raises(UnsafeXmlError, match="complexity"):
        parse_untrusted_xml(content, budget=XmlComplexityBudget(limit=2))


def test_xml_complexity_budget_is_shared_between_documents():
    budget = XmlComplexityBudget(limit=3)
    parse_untrusted_xml(b"<r><a/></r>", budget=budget)
    with pytest.raises(UnsafeXmlError, match="complexity"):
        parse_untrusted_xml(b"<r><b/></r>", budget=budget)


def test_complexity_is_rejected_before_constructing_dom(monkeypatch):
    monkeypatch.setattr(
        "idml_foundation.ingest.xml_security.etree.fromstring",
        lambda *_a, **_kw: pytest.fail("tree must not be constructed"),
    )
    with pytest.raises(UnsafeXmlError, match="complexity"):
        parse_untrusted_xml(b"<r><a/><b/></r>", budget=XmlComplexityBudget(limit=2))


def test_aggregate_xml_bytes_checked_before_crc(settings, monkeypatch):
    data = make_idml(extra_name="Stories/second.xml", extra_data=b"<Story/>")
    monkeypatch.setattr("idml_foundation.ingest.safe_zip.MAX_IDML_XML_BYTES", 18)
    monkeypatch.setattr(ZipFile, "testzip", lambda _self: pytest.fail("must reject before CRC"))
    with pytest.raises(UnsafeArchiveError) as rejected:
        inspect_idml(data, settings)
    assert rejected.value.code == "expanded_xml_too_large"


def test_aggregate_xml_bytes_accept_exact_limit(settings, monkeypatch):
    data = make_idml(extra_name="Stories/second.xml", extra_data=b"<Story/>")
    monkeypatch.setattr("idml_foundation.ingest.safe_zip.MAX_IDML_XML_BYTES", 19)
    assert inspect_idml(data, settings).entry_count == 3


def test_idml_parser_shares_one_budget_across_archive(settings, monkeypatch):
    data = make_idml(extra_name="Stories/second.xml", extra_data=b"<Story><p/><p/></Story>")
    monkeypatch.setattr(
        "idml_foundation.pipeline.idml_parser.XmlComplexityBudget",
        lambda: XmlComplexityBudget(limit=3),
    )
    with pytest.raises(UnsafeArchiveError) as rejected:
        IdmlParser(settings).parse(data, logical_name="synthetic.idml")
    assert rejected.value.code == "unsafe_xml"


def test_oversized_xml_is_rejected_before_crc_or_decompression(settings, monkeypatch):
    data = make_idml(extra_name="Stories/large.XML", extra_data=b"<Story>large</Story>")
    monkeypatch.setattr("idml_foundation.ingest.safe_zip.MAX_UNTRUSTED_XML_BYTES", 11)
    monkeypatch.setattr(ZipFile, "testzip", lambda _self: pytest.fail("must reject before CRC"))
    with pytest.raises(UnsafeArchiveError) as rejected:
        inspect_idml(data, settings)
    assert rejected.value.code == "unsafe_xml"


def test_oversized_mimetype_is_rejected_before_crc(settings, monkeypatch):
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_STORED) as archive:
        archive.writestr("mimetype", b"x" * 4096)
        archive.writestr("designmap.xml", b"<Document/>")
    monkeypatch.setattr(ZipFile, "testzip", lambda _self: pytest.fail("must reject before CRC"))
    with pytest.raises(UnsafeArchiveError) as rejected:
        inspect_idml(output.getvalue(), settings)
    assert rejected.value.code == "invalid_mimetype"


@pytest.mark.parametrize("mutation", ["valid", "grown", "truncated", "oversize", "digest"])
def test_artifact_read_checks_size_before_hash(settings, mutation):
    content = b"synthetic bounded artifact"
    digest = hashlib.sha256(content).hexdigest()
    key = f"synthetic-org/{digest[:2]}/{digest}"
    path = settings.artifact_root / key
    path.parent.mkdir(parents=True)
    path.write_bytes(content)
    artifact = Artifact(
        organization_id="synthetic-org", storage_key=key, size_bytes=len(content), sha256=digest
    )
    if mutation == "grown":
        path.write_bytes(content + b"x")
    elif mutation == "truncated":
        path.write_bytes(content[:-1])
    elif mutation == "oversize":
        settings.upload_max_bytes = len(content) - 1
    elif mutation == "digest":
        path.write_bytes(b"!" + content[1:])
    if mutation == "valid":
        assert read_artifact_bytes(artifact, settings) == content
    else:
        expected = {
            "grown": "size integrity failure",
            "truncated": "size integrity failure",
            "oversize": "size exceeds read limit",
            "digest": "artifact integrity failure",
        }
        with pytest.raises(ValueError, match=expected[mutation]):
            read_artifact_bytes(artifact, settings)
