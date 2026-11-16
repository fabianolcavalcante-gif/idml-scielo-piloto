import sys
from types import SimpleNamespace

import pytest

from ops.sps_rendition_compat import PackageRenditionView, validate_package


def article(names, *, main=True, lang="pt"):
    return SimpleNamespace(
        xml_name="article",
        filenames=names,
        renditions=[{"name": "article_00224.pdf", "main": main, "lang": lang}],
        xmltree=object(),
        assets=["unchanged"],
    )


def test_view_uses_actual_basename_and_preserves_other_data():
    original = article(["article.pdf"])
    view = PackageRenditionView(original)
    assert view.renditions == [{"name": "article.pdf", "main": True, "lang": "pt"}]
    assert view.xmltree is original.xmltree
    assert view.assets == original.assets
    assert original.renditions[0]["name"] == "article_00224.pdf"


@pytest.mark.parametrize("names", [[], ["unrelated.pdf"], ["article_00224.pdf"]])
def test_missing_main_pdf_is_still_missing(names):
    view = PackageRenditionView(article(names))
    assert view.renditions[0]["name"] not in view.filenames


def test_translation_cannot_reuse_main_pdf():
    view = PackageRenditionView(article(["article.pdf"], main=False, lang="en"))
    assert view.renditions[0]["name"] == "article-en.pdf"
    assert view.renditions[0]["name"] not in view.filenames


@pytest.mark.parametrize(
    "names", [["article.pdf", "article_00224.pdf"], ["article.pdf", "ARTICLE.PDF"]]
)
def test_ambiguous_candidates_are_rejected(names):
    with pytest.raises(ValueError, match="ambiguous"):
        _ = PackageRenditionView(article(names)).renditions


@pytest.mark.parametrize("stem", ["../article", "a/b", "a\\b", "..", ""])
def test_unsafe_xml_basename_rejected(stem):
    data = article([])
    data.xml_name = stem
    with pytest.raises(ValueError):
        _ = PackageRenditionView(data).renditions


@pytest.mark.parametrize("main,lang", [(None, "pt"), (False, None), (False, "../en")])
def test_unresolved_renditions_rejected(main, lang):
    with pytest.raises(ValueError):
        _ = PackageRenditionView(article([], main=main, lang=lang)).renditions


def install_native_stubs(monkeypatch, articles, validate):
    monkeypatch.setitem(
        sys.modules,
        "packtools.sps.pid_provider.xml_sps_lib",
        SimpleNamespace(XMLWithPre=SimpleNamespace(create=lambda **kw: articles)),
    )
    monkeypatch.setitem(
        sys.modules,
        "spsvalidator.domain.validation",
        SimpleNamespace(validate_sps_xml_with_pre=validate),
    )


def test_validate_package_preserves_native_findings_and_exceptions(monkeypatch):
    def native(view):
        assert isinstance(view, PackageRenditionView)
        return {"rows": [{"status": "CRITICAL"}], "exceptions": ["sentinel"], "article": {}}

    install_native_stubs(monkeypatch, [article([]), article([])], native)
    assert validate_package("unused.zip") == {
        "rows": [{"status": "CRITICAL"}] * 2,
        "exceptions": ["sentinel"] * 2,
        "articles": [{}, {}],
    }


def test_validate_package_rejects_empty_package(monkeypatch):
    install_native_stubs(monkeypatch, [], None)
    with pytest.raises(ValueError, match="no article"):
        validate_package("unused.zip")


def test_validate_package_does_not_swallow_native_crash(monkeypatch):
    def native(view):
        raise RuntimeError("native failure")

    install_native_stubs(monkeypatch, [article([])], native)
    with pytest.raises(RuntimeError, match="native failure"):
        validate_package("unused.zip")
