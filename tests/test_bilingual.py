import pytest
from lxml import etree

from idml_foundation.pipeline.bilingual import BilingualCompositionError, compose_bilingual

_LANG = "{http://www.w3.org/XML/1998/namespace}lang"


def _article(lang: str, other: str, title: str, ref_prefix: str) -> bytes:
    return f"""<?xml version='1.0' encoding='UTF-8'?>
<!DOCTYPE article PUBLIC "-//NLM//DTD JATS (Z39.96) Journal Publishing DTD v1.1//EN" "x.dtd">
<article xmlns:xlink="http://www.w3.org/1999/xlink" xml:lang="{lang}"><front><article-meta>
<article-id pub-id-type="doi">10.1590/x{".2" if lang == "pt" else ""}</article-id>
<title-group><article-title>{title}</article-title><trans-title-group xml:lang="{other}">
<trans-title>T</trans-title></trans-title-group></title-group>
<contrib-group><contrib><xref ref-type="aff" rid="aff-1">I</xref></contrib></contrib-group>
<aff id="aff-1"><institution content-type="original">Inst</institution></aff>
<abstract xml:lang="{lang}"><p>A {lang}</p></abstract>
<trans-abstract xml:lang="{other}"><p>A {other}</p></trans-abstract>
<kwd-group xml:lang="{lang}"><kwd>k{lang}</kwd></kwd-group>
<kwd-group xml:lang="{other}"><kwd>k{other}</kwd></kwd-group></article-meta></front>
<body><sec id="sec-1"><p>Text<sup><xref rid="{ref_prefix}1" ref-type="bibr">1</xref></sup></p>
</sec></body>
<back><ref-list><ref id="{ref_prefix}1"><mixed-citation>1. R</mixed-citation></ref></ref-list>
</back></article>""".encode()


def test_translation_becomes_sub_article_with_prefixed_ids_and_main_references() -> None:
    xml = compose_bilingual(
        _article("en", "pt", "Title", "main-r"), _article("pt", "en", "Titulo", "pt-r")
    )
    root = etree.fromstring(xml, parser=etree.XMLParser(load_dtd=False, no_network=True))
    meta = root.find("front/article-meta")
    assert meta.find("trans-abstract") is None and meta.find(".//trans-title-group") is None
    assert [g.get(_LANG) for g in meta.findall("kwd-group")] == ["en"]
    sub = root.find("sub-article")
    assert (sub.get("article-type"), sub.get("id"), sub.get(_LANG)) == ("translation", "s1", "pt")
    stub = sub.find("front-stub")
    assert stub.findtext("article-id") == "10.1590/x.2"
    assert stub.findtext("title-group/article-title") == "Titulo"
    assert stub.find("title-group/trans-title-group") is None
    assert stub.find("aff").get("id") == "s1-aff-1"
    assert stub.find(".//xref").get("rid") == "s1-aff-1"
    assert sub.find("body/sec").get("id") == "s1-sec-1"
    assert sub.find(".//xref[@ref-type='bibr']").get("rid") == "main-r1"
    assert sub.find("back") is None  # only a reference list, which stays in the main article
    assert b"<!DOCTYPE article PUBLIC" in xml


def test_same_language_inputs_are_rejected() -> None:
    with pytest.raises(BilingualCompositionError):
        compose_bilingual(_article("en", "pt", "A", "r"), _article("en", "pt", "B", "r"))


def test_missing_orcid_in_main_is_filled_from_translation_by_exact_name() -> None:
    def article(lang: str, other: str, orcid: str) -> bytes:
        contrib = (
            f"<contrib>{orcid}<name><surname>Silva</surname><given-names>Ana</given-names></name>"
            "</contrib>"
        )
        return _article(lang, other, "T", "r").replace(
            b'<contrib><xref ref-type="aff" rid="aff-1">I</xref></contrib>', contrib.encode()
        )

    orcid = '<contrib-id contrib-id-type="orcid">0000-0002-1825-0097</contrib-id>'
    xml = compose_bilingual(article("en", "pt", ""), article("pt", "en", orcid))
    root = etree.fromstring(xml, parser=etree.XMLParser(load_dtd=False, no_network=True))
    assert root.findtext("front/article-meta/contrib-group/contrib/contrib-id") == (
        "0000-0002-1825-0097"
    )
