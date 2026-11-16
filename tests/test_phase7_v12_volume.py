import pytest

from idml_foundation.ingest.safe_zip import inspect_idml
from idml_foundation.pipeline.service import DeterministicPipeline
from ops.probe_phase7_v12_volume import make_package, make_text_package


@pytest.mark.parametrize("mode", ["stored", "expanded"])
def test_volume_fixture_has_exact_limit_and_valid_pipeline(tmp_path, settings, mode):
    path = tmp_path / "synthetic.idml"
    limit = 1024**2
    make_package(path, **{f"{mode}_bytes": limit})
    data = path.read_bytes()
    inspection = inspect_idml(data, settings)
    if mode == "stored":
        assert len(data) == limit
    else:
        assert inspection.total_uncompressed_bytes == limit
    assert inspection.max_compression_ratio <= settings.zip_max_ratio
    result = DeterministicPipeline(settings=settings).run(data, logical_name="ESA_2024001_AOP.idml")
    assert result.validation.valid


def test_volume_fixture_requires_one_valid_size(tmp_path):
    with pytest.raises(ValueError):
        make_package(tmp_path / "a.idml")
    with pytest.raises(ValueError):
        make_package(tmp_path / "a.idml", stored_bytes=100, expanded_bytes=100)
    with pytest.raises(ValueError):
        make_package(tmp_path / "a.idml", stored_bytes=1)


def test_text_fixture_really_changes_article_text(tmp_path, settings):
    path = tmp_path / "text.idml"
    make_text_package(path, text_bytes=1024)
    result = DeterministicPipeline(settings=settings).run(
        path.read_bytes(), logical_name="ESA_2024001_AOP.idml"
    )
    assert result.validation.valid
    assert b"a" * 1024 in result.xml
    assert b"b" * 1024 in result.xml
