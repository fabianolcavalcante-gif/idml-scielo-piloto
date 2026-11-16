import pytest

from ops.inventory_homologation import FILES, compare, inventory


def setup_source(root):
    for name in FILES:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}")
    code = root / "src/idml_foundation/example.py"
    code.parent.mkdir(parents=True)
    code.write_text("version = 1")
    return code


def test_inventory_excludes_secrets_and_corpus(tmp_path):
    setup_source(tmp_path)
    (tmp_path / ".env").write_text("private")
    (tmp_path / "private.idml").write_bytes(b"private")
    result = inventory(tmp_path)
    assert len(result["sha256"]) == 4
    assert not result["ready_for_expert"]
    assert inventory(tmp_path) == result


def test_compare_tracks_changed_added_removed(tmp_path):
    code = setup_source(tmp_path)
    old = inventory(tmp_path)
    code.write_text("version = 2")
    other = code.parent / "new.py"
    other.write_text("pass")
    result = compare(inventory(tmp_path), old)
    assert result["changed"] == ["src/idml_foundation/example.py"]
    assert result["added"] == ["src/idml_foundation/new.py"]
    assert result["unchanged"] == 3
    reverse = compare(old, inventory(tmp_path))
    assert reverse["removed"] == result["added"]


def test_missing_required_file_fails_closed(tmp_path):
    with pytest.raises(ValueError):
        inventory(tmp_path)


def test_incompatible_scope_rejected(tmp_path):
    setup_source(tmp_path)
    first = inventory(tmp_path)
    second = {**first, "scope": []}
    with pytest.raises(ValueError):
        compare(first, second)
