import re

from idml_foundation.pipeline.canonical_mapper import (
    _AFFILIATION,
    _AFFILIATION_NO_DEPARTMENT,
    _split_trailing_country,
    _strip_affiliation_label,
)
from idml_foundation.pipeline.country_codes import iso_country_code


def test_country_names_in_three_languages_map_to_iso_codes() -> None:
    assert [
        iso_country_code(name)
        for name in ("Portugal", "United States", "Estados Unidos", "EUA", "Alemanha", "España")
    ] == ["PT", "US", "US", "US", "DE", "ES"]
    assert iso_country_code("Brazil.") == "BR"
    assert iso_country_code("Atlantis") is None


def test_affiliation_labels_are_stripped_only_when_they_are_labels() -> None:
    assert _strip_affiliation_label("1Universidade Federal", 1) == "Universidade Federal"
    assert _strip_affiliation_label("II Universidade Federal", 2) == "Universidade Federal"
    assert _strip_affiliation_label("IVNTS Electronic Control", 4) == "NTS Electronic Control"
    # Not the expected ordinal: an institution that merely starts with roman letters is kept.
    assert _strip_affiliation_label("IVNTS Electronic Control", 2) == "IVNTS Electronic Control"
    assert _strip_affiliation_label("Instituto Federal", 1) == "Instituto Federal"


def test_multi_segment_city_and_affiliation_without_department() -> None:
    match = _AFFILIATION.fullmatch(
        "Universidad Exemplo, School of X \u2013 Santander, Bucaramanga, Colombia."
    )
    assert isinstance(match, re.Match)
    parts = _split_trailing_country(match).groupdict()
    assert (parts["city"], parts["country"]) == ("Santander, Bucaramanga", "Colombia")
    plain = _AFFILIATION_NO_DEPARTMENT.fullmatch("NTS Electronic Control \u2013 Bogotá, Colombia.")
    assert plain is not None and plain.group("country") == "Colombia"


def test_abnt_last_author_initials_do_not_leak_into_title() -> None:
    from idml_foundation.pipeline.canonical_mapper import _reference_parts

    assert _reference_parts(
        "LOPES, M. D.; NUNES, T. F. Decentralized sewage. Revista Exemplo, v. 12, p. 1-2, 2019."
    ) == (("LOPES, M. D.", "NUNES, T. F"), "Decentralized sewage", "Revista Exemplo")
    assert _reference_parts("SANTOS, R. A. A study of nitrogen. Exemplo, v. 5, 2015.") == (
        ("SANTOS, R. A",),
        "A study of nitrogen",
        "Exemplo",
    )
    assert _reference_parts("SILVA, Ana Maria. Um titulo. Revista, v. 1, 2020.")[1] == "Um titulo"


def test_two_author_parenthetical_citation_accepts_ampersand_and_e() -> None:
    from idml_foundation.pipeline.citation_resolver import ReferenceSignature, _citation_patterns

    signature = ReferenceSignature(target_id="r1", authors=("LOPES", "NUNES"), year="2019")
    pattern = _citation_patterns(signature)[0][0]
    for text in ("(Lopes & Nunes, 2019)", "(LOPES; NUNES, 2019)", "(Lopes e Nunes, 2019)"):
        assert pattern.search(text), text


def test_chart_and_portuguese_captions_keep_label_word_and_family() -> None:
    from idml_foundation.pipeline.canonical_mapper import (
        _CONTINUATION_CAPTION,
        _NUMBERED_GRAPHIC,
        _caption_family,
        _caption_label,
    )
    from idml_foundation.pipeline.object_reference_resolver import _label_namespace

    match = _NUMBERED_GRAPHIC.match("Chart 1. Category of the ICD-10")
    assert match is not None and _caption_family(match.group(1)) == "table"
    assert _caption_label(match.group(1), 1) == "Chart 1"
    assert _caption_label("Fig.", 2) == "Figure 2" and _caption_family("Quadro") == "table"
    assert _CONTINUATION_CAPTION.match(". Continuation.") and _CONTINUATION_CAPTION.match(
        " - Continuação"
    )
    assert not _CONTINUATION_CAPTION.match(". Category of the ICD-10")
    assert _label_namespace("Chart 1") != _label_namespace("Table 1")
    assert _label_namespace("Quadro 1") == _label_namespace("Chart 1") == "chart"
    assert _label_namespace("Tabela 2") == _label_namespace("tables") == "table"


def test_erratum_detection_and_id_rule() -> None:
    from pathlib import Path

    from idml_foundation.pipeline.canonical_mapper import _ERRATUM_CORRECTS
    from idml_foundation.pipeline.profile import load_profile

    found = _ERRATUM_CORRECTS.search("This erratum corrects: https://doi.org/10.1590/1980-5497x.")
    assert found is not None and found.group(1).rstrip(".") == "10.1590/1980-5497x"
    assert _ERRATUM_CORRECTS.search("Esta errata corrige: 10.1590/abc")
    rbepid = load_profile(Path("profiles/rbepid-aop-1.0.json"))
    assert rbepid.article_id_for_doi("10.1590/1980-549720250022erratum") == "e20250022erratum"
    assert rbepid.article_id_for_doi("10.1590/1980-549720250022") == "e250022"
