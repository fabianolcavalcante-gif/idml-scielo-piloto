"""Materialize upstream one-shot authors once; preserve native comparison rules."""


def repeatable_doi_model(original):
    class RepeatableDoiModel(original):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.authors = tuple(self.authors)

    return RepeatableDoiModel


def install():
    from packtools.sps.validation import article_doi

    original = article_doi.DoiWithLang
    if not getattr(original, "_idml_repeatable_authors", False):
        model = repeatable_doi_model(original)
        model._idml_repeatable_authors = True
        article_doi.DoiWithLang = model
