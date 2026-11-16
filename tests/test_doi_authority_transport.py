import hashlib
import json
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from ops.doi_authority_runtime import authority_lookup
from ops.doi_authority_transport import mount_arguments, stage_authority, trusted_read
from ops.validator_broker import create_arguments, select_spec
from tests.test_doi_snapshot import RESPONSE, XML
from tests.test_validator_transport import request


def setup_case(tmp_path):
    candidate = tmp_path / "candidate.xml"
    candidate.write_bytes(XML)
    snapshot = json.dumps(RESPONSE).encode()
    manifest = {
        "authority": "https://api.crossref.org/works/",
        "candidate_sha256": hashlib.sha256(XML).hexdigest(),
        "snapshot_sha256": hashlib.sha256(snapshot).hexdigest(),
        "retrieved_at": datetime.now(UTC).isoformat(),
    }
    registry, header = request()
    spec = select_spec(registry, header)
    spec["doi_authority"] = {
        "manifest_path": "manifest",
        "snapshot_path": "snapshot",
        "manifest_sha256": "",
    }
    return candidate, snapshot, manifest, spec


def stage(case, **kwargs):
    candidate, snapshot, manifest, spec = case
    raw = json.dumps(manifest).encode()
    spec["doi_authority"]["manifest_sha256"] = hashlib.sha256(raw).hexdigest()
    return stage_authority(
        spec,
        candidate,
        reader=lambda path, limit: {"manifest": raw, "snapshot": snapshot}[path],
        **kwargs,
    )


def test_staged_mounts_remain_offline_read_only_and_scoped(tmp_path):
    case = setup_case(tmp_path)
    folder = stage(case)
    args = mount_arguments(create_arguments(case[3], case[0]), folder)
    assert "--network=none" in args and "--read-only" in args
    assert len([a for a in args if "dst=/authority/" in a and a.endswith(",readonly")]) == 2
    original = lambda _: {"network": "must not run"}  # noqa: E731
    utils = SimpleNamespace(get_doi_information=original)
    with authority_lookup(utils, XML, folder):
        assert utils.get_doi_information("10.1234/test") == RESPONSE
        with pytest.raises(ValueError):
            utils.get_doi_information("10.1234/other")
    assert utils.get_doi_information is original


@pytest.mark.parametrize("kind", ["candidate", "snapshot", "expired", "future", "origin", "sps"])
def test_staging_rejects_invalid_authority_before_writing(tmp_path, kind):
    candidate, snapshot, manifest, spec = setup_case(tmp_path)
    if kind in {"candidate", "snapshot"}:
        manifest[kind + "_sha256"] = "a" * 64
    elif kind in {"expired", "future"}:
        offset = -8 if kind == "expired" else 1
        manifest["retrieved_at"] = (datetime.now(UTC) + timedelta(days=offset)).isoformat()
    elif kind == "origin":
        manifest["authority"] = "https://untrusted.invalid/"
    else:
        spec["name"] = "spsvalidator"
    with pytest.raises(ValueError):
        stage((candidate, snapshot, manifest, spec))
    assert not (tmp_path / "doi-authority").exists()


def test_rejects_manifest_tamper_and_client_authority_selection(tmp_path):
    candidate, _, _, spec = setup_case(tmp_path)
    with pytest.raises(ValueError, match="manifest_mismatch"):
        stage_authority(spec, candidate, reader=lambda *_: b"{}")
    registry, header = request()
    header["doi_authority"] = {"manifest_path": "/user/chosen"}
    with pytest.raises(ValueError, match="invalid_request"):
        select_spec(registry, header)


def test_runtime_rejects_wrong_article_and_restores_callback_after_exception(tmp_path):
    folder = stage(setup_case(tmp_path))
    original = lambda _: None  # noqa: E731
    utils = SimpleNamespace(get_doi_information=original)
    with pytest.raises(ValueError):
        with authority_lookup(utils, XML + b" ", folder):
            pytest.fail("must not enter")
    with pytest.raises(RuntimeError):
        with authority_lookup(utils, XML, folder):
            raise RuntimeError("synthetic validator failure")
    assert utils.get_doi_information is original


def test_absent_configuration_preserves_legacy_and_partial_authority_fails(tmp_path):
    registry, header = request()
    assert stage_authority(select_spec(registry, header), tmp_path / "unused") is None
    original = lambda _: None  # noqa: E731
    utils = SimpleNamespace(get_doi_information=original)
    with authority_lookup(utils, XML, tmp_path / "missing"):
        assert utils.get_doi_information is original
    with pytest.raises(FileNotFoundError):
        with authority_lookup(utils, XML, tmp_path):
            pytest.fail("partial authority must fail closed")


@pytest.mark.parametrize(
    "uid,mode",
    [(10001, stat.S_IFREG | 0o644), (0, stat.S_IFLNK | 0o777), (0, stat.S_IFREG | 0o666)],
)
def test_trusted_reader_rejects_untrusted_owner_symlink_or_writable_path(
    monkeypatch, tmp_path, uid, mode
):
    monkeypatch.setattr(Path, "lstat", lambda _: SimpleNamespace(st_uid=uid, st_mode=mode))
    with pytest.raises(ValueError, match="authority_untrusted_path"):
        trusted_read(tmp_path / "authority.json", 8192)


def test_trusted_reader_rejects_relative_path():
    with pytest.raises(ValueError, match="absolute_path"):
        trusted_read("relative.json", 8192)
