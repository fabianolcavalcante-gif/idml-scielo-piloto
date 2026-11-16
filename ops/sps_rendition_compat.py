"""Narrow compatibility view: PDFs follow the actual XML basename, not a computed PID."""

from pathlib import PurePosixPath


class PackageRenditionView:
    def __init__(self, article):
        self._article = article

    def __getattr__(self, name):
        return getattr(self._article, name)

    @property
    def renditions(self):
        stem = self._article.xml_name
        if not isinstance(stem, str) or not stem or PurePosixPath(stem).name != stem:
            raise ValueError("invalid XML basename")
        if "\\" in stem or stem in {".", ".."}:
            raise ValueError("invalid XML basename")
        names = list(self._article.filenames or [])
        if len({name.casefold() for name in names}) != len(names):
            raise ValueError("ambiguous package members")
        results = []
        for rendition in self._article.renditions:
            main = rendition.get("main")
            lang = rendition.get("lang")
            if type(main) is not bool:
                raise ValueError("unresolved rendition role")
            if not main and (not isinstance(lang, str) or not lang.isascii() or not lang.isalpha()):
                raise ValueError("unresolved translation language")
            expected = stem + (".pdf" if main else f"-{lang}.pdf")
            legacy = rendition["name"]
            if legacy != expected and legacy in names and expected in names:
                raise ValueError("ambiguous PDF candidates")
            results.append({**rendition, "name": expected})
        return results


def validate_package(zip_path):
    # Imported only inside the pinned validator environment.
    from packtools.sps.pid_provider.xml_sps_lib import XMLWithPre
    from spsvalidator.domain.validation import validate_sps_xml_with_pre

    rows, exceptions, articles = [], [], []
    count = 0
    for article in XMLWithPre.create(path=zip_path):
        count += 1
        result = validate_sps_xml_with_pre(PackageRenditionView(article))
        rows.extend(result["rows"])
        exceptions.extend(result["exceptions"])
        articles.append(result["article"])
    if not count:
        raise ValueError("package contains no article")
    return {"rows": rows, "exceptions": exceptions, "articles": articles}
