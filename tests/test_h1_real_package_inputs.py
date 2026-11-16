import hashlib
from types import SimpleNamespace

import pytest

from ops import build_h1_real_packages as builder


@pytest.mark.parametrize("case", ["nested", "root", "corrupt", "duplicate"])
def test_figure_resolution_requires_unique_manifest_hash(tmp_path, monkeypatch, case):
    nested = tmp_path / "package"
    nested.mkdir()
    pdf = nested / "article.pdf"
    monkeypatch.setattr(builder, "_single_artifact", lambda *a: pdf)
    data = b"synthetic-figure"
    artifact = SimpleNamespace(
        role="figure_asset",
        logical_path="figure.jpg",
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
    )
    manifest = SimpleNamespace(artifacts=[artifact])
    location = tmp_path if case == "root" else nested
    (location / "figure.jpg").write_bytes(b"incorrect" if case == "corrupt" else data)
    if case == "duplicate":
        (tmp_path / "figure.jpg").write_bytes(data)
    if case in {"corrupt", "duplicate"}:
        with pytest.raises(ValueError, match="provenance"):
            builder.figure_paths(tmp_path, manifest)
    else:
        assert builder.figure_paths(tmp_path, manifest) == [(location / "figure.jpg").resolve()]
