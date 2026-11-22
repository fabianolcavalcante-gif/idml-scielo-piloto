"""Compose a bilingual SciELO article: main XML + translation as <sub-article>.

Both inputs are JATS produced by the deterministic pipeline from the two IDMLs of the same
article (e.g. RBEPID ``*_IN_AOP.idml`` and ``*_PT_AOP.idml``), the translation converted with
its own language as primary. Following SciELO SPS and the published RBEPID XML:

* the main article keeps only its own language (no trans-title / trans-abstract and only
  its own keyword group);
* ``<sub-article article-type="translation" id="s1" xml:lang="..">`` holds a front-stub
  (translation DOI, heading, title, contributors and affiliations, abstract, keywords),
  the translated body and the back matter without a reference list;
* every id inside the sub-article is prefixed (``s1-``) and bibliographic cross-references
  point to the main article's references, matched by list position.
"""

from __future__ import annotations

import copy

from lxml import etree

from idml_foundation.pipeline.profile import JournalProfile

_XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"
_PARSER = etree.XMLParser(
    resolve_entities=False, load_dtd=False, no_network=True, recover=False, huge_tree=False
)


class BilingualCompositionError(ValueError):
    pass


def _strip_other_languages(article_meta: etree._Element, language: str) -> None:
    for element in list(article_meta):
        tag = etree.QName(element).localname
        lang = element.get(_XML_LANG)
        if tag == "trans-abstract" or (tag == "kwd-group" and lang not in (None, language)):
            article_meta.remove(element)
    title_group = article_meta.find("title-group")
    if title_group is not None:
        for trans in title_group.findall("trans-title-group"):
            title_group.remove(trans)


def _person_key(contrib: etree._Element) -> tuple[str, str]:
    return (
        " ".join((contrib.findtext("name/surname") or "").split()).casefold(),
        " ".join((contrib.findtext("name/given-names") or "").split()).casefold(),
    )


def _share_contributor_ids(main_meta: etree._Element, translation_meta: etree._Element) -> None:
    """The same authors sign both versions: fill a missing ORCID in the main article from
    the translation (matched by exact surname + given names; never overwritten)."""
    known: dict[tuple[str, str], etree._Element] = {}
    for contrib in translation_meta.iter("contrib"):
        orcid = contrib.find("contrib-id[@contrib-id-type='orcid']")
        if orcid is not None and any(_person_key(contrib)):
            known.setdefault(_person_key(contrib), orcid)
    for contrib in main_meta.iter("contrib"):
        if contrib.find("contrib-id[@contrib-id-type='orcid']") is not None:
            continue
        source = known.get(_person_key(contrib))
        if source is not None:
            contrib.insert(0, copy.deepcopy(source))


def compose_bilingual(main_xml: bytes, translation_xml: bytes, *, prefix: str = "s1") -> bytes:
    main = etree.fromstring(main_xml, parser=_PARSER)
    translation = etree.fromstring(translation_xml, parser=_PARSER)
    main_lang, translation_lang = main.get(_XML_LANG), translation.get(_XML_LANG)
    if not main_lang or not translation_lang or main_lang == translation_lang:
        raise BilingualCompositionError("bilingual_languages_invalid")
    main_meta = main.find("front/article-meta")
    meta = translation.find("front/article-meta")
    if main_meta is None or meta is None:
        raise BilingualCompositionError("bilingual_article_meta_missing")
    _strip_other_languages(main_meta, main_lang)
    _share_contributor_ids(main_meta, meta)

    sub = etree.Element(
        "sub-article",
        {"article-type": "translation", "id": prefix, _XML_LANG: translation_lang},
    )
    stub = etree.SubElement(sub, "front-stub")
    for element in meta.findall("article-id"):
        if element.get("pub-id-type") == "doi":
            stub.append(copy.deepcopy(element))
    for name in ("article-categories", "title-group", "contrib-group"):
        found = meta.find(name)
        if found is not None:
            stub.append(copy.deepcopy(found))
    title_group = stub.find("title-group")
    if title_group is not None:
        for trans in title_group.findall("trans-title-group"):
            title_group.remove(trans)
    for aff in meta.findall("aff"):
        stub.append(copy.deepcopy(aff))
    for element in meta:
        tag = etree.QName(element).localname
        if tag == "abstract" or (
            tag == "kwd-group" and element.get(_XML_LANG) in (None, translation_lang)
        ):
            stub.append(copy.deepcopy(element))
    body = translation.find("body")
    if body is not None:
        sub.append(copy.deepcopy(body))
    back = translation.find("back")
    if back is not None:
        translated_back = copy.deepcopy(back)
        for ref_list in translated_back.findall("ref-list"):
            translated_back.remove(ref_list)
        if len(translated_back):
            sub.append(translated_back)

    main_refs = [ref.get("id") for ref in main.iter("ref")]
    translation_refs = [ref.get("id") for ref in translation.iter("ref")]
    reference_map = {
        source: target
        for source, target in zip(translation_refs, main_refs, strict=False)
        if source and target
    }
    local_ids = {element.get("id") for element in sub.iter() if element.get("id")}
    for element in sub.iter():
        if element.get("id") and element is not sub:
            element.set("id", f"{prefix}-{element.get('id')}")
        rid = element.get("rid")
        if rid:
            targets = []
            for value in rid.split():
                if value in reference_map:
                    targets.append(reference_map[value])
                elif value in local_ids:
                    targets.append(f"{prefix}-{value}")
                else:
                    raise BilingualCompositionError("bilingual_unresolved_cross_reference")
            element.set("rid", " ".join(targets))
    main.append(sub)
    doctype = str(getattr(main.getroottree().docinfo, "doctype", "") or "")
    serialized = etree.tostring(main, encoding="UTF-8", xml_declaration=True, doctype=doctype)
    if not isinstance(serialized, bytes):
        raise TypeError("XML serialization did not return bytes")
    return serialized


def translation_profile(profile: JournalProfile) -> JournalProfile:
    """Same journal profile with the languages swapped, for the translation's own IDML."""
    return profile.model_copy(
        update={
            "primary_language": profile.secondary_language,
            "secondary_language": profile.primary_language,
        }
    )
