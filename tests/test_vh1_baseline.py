from copy import deepcopy

import pytest

from idml_foundation.pipeline.profile import load_profile
from idml_foundation.release.validator_registry import ValidatorChannel, load_validator_registry
from ops.vh1_baseline import PROFILE, REGISTRY, ROOT, same_runtime, source_inventory


def test_vh1_selection_does_not_promote_active_configuration():
    original = load_validator_registry(ROOT / "config/validator-registry-v1.json")
    candidate = load_validator_registry(ROOT / REGISTRY)
    assert load_profile().profile_id == "esa-aop-1.0.0"
    assert load_profile(ROOT / PROFILE).profile_id == "esa-aop-1.1.0"
    assert candidate.xpm == original.xpm
    for tool in ("packtools", "spsvalidator"):
        assert (
            candidate.select(tool, ValidatorChannel.ACTIVE).image_id
            != original.select(tool, ValidatorChannel.ACTIVE).image_id
        )
        assert candidate.select(tool, ValidatorChannel.ROLLBACK) == original.select(
            tool, ValidatorChannel.ROLLBACK
        )


@pytest.mark.parametrize("field", ["image_id", "python", "packages", "rules", "wrappers"])
def test_mixed_runtime_cannot_be_treated_as_equivalent(field):
    expected = {
        "image_id": "a" * 64,
        "python": "3.12.14",
        "packages": {"packtools": "1"},
        "rules": "b" * 64,
        "wrappers": "c" * 64,
    }
    same_runtime(expected, deepcopy(expected))
    changed = {**expected, field: "different"}
    with pytest.raises(ValueError, match="vh1_runtime_mismatch"):
        same_runtime(expected, changed)


def test_inventory_includes_native_dtd_and_runtime_glue_but_not_private_corpus():
    result = source_inventory(ROOT)
    paths = result["sha256"]
    assert REGISTRY in paths
    assert "ops/doi_authority_runtime.py" in paths
    assert "src/idml_foundation/services/source_authorization.py" in paths
    assert any(p.startswith("vendor/jats/1.3/") for p in paths)
    assert not any(p.startswith(("tmp/", "benchmarks/private/")) for p in paths)
    assert not any(p.endswith(".env") for p in paths)


def test_inventory_detects_mutated_rule_dependency(tmp_path):
    from tests.test_homologation_inventory import setup_source

    setup_source(tmp_path)
    (tmp_path / REGISTRY).write_text("{}")
    (tmp_path / "requirements-dev.lock").write_text("lock")
    rule = tmp_path / "vendor/jats/1.3/rule.dtd"
    rule.parent.mkdir(parents=True)
    rule.write_text("one")
    first = source_inventory(tmp_path)
    rule.write_text("two")
    with pytest.raises(ValueError, match="vh1_runtime_mismatch"):
        same_runtime(first, source_inventory(tmp_path))
