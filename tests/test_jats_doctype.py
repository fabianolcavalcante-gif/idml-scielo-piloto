"""Check the emitted declaration against the independent NLM catalog, not itself."""

import hashlib
from pathlib import Path

import pytest
from lxml import etree

from idml_foundation.pipeline.jats_builder import JatsBuilder
from idml_foundation.pipeline.validation import OfflineJatsValidator
from ops.v05_fixture import complete_article

VENDOR = Path(__file__).parents[1] / "vendor/jats/1.3"
PUBLIC = b"-//NLM//DTD JATS (Z39.96) Journal Publishing DTD with MathML3 v1.3 20210610//EN"
SYSTEM = b"JATS-journalpublishing1-3-mathml3.dtd"
LEGACY = PUBLIC.replace(b" with MathML3", b"")


def validate(xml):
    article = complete_article()
    return OfflineJatsValidator(VENDOR).validate(
        xml, asset_names={a.logical_name for a in article.assets}
    )


def test_generated_declaration_matches_official_nlm_catalog():
    xml = JatsBuilder().build(complete_article())
    info = etree.fromstring(xml).getroottree().docinfo
    catalog = etree.parse(str(VENDOR / "catalog-jats-v1-3-no-base.xml"))
    entries = catalog.xpath(
        "//*[local-name()='public'][@uri=$system]/@publicId", system=info.system_url
    )
    assert entries == [info.public_id] == [PUBLIC.decode()]
    assert info.system_url == SYSTEM.decode()
    assert hashlib.sha256((VENDOR / SYSTEM.decode()).read_bytes()).hexdigest() == (
        "af6f75cd07a575d4be12f4e44cc97c644c3b8a4d2ce68e6ff582c5b6170760fc"
    )
    assert validate(xml).valid


@pytest.mark.parametrize(
    "old,new",
    [
        (PUBLIC, LEGACY),
        (SYSTEM, b"JATS-journalpublishing1-3.dtd"),
        (SYSTEM, b"https://example.invalid/schema.dtd"),
        (SYSTEM, b"file:///private/schema.dtd"),
        (PUBLIC, PUBLIC.replace(b"v1.3", b"v1.1")),
    ],
)
def test_wrong_or_mixed_identifiers_are_rejected_without_loading_them(old, new):
    xml = JatsBuilder().build(complete_article()).replace(old, new)
    report = validate(xml)
    assert not report.valid
    assert "unexpected-doctype" in {i.code for i in report.issues}


def test_correct_header_does_not_hide_invalid_footnote_type():
    xml = JatsBuilder().build(complete_article())
    assert b'fn-type="coi-statement"' in xml
    result = validate(xml.replace(b'fn-type="coi-statement"', b'fn-type="invented"'))
    assert not result.valid
    assert any(i.code.startswith("dtd-") for i in result.issues)


def test_correct_header_does_not_hide_wrong_root_version_or_truncation():
    xml = JatsBuilder().build(complete_article())
    version = validate(xml.replace(b'dtd-version="1.3"', b'dtd-version="1.1"'))
    assert not version.valid
    assert "unsupported-jats-version" in {i.code for i in version.issues}
    assert not validate(xml[:-20]).valid
