from ops.doi_model_compat import repeatable_doi_model


def test_model_preserves_authors_across_native_rule_iterations():
    class OneShotModel:
        def __init__(self):
            self.authors = (author for author in ("Author A", "Author B"))

        @property
        def data(self):
            return list(self.authors)

    model = repeatable_doi_model(OneShotModel)()
    assert model.data == ["Author A", "Author B"]
    assert model.data == ["Author A", "Author B"]
    assert model.data == ["Author A", "Author B"]
